#!/usr/bin/env python3
"""Tail Kanban task events for mission progress and Atlas fan-in.

This is intentionally narrower than a router: Kanban remains the source of
truth, while this script reacts to append-only task_events rows. It creates
operator notification outbox rows for blockers/progress/final answers and
idempotently creates one Atlas synthesis task when all worker tasks in a mission
are terminal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
KANBAN_DB = REPO_ROOT / "shared" / "kanban" / "kanban.db"
DEFAULT_LOG = REPO_ROOT / "shared" / "kanban" / "mission-notifier.log"
DISCORD_STATUS_SCRIPT = REPO_ROOT / "scripts" / "discord-post-status.py"
TERMINAL_STATUSES = {"done", "archived"}
ATLAS_SYNTHESIS_SUFFIX = ":atlas-synthesis"
MISSION_RE = re.compile(r"\bconversation_id\s*[:=]\s*([A-Za-z0-9_.:-]+)")
MISSION_TITLE_RE = re.compile(r"\[mission:([^\]]+)\]")
DISCORD_THREAD_RE = re.compile(r"\b(?:discord_)?thread_id\s*[:=]\s*([0-9]{15,25})")
DISCORD_SNOWFLAKE_RE = re.compile(r"^[0-9]{15,25}$")
MAX_MESSAGE_CHARS = 1800
MAX_EMBED_DESCRIPTION_CHARS = 4096


class RunResult:
    def __init__(
        self,
        *,
        processed_events: int = 0,
        outbox_rows: int = 0,
        created_synthesis_tasks: int = 0,
        final_responses_ready: int = 0,
        delivered_rows: int = 0,
    ) -> None:
        self.processed_events = processed_events
        self.outbox_rows = outbox_rows
        self.created_synthesis_tasks = created_synthesis_tasks
        self.final_responses_ready = final_responses_ready
        self.delivered_rows = delivered_rows

    def to_dict(self) -> dict[str, int]:
        return {
            "processed_events": self.processed_events,
            "outbox_rows": self.outbox_rows,
            "created_synthesis_tasks": self.created_synthesis_tasks,
            "final_responses_ready": self.final_responses_ready,
            "delivered_rows": self.delivered_rows,
        }

    def merge(self, other: "RunResult") -> "RunResult":
        self.processed_events += other.processed_events
        self.outbox_rows += other.outbox_rows
        self.created_synthesis_tasks += other.created_synthesis_tasks
        self.final_responses_ready += other.final_responses_ready
        self.delivered_rows += other.delivered_rows
        return self


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tail Team Nexus Kanban mission events and queue user updates")
    parser.add_argument("--db", default=str(KANBAN_DB), help="Path to shared kanban.db")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="Notifier log path")
    parser.add_argument("--limit", type=int, default=100, help="Maximum task events to process per pass")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between daemon passes")
    parser.add_argument("--deliver", action="store_true", help="Deliver pending outbox rows through scripts/discord-post-status.py")
    parser.add_argument("--dry-run", action="store_true", help="Show delivery payloads without posting")
    return parser.parse_args()


def log(path: Path, message: str) -> None:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"{timestamp} {message}"
    print(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mission_notifier_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mission_notification_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            task_id TEXT,
            kind TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT 'discord:status',
            message TEXT NOT NULL,
            payload_json TEXT,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at INTEGER NOT NULL,
            sent_at INTEGER,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mission_outbox_status ON mission_notification_outbox(status, id);
        CREATE INDEX IF NOT EXISTS idx_mission_outbox_conversation ON mission_notification_outbox(conversation_id);
        """
    )
    columns = table_columns(conn, "mission_notification_outbox")
    if "payload_json" not in columns:
        conn.execute("ALTER TABLE mission_notification_outbox ADD COLUMN payload_json TEXT")
    conn.commit()


def get_state(conn: sqlite3.Connection, key: str, default: str = "0") -> str:
    row = conn.execute("SELECT value FROM mission_notifier_state WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else default


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO mission_notifier_state(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def safe_json_loads(text: Optional[str]) -> dict[str, Any]:
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"value": value}
    except json.JSONDecodeError:
        return {"raw": text}


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def human_agent(slug: Optional[str]) -> str:
    if not slug:
        return "Unassigned"
    return slug.replace("-", " ").replace("_", " ").title()


def extract_conversation_id(task: sqlite3.Row, payload: dict[str, Any]) -> Optional[str]:
    for key in ("conversation_id", "mission_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for source in (task["body"] or "", task["title"] or ""):
        match = MISSION_RE.search(source)
        if match:
            return match.group(1)
        match = MISSION_TITLE_RE.search(source)
        if match:
            return match.group(1)
    return None


def extract_discord_thread_id(task: sqlite3.Row, payload: dict[str, Any], conversation_id: str) -> Optional[str]:
    for key in ("discord_thread_id", "thread_id", "discord_thread"):
        value = payload.get(key)
        if isinstance(value, str) and DISCORD_SNOWFLAKE_RE.match(value.strip()):
            return value.strip()
        if isinstance(value, int):
            text = str(value)
            if DISCORD_SNOWFLAKE_RE.match(text):
                return text
    for source in (task["body"] or "", task["title"] or ""):
        match = DISCORD_THREAD_RE.search(source)
        if match:
            return match.group(1)
    if DISCORD_SNOWFLAKE_RE.match(conversation_id):
        return conversation_id
    return None


def discord_target(channel: str = "status", thread_id: Optional[str] = None) -> str:
    return f"discord:{channel}:{thread_id}" if thread_id else f"discord:{channel}"


def parse_discord_target(target: str) -> tuple[str, Optional[str]]:
    parts = target.split(":", 2)
    if len(parts) < 2 or parts[0] != "discord":
        return "status", None
    channel = parts[1] or "status"
    thread_id = parts[2] if len(parts) == 3 and DISCORD_SNOWFLAKE_RE.match(parts[2]) else None
    return channel, thread_id


def discord_embed_payload(*, title: str, description: str, conversation_id: str, task_id: Optional[str], kind: str) -> str:
    trimmed_description = description.strip()
    if len(trimmed_description) > MAX_EMBED_DESCRIPTION_CHARS:
        trimmed_description = trimmed_description[: MAX_EMBED_DESCRIPTION_CHARS - 1] + "…"
    fields = [
        {"name": "Conversation", "value": conversation_id, "inline": True},
        {"name": "Kind", "value": kind, "inline": True},
    ]
    if task_id:
        fields.append({"name": "Kanban task", "value": task_id, "inline": True})
    return json.dumps(
        {
            "content": None,
            "embeds": [
                {
                    "title": title,
                    "description": trimmed_description,
                    "color": 0x7C5CFF,
                    "fields": fields,
                    "footer": {"text": "Team Nexus / Atlas"},
                }
            ],
            "allowed_mentions": {"parse": []},
        },
        sort_keys=True,
    )


def final_response_payload(conversation_id: str, task_id: str, summary: str) -> str:
    return discord_embed_payload(
        title="Atlas completed",
        description=summary,
        conversation_id=conversation_id,
        task_id=task_id,
        kind="final_response_ready",
    )


def is_atlas_synthesis_task(task: sqlite3.Row, conversation_id: Optional[str] = None) -> bool:
    key = task["idempotency_key"] if "idempotency_key" in task.keys() else None
    if key and key.endswith(ATLAS_SYNTHESIS_SUFFIX):
        return True
    title = task["title"] or ""
    if "synthesize final answer" in title.lower() and task["assignee"] == "atlas":
        if conversation_id is None or f"[mission:{conversation_id}]" in title:
            return True
    return False


def event_summary(task: sqlite3.Row, payload: dict[str, Any]) -> str:
    for key in ("reason", "summary", "error", "message", "result"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("result", "body"):
        try:
            value = task[key]
        except Exception:
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip().splitlines()[0]
    return task["title"] or task["id"]


def enqueue_outbox(
    conn: sqlite3.Connection,
    *,
    conversation_id: str,
    task_id: Optional[str],
    kind: str,
    message: str,
    idempotency_key: str,
    target: str = "discord:status",
    status: str = "pending",
    payload_json: Optional[str] = None,
) -> bool:
    now = int(time.time())
    trimmed = message.strip()
    if len(trimmed) > MAX_MESSAGE_CHARS:
        trimmed = trimmed[: MAX_MESSAGE_CHARS - 1] + "…"
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO mission_notification_outbox
            (conversation_id, task_id, kind, target, message, payload_json, idempotency_key, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (conversation_id, task_id, kind, target, trimmed, payload_json, idempotency_key, status, now),
    )
    return cur.rowcount == 1


def get_task(conn: sqlite3.Connection, task_id: str) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def mission_tasks(conn: sqlite3.Connection, conversation_id: str) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    like_body = f"%conversation_id:%{conversation_id}%"
    like_title = f"%[mission:{conversation_id}]%"
    return conn.execute(
        """
        SELECT * FROM tasks
         WHERE body LIKE ? OR title LIKE ? OR idempotency_key = ?
         ORDER BY created_at, id
        """,
        (like_body, like_title, f"mission:{conversation_id}:atlas-synthesis"),
    ).fetchall()


def worker_mission_tasks(conn: sqlite3.Connection, conversation_id: str) -> list[sqlite3.Row]:
    return [
        task
        for task in mission_tasks(conn, conversation_id)
        if not is_atlas_synthesis_task(task, conversation_id)
        and (task["assignee"] or "") != "atlas"
    ]


def mission_ready_for_synthesis(conn: sqlite3.Connection, conversation_id: str) -> bool:
    workers = worker_mission_tasks(conn, conversation_id)
    return bool(workers) and all((task["status"] in TERMINAL_STATUSES) for task in workers)


def latest_completion_summary(conn: sqlite3.Connection, task_id: str, fallback: str) -> str:
    row = conn.execute(
        """
        SELECT payload FROM task_events
         WHERE task_id = ? AND kind IN ('completed', 'done')
         ORDER BY id DESC LIMIT 1
        """,
        (task_id,),
    ).fetchone()
    if row:
        payload = safe_json_loads(row[0])
        for key in ("reason", "summary", "error", "message", "result"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return fallback.strip() if fallback and fallback.strip() else "No summary recorded."


def latest_run_handoff(conn: sqlite3.Connection, task_id: str) -> tuple[Optional[str], dict[str, Any]]:
    row = conn.execute(
        """
        SELECT summary, metadata FROM task_runs
         WHERE task_id = ?
         ORDER BY id DESC LIMIT 1
        """,
        (task_id,),
    ).fetchone()
    if not row:
        return None, {}
    metadata = safe_json_loads(row[1]) if len(row) > 1 else {}
    summary = row[0].strip() if isinstance(row[0], str) and row[0].strip() else None
    return summary, metadata


def final_answer_text(conn: sqlite3.Connection, task: sqlite3.Row, payload: dict[str, Any]) -> str:
    result = task["result"] if "result" in task.keys() else None
    if isinstance(result, str) and result.strip():
        return result.strip()
    run_summary, run_metadata = latest_run_handoff(conn, task["id"])
    for source in (payload, run_metadata):
        for key in ("final_answer", "answer", "response", "result"):
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, str) and value.strip():
                return value.strip()
    if run_summary:
        return run_summary
    return event_summary(task, payload)


def mission_worker_summary_block(conn: sqlite3.Connection, conversation_id: str) -> str:
    lines = []
    for task in worker_mission_tasks(conn, conversation_id):
        summary = latest_completion_summary(conn, task["id"], task["result"] or "")
        lines.append(f"- {task['id']} ({task['assignee']}, {task['status']}): {summary}")
    return "\n".join(lines) if lines else "- No worker tasks found."


def mission_discord_thread_id(conn: sqlite3.Connection, conversation_id: str) -> Optional[str]:
    for task in mission_tasks(conn, conversation_id):
        thread_id = extract_discord_thread_id(task, {}, conversation_id)
        if thread_id:
            return thread_id
    if DISCORD_SNOWFLAKE_RE.match(conversation_id):
        return conversation_id
    return None


def synthesis_task_exists(conn: sqlite3.Connection, conversation_id: str) -> bool:
    row = conn.execute(
        "SELECT id FROM tasks WHERE idempotency_key = ? LIMIT 1",
        (f"mission:{conversation_id}:atlas-synthesis",),
    ).fetchone()
    return row is not None


def create_atlas_synthesis_task(conn: sqlite3.Connection, conversation_id: str) -> Optional[str]:
    if synthesis_task_exists(conn, conversation_id):
        return None
    now = int(time.time())
    task_id = f"mission-synth-{short_hash(conversation_id)}"
    title = f"[mission:{conversation_id}] synthesize final answer"
    artifact_hint = f"/shared/project/artifacts/missions/{conversation_id}/"
    worker_summaries = mission_worker_summary_block(conn, conversation_id)
    thread_id = mission_discord_thread_id(conn, conversation_id)
    discord_thread_line = f"discord_thread_id: {thread_id}\n" if thread_id else ""
    direct_reply_lines = (
        f"reply_mode: direct_discord\nreply_target: discord:{thread_id}\nreply_expected: true\n"
        if thread_id
        else "reply_mode: kanban_only\nreply_expected: false\n"
    )
    body = f"""conversation_id: {conversation_id}
{discord_thread_line}{direct_reply_lines}assignee: atlas
objective: Synthesize the final user-facing answer for this mission.

The notifier created this task because all non-Atlas worker tasks for the mission are terminal.

Worker task summaries available at synthesis time:
{worker_summaries}

Read completed worker outputs, Kanban task results/comments, and artifacts for this mission.
Artifact directory convention: {artifact_hint}

Rules:
- Do not claim missing work was completed.
- If any required artifact or answer is missing, block this task and ask for operator intervention.
- Produce the actual final user-facing answer, not just a completion/status note.
- If `reply_mode: direct_discord`, send the final answer to `reply_target` with `send_message` before completing this task. Use the full final answer as the Discord message.
- When completing this Kanban task, put the full final answer in `kanban_complete(result=...)`, use `summary` only for a one-sentence delivery/status note, and include reply evidence in metadata when available (`discord_reply_sent`, `reply_target`, `discord_message_id`).
- Include material task IDs and artifact paths when useful.
"""
    columns = table_columns(conn, "tasks")
    insert_cols = ["id", "title", "body", "assignee", "status", "priority", "created_by", "created_at", "idempotency_key"]
    values: list[Any] = [task_id, title, body, "atlas", "ready", 0, "mission-notifier", now, f"mission:{conversation_id}:atlas-synthesis"]
    if "workspace_kind" in columns:
        insert_cols.append("workspace_kind")
        values.append("scratch")
    placeholders = ", ".join("?" for _ in insert_cols)
    conn.execute(f"INSERT INTO tasks ({', '.join(insert_cols)}) VALUES ({placeholders})", values)
    conn.execute(
        "INSERT INTO task_events(task_id, kind, payload, created_at) VALUES (?, 'created', ?, ?)",
        (task_id, json.dumps({"by": "mission-notifier", "conversation_id": conversation_id}), now),
    )
    return task_id


def handle_blocked_event(conn: sqlite3.Connection, event: sqlite3.Row, task: sqlite3.Row, conversation_id: str, payload: dict[str, Any]) -> RunResult:
    summary = event_summary(task, payload)
    message = f"Blocked: {human_agent(task['assignee'])} needs input for {event['task_id']} in {conversation_id}: {summary}"
    inserted = enqueue_outbox(
        conn,
        conversation_id=conversation_id,
        task_id=event["task_id"],
        kind="human_blocker",
        message=message,
        idempotency_key=f"notify:{conversation_id}:{event['task_id']}:blocked:{event['id']}",
    )
    return RunResult(outbox_rows=1 if inserted else 0)


def handle_completed_event(conn: sqlite3.Connection, event: sqlite3.Row, task: sqlite3.Row, conversation_id: str, payload: dict[str, Any]) -> RunResult:
    result = RunResult()
    summary = event_summary(task, payload)
    if is_atlas_synthesis_task(task, conversation_id):
        thread_id = extract_discord_thread_id(task, payload, conversation_id)
        message = f"Atlas completed synthesis for {conversation_id}: {summary}"
        if enqueue_outbox(
            conn,
            conversation_id=conversation_id,
            task_id=event["task_id"],
            kind="final_response_ready",
            message=message,
            idempotency_key=f"final:{conversation_id}:{event['task_id']}:{event['id']}",
            target=discord_target("status", thread_id),
            payload_json=final_response_payload(conversation_id, event["task_id"], summary),
        ):
            result.outbox_rows += 1
            result.final_responses_ready += 1
        return result

    message = f"Completed: {human_agent(task['assignee'])} finished {event['task_id']} for {conversation_id}: {summary}"
    if enqueue_outbox(
        conn,
        conversation_id=conversation_id,
        task_id=event["task_id"],
        kind="human_update",
        message=message,
        idempotency_key=f"notify:{conversation_id}:{event['task_id']}:completed:{event['id']}",
        target="atlas:mission",
        status="queued",
    ):
        result.outbox_rows += 1

    if mission_ready_for_synthesis(conn, conversation_id):
        synth_id = create_atlas_synthesis_task(conn, conversation_id)
        if synth_id:
            result.created_synthesis_tasks += 1
            if enqueue_outbox(
                conn,
                conversation_id=conversation_id,
                task_id=synth_id,
                kind="mission_ready_for_synthesis",
                message=f"Mission {conversation_id} has all worker tasks complete; queued Atlas synthesis task {synth_id}.",
                idempotency_key=f"notify:{conversation_id}:synthesis-created",
                target="atlas:kanban",
                status="queued",
            ):
                result.outbox_rows += 1
    return result


def handle_failed_event(conn: sqlite3.Connection, event: sqlite3.Row, task: sqlite3.Row, conversation_id: str, payload: dict[str, Any]) -> RunResult:
    summary = event_summary(task, payload)
    message = f"Attention: {human_agent(task['assignee'])} task {event['task_id']} hit {event['kind']} in {conversation_id}: {summary}"
    inserted = enqueue_outbox(
        conn,
        conversation_id=conversation_id,
        task_id=event["task_id"],
        kind="human_blocker",
        message=message,
        idempotency_key=f"notify:{conversation_id}:{event['task_id']}:{event['kind']}:{event['id']}",
    )
    return RunResult(outbox_rows=1 if inserted else 0)


def process_events(conn: sqlite3.Connection, limit: int = 100) -> RunResult:
    ensure_schema(conn)
    conn.row_factory = sqlite3.Row
    last_id = int(get_state(conn, "last_event_id", "0"))
    events = conn.execute(
        "SELECT * FROM task_events WHERE id > ? ORDER BY id ASC LIMIT ?",
        (last_id, limit),
    ).fetchall()
    result = RunResult(processed_events=len(events))
    max_seen = last_id
    for event in events:
        max_seen = max(max_seen, int(event["id"]))
        task = get_task(conn, event["task_id"])
        if task is None:
            continue
        payload = safe_json_loads(event["payload"])
        conversation_id = extract_conversation_id(task, payload)
        if not conversation_id:
            continue
        kind = event["kind"]
        if kind in {"blocked", "dispatch_timed_out"}:
            result.merge(handle_blocked_event(conn, event, task, conversation_id, payload))
        elif kind in {"completed", "done"}:
            result.merge(handle_completed_event(conn, event, task, conversation_id, payload))
        elif kind in {"dispatch_failed", "failed", "error"}:
            result.merge(handle_failed_event(conn, event, task, conversation_id, payload))
    set_state(conn, "last_event_id", str(max_seen))
    conn.commit()
    return result


def pending_outbox(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn.execute(
        "SELECT * FROM mission_notification_outbox WHERE status = 'pending' AND target LIKE 'discord:%' ORDER BY id ASC LIMIT ?",
        (limit,),
    ).fetchall()


def deliver_pending(conn: sqlite3.Connection, *, dry_run: bool = False, limit: int = 20) -> RunResult:
    rows = pending_outbox(conn, limit=limit)
    delivered = 0
    for row in rows:
        channel, thread_id = parse_discord_target(row["target"])
        cmd = [sys.executable, str(DISCORD_STATUS_SCRIPT), "--channel", channel]
        if row["payload_json"]:
            cmd.extend(["--payload-json", row["payload_json"]])
        else:
            cmd.extend(["--message", row["message"]])
        if thread_id:
            cmd.extend(["--thread-id", thread_id])
        if dry_run:
            cmd.append("--dry-run")
        try:
            proc = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True, timeout=30)
        except Exception as exc:  # pragma: no cover - defensive delivery path
            conn.execute("UPDATE mission_notification_outbox SET status = 'failed', error = ? WHERE id = ?", (str(exc), row["id"]))
            continue
        if proc.returncode == 0:
            status = "dry_run" if dry_run else "sent"
            conn.execute(
                "UPDATE mission_notification_outbox SET status = ?, sent_at = ?, error = NULL WHERE id = ?",
                (status, int(time.time()), row["id"]),
            )
            delivered += 1
        else:
            err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[:500]
            conn.execute("UPDATE mission_notification_outbox SET status = 'failed', error = ? WHERE id = ?", (err, row["id"]))
    conn.commit()
    return RunResult(delivered_rows=delivered)


def run_once(db: Path | str = KANBAN_DB, *, limit: int = 100, deliver: bool = False, dry_run: bool = False) -> RunResult:
    db_path = Path(db)
    if not db_path.exists():
        raise SystemExit(f"missing Kanban DB: {db_path}; run `make kanban-init` first")
    with sqlite3.connect(db_path) as conn:
        result = process_events(conn, limit=limit)
        if deliver or dry_run:
            result.merge(deliver_pending(conn, dry_run=dry_run, limit=limit))
        return result


def main() -> int:
    args = parse_args()
    db = Path(args.db)
    log_path = Path(args.log)
    while True:
        result = run_once(db, limit=args.limit, deliver=args.deliver, dry_run=args.dry_run)
        log(log_path, json.dumps(result.to_dict(), sort_keys=True))
        if not args.daemon:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
