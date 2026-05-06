#!/usr/bin/env python3
"""Team Nexus message router MVP."""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sqlite3
import string
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("TEAM_NEXUS_ROOT", Path(__file__).resolve().parents[1])).resolve()
SHARED_ROOT = Path(
    os.environ.get(
        "TEAM_NEXUS_SHARED_ROOT",
        "/shared" if (Path("/shared/router").exists() and Path("/shared/kanban").exists()) else str(REPO_ROOT / "shared"),
    )
).resolve()
DEFAULT_DB_PATH = SHARED_ROOT / "router" / "messages.db"
DEFAULT_POLICY_PATH = SHARED_ROOT / "router" / "router-policy.yaml"
DEFAULT_AGENTS_PATH = SHARED_ROOT / "team-agents.yaml"
DEFAULT_KANBAN_DB_PATH = SHARED_ROOT / "kanban" / "kanban.db"
ARTIFACT_DIR = SHARED_ROOT / "project" / "artifacts" / "router"
COMPOSE_CMD = [
    "docker", "compose",
    "-f", "docker-compose.yml",
    "-f", "docker-compose.agents.generated.yml",
    "-f", "docker-compose.dashboards.generated.yml",
]
KNOWN_STATUSES = {"pending", "dispatching", "dispatched", "blocked", "failed", "completed"}
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\b[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|WEBHOOK[_-]?URL)\s*="),
    re.compile(r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
]


class RouterError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_message_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    return f"msg_{ts}_{suffix}"


def db_path(path: str | os.PathLike[str] | None) -> Path:
    return Path(path) if path else DEFAULT_DB_PATH


def connect_db(path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    p = db_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str | os.PathLike[str] | None = None) -> None:
    with connect_db(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages(
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                parent_id TEXT,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                type TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'normal',
                ttl INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                requires_response INTEGER NOT NULL DEFAULT 1,
                reply_to TEXT,
                summary TEXT NOT NULL,
                body_json TEXT NOT NULL,
                artifacts_json TEXT NOT NULL DEFAULT '[]',
                trace_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT,
                kanban_task_id TEXT
            );
            CREATE TABLE IF NOT EXISTS route_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations(
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'open',
                summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                expected_count INTEGER NOT NULL DEFAULT 0,
                terminal_count INTEGER NOT NULL DEFAULT 0,
                report_task_id TEXT,
                report_error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_route_events_message_id ON route_events(message_id);
            CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);
            """
        )


def _parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [item.strip().strip('"\'') for item in inner.split(",")]


def load_agents(path: str | os.PathLike[str] | None = None) -> set[str]:
    p = Path(path) if path else DEFAULT_AGENTS_PATH
    agents: set[str] = set()
    in_agents = False
    current: str | None = None
    enabled: bool | None = None
    for line in p.read_text().splitlines():
        if line.strip() == "agents:":
            in_agents = True
            continue
        if not in_agents:
            continue
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            if current and enabled is not False:
                agents.add(current)
            current = m.group(1)
            enabled = None
            continue
        m = re.match(r"^    enabled:\s*(true|false)\s*$", line)
        if m and current:
            enabled = (m.group(1) == "true")
    if current and enabled is not False:
        agents.add(current)
    return agents


def load_policy(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_POLICY_PATH
    policy: dict[str, Any] = {"routes": {}, "groups": {}, "limits": {}}
    section: str | None = None
    current_route: str | None = None
    for raw in p.read_text().splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^[A-Za-z_-]+:\s*$", line):
            section = stripped[:-1]
            current_route = None
            continue
        if section == "routes":
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if m:
                current_route = m.group(1)
                policy["routes"].setdefault(current_route, {})
                continue
            m = re.match(r"^    can_send_to:\s*(\[.*\])\s*$", line)
            if m and current_route:
                policy["routes"][current_route]["can_send_to"] = _parse_inline_list(m.group(1))
                continue
        elif section == "groups":
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*(\[.*\])\s*$", line)
            if m:
                policy["groups"][m.group(1)] = _parse_inline_list(m.group(2))
                continue
        elif section == "limits":
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*([0-9]+)\s*$", line)
            if m:
                policy["limits"][m.group(1)] = int(m.group(2))
                continue
    return policy


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true/false")


def build_body(goal: str, deliverable: str) -> dict[str, str]:
    return {"goal": goal, "deliverable": deliverable}


def reject_sensitive_text(*values: str) -> None:
    text = "\n".join(v for v in values if v)
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            raise RouterError("sensitive payload rejected; route summaries/goals/deliverables must not include secrets or raw credentials")


def validate_and_expand(
    sender: str,
    recipient: str,
    summary: str,
    body: dict[str, Any],
    ttl: int | None = None,
    trace: list[str] | None = None,
    allow_wide_fanout: bool = False,
    agents: set[str] | None = None,
    policy: dict[str, Any] | None = None,
) -> tuple[list[str], int]:
    agents = agents if agents is not None else load_agents()
    policy = policy if policy is not None else load_policy()
    limits = policy.get("limits", {})
    groups = policy.get("groups", {})
    routes = policy.get("routes", {})
    if sender not in agents:
        raise RouterError(f"unknown sender: {sender}")
    if recipient not in agents and recipient not in groups:
        raise RouterError(f"unknown recipient: {recipient}")
    allowed = set(routes.get(sender, {}).get("can_send_to", []))
    if recipient not in allowed:
        if not (recipient == "all-workers" and allow_wide_fanout and sender == "atlas"):
            raise RouterError(f"sender {sender} may not send to {recipient}")
    actual_ttl = int(ttl) if ttl is not None else int(limits.get("default_ttl", 3))
    max_ttl = int(limits.get("max_ttl", 5))
    if actual_ttl < 1 or actual_ttl > max_ttl:
        raise RouterError(f"ttl must be 1..{max_ttl}")
    max_summary = int(limits.get("max_summary_chars", 240))
    if len(summary) > max_summary:
        raise RouterError(f"summary exceeds {max_summary} characters")
    body_json = json.dumps(body, sort_keys=True, separators=(",", ":"))
    max_body = int(limits.get("max_body_chars", 4000))
    if len(body_json) > max_body:
        raise RouterError(f"body_json exceeds {max_body} characters")
    recipients = list(groups.get(recipient, [recipient]))
    max_fanout = int(limits.get("max_fanout", 3))
    if recipient == "all-workers" and not allow_wide_fanout:
        raise RouterError("all-workers requires --allow-wide-fanout")
    if len(recipients) > max_fanout and not allow_wide_fanout:
        raise RouterError(f"fanout {len(recipients)} exceeds max_fanout {max_fanout}")
    trace_set = set(trace or [])
    loops = [r for r in recipients if r in trace_set]
    if loops:
        raise RouterError(f"recipient already in trace: {loops[0]}")
    unknown = [r for r in recipients if r not in agents]
    if unknown:
        raise RouterError(f"group contains unknown agent: {unknown[0]}")
    return recipients, actual_ttl


def _insert_event(conn: sqlite3.Connection, message_id: str, kind: str, payload: dict[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO route_events(message_id, kind, payload_json, created_at) VALUES (?, ?, ?, ?)",
        (message_id, kind, json.dumps(payload or {}, sort_keys=True), now_iso()),
    )


def _conversation_event_id(conversation_id: str) -> str:
    return f"conversation:{conversation_id}"


def _upsert_conversation(conn: sqlite3.Connection, conversation_id: str, summary: str) -> None:
    now = now_iso()
    conn.execute(
        """
        INSERT INTO conversations(id, status, summary, created_at, updated_at, expected_count, terminal_count)
        VALUES (?, 'open', ?, ?, ?, 0, 0)
        ON CONFLICT(id) DO UPDATE SET
            summary = COALESCE(conversations.summary, excluded.summary),
            updated_at = excluded.updated_at
        """,
        (conversation_id, summary, now, now),
    )


def _refresh_conversation_counts(conn: sqlite3.Connection, conversation_id: str) -> dict[str, int]:
    counts = {status: 0 for status in sorted(KNOWN_STATUSES)}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM messages WHERE conversation_id=? GROUP BY status", (conversation_id,)):
        counts[row["status"]] = int(row["n"])
    expected = conn.execute("SELECT COUNT(*) AS n FROM messages WHERE conversation_id=? AND requires_response=1", (conversation_id,)).fetchone()["n"]
    terminal = conn.execute("SELECT COUNT(*) AS n FROM messages WHERE conversation_id=? AND requires_response=1 AND status IN ('completed','blocked','failed')", (conversation_id,)).fetchone()["n"]
    conn.execute(
        "UPDATE conversations SET expected_count=?, terminal_count=?, updated_at=? WHERE id=?",
        (int(expected), int(terminal), now_iso(), conversation_id),
    )
    counts["total"] = sum(counts.values())
    counts["expected"] = int(expected)
    counts["terminal"] = int(terminal)
    return counts


def send_messages(
    db: str | os.PathLike[str] | None,
    sender: str,
    recipient: str,
    msg_type: str,
    summary: str,
    goal: str,
    deliverable: str,
    conversation_id: str | None = None,
    parent_id: str | None = None,
    priority: str = "normal",
    ttl: int | None = None,
    requires_response: bool = True,
    allow_wide_fanout: bool = False,
    trace: list[str] | None = None,
) -> list[str]:
    body = build_body(goal, deliverable)
    reject_sensitive_text(summary, goal, deliverable)
    recipients, actual_ttl = validate_and_expand(sender, recipient, summary, body, ttl, trace, allow_wide_fanout)
    if conversation_id is None and len(recipients) > 1:
        conversation_id = new_message_id()
    init_db(db)
    ids: list[str] = []
    created = now_iso()
    with connect_db(db) as conn:
        conversation_ids: set[str] = set()
        for rec in recipients:
            mid = new_message_id()
            ids.append(mid)
            conv = conversation_id or mid
            conversation_ids.add(conv)
            _upsert_conversation(conn, conv, summary)
            trace_list = list(trace or []) + [sender, rec]
            body_json = json.dumps(body, sort_keys=True, separators=(",", ":"))
            conn.execute(
                """
                INSERT INTO messages(id, conversation_id, parent_id, sender, recipient, type, priority, ttl,
                    created_at, requires_response, reply_to, summary, body_json, artifacts_json, trace_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    mid, conv, parent_id, sender, rec, msg_type, priority, actual_ttl, created,
                    1 if requires_response else 0, ("atlas" if requires_response else None), summary,
                    body_json, "[]", json.dumps(trace_list),
                ),
            )
            _insert_event(conn, mid, "created", {"requested_recipient": recipient})
        for conv in conversation_ids:
            _refresh_conversation_counts(conn, conv)
    return ids


def row_to_envelope(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "parent_id": row["parent_id"],
        "from": row["sender"],
        "to": row["recipient"],
        "sender": row["sender"],
        "recipient": row["recipient"],
        "type": row["type"],
        "priority": row["priority"],
        "ttl": row["ttl"],
        "created_at": row["created_at"],
        "requires_response": bool(row["requires_response"]),
        "reply_to": row["reply_to"],
        "summary": row["summary"],
        "body": json.loads(row["body_json"]),
        "artifacts": json.loads(row["artifacts_json"]),
        "trace": json.loads(row["trace_json"]),
        "status": row["status"],
        "error": row["error"],
        "kanban_task_id": row["kanban_task_id"],
    }


def list_messages(db: str | os.PathLike[str] | None = None, status: str | None = None, out: Any = None) -> None:
    if status and status not in KNOWN_STATUSES:
        raise RouterError(f"status must be one of: {', '.join(sorted(KNOWN_STATUSES))}")
    init_db(db)
    out = out or sys.stdout
    with connect_db(db) as conn:
        if status:
            rows = conn.execute("SELECT * FROM messages WHERE status=? ORDER BY created_at, id", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM messages ORDER BY created_at, id").fetchall()
    print(f"{'ID':<28} {'from':<10} {'to':<10} {'type':<14} {'ttl':<3} {'status':<10} summary", file=out)
    for r in rows:
        print(f"{r['id']:<28} {r['sender']:<10} {r['recipient']:<10} {r['type']:<14} {r['ttl']:<3} {r['status']:<10} {r['summary']}", file=out)


def inspect_message(db: str | os.PathLike[str] | None, message_id: str, out: Any = None) -> dict[str, Any]:
    init_db(db)
    out = out or sys.stdout
    with connect_db(db) as conn:
        row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if row is None:
            raise RouterError(f"message not found: {message_id}")
        events = conn.execute("SELECT kind, payload_json, created_at FROM route_events WHERE message_id=? ORDER BY id", (message_id,)).fetchall()
    payload = row_to_envelope(row)
    payload["events"] = [{"kind": e["kind"], "payload": json.loads(e["payload_json"]), "created_at": e["created_at"]} for e in events]
    print(json.dumps(payload, indent=2, sort_keys=True), file=out)
    return payload


def parse_kanban_task_id(output: str) -> str | None:
    # Prefer JSON emitted by `kanban create --json`. Compose/run wrappers may add
    # log lines before or after a pretty-printed JSON object, so parse from every
    # object start instead of assuming one compact JSON object per line.
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", output):
        try:
            payload, _ = decoder.raw_decode(output[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("id"):
            return str(payload["id"])
    # Fall back to obvious Kanban task IDs in either legacy K... or current t_...
    # formats.
    m = re.search(r"\b(K[0-9][A-Za-z0-9_-]*|t_[A-Za-z0-9_-]+)\b", output)
    return m.group(1) if m else None


def artifact_display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def build_kanban_body(envelope: dict[str, Any], artifact_path: Path) -> str:
    body = envelope.get("body", {})
    return "\n".join([
        "Router-dispatched Team Nexus task.",
        "",
        f"Message: {envelope['id']}",
        f"Conversation: {envelope['conversation_id']}",
        f"From: {envelope['from']}",
        f"To: {envelope['to']}",
        f"Reply to: {envelope.get('reply_to') or 'atlas'}",
        f"Router artifact: {artifact_display_path(artifact_path)}",
        "",
        f"Goal: {body.get('goal', '')}",
        f"Expected deliverable: {body.get('deliverable', '')}",
        "",
        "Use the router artifact for the complete bounded envelope. Return a concise result to Atlas via Kanban completion/artifacts; do not summon other Discord bots.",
    ])


def _new_kanban_task_id(conn: sqlite3.Connection) -> str:
    for _ in range(5):
        task_id = "t_" + "".join(random.choice("0123456789abcdef") for _ in range(8))
        if conn.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone() is None:
            return task_id
    raise RouterError("could not allocate unique Kanban task id")


def create_kanban_task_direct(
    *,
    title: str,
    assignee: str,
    body: str,
    idempotency_key: str,
    created_by: str = "router",
    kanban_db: str | os.PathLike[str] | None = None,
) -> str:
    """Create a Kanban task directly in SQLite.

    Router dispatch should not shell through Atlas' Hermes CLI: Atlas has a
    runtime guard that blocks direct Kanban creation, and Compose `run atlas`
    also contends with the live Atlas home bind mount. The router is the
    trusted control plane, so it writes the Kanban row itself and records the
    same minimal creation event the Hermes CLI emits.
    """
    kanban_path = Path(kanban_db) if kanban_db else DEFAULT_KANBAN_DB_PATH
    if not kanban_path.exists():
        raise RouterError(f"kanban db not found: {kanban_path}")
    now = int(time.time())
    with sqlite3.connect(kanban_path) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT id FROM tasks WHERE idempotency_key=? AND status!='archived' ORDER BY created_at DESC LIMIT 1",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return str(existing["id"])
        task_id = _new_kanban_task_id(conn)
        conn.execute(
            """
            INSERT INTO tasks (
                id, title, body, assignee, status, priority, created_by,
                created_at, workspace_kind, idempotency_key
            ) VALUES (?, ?, ?, ?, 'ready', 0, ?, ?, 'scratch', ?)
            """,
            (task_id, title.strip(), body, assignee, created_by, now, idempotency_key),
        )
        conn.execute(
            """
            INSERT INTO task_events (task_id, run_id, kind, payload, created_at)
            VALUES (?, NULL, 'created', ?, ?)
            """,
            (
                task_id,
                json.dumps({"assignee": assignee, "status": "ready", "parents": [], "tenant": None, "skills": None}),
                now,
            ),
        )
        return task_id


def dispatch_pending(
    db: str | os.PathLike[str] | None = None,
    max_messages: int = 1,
    dry_run: bool = False,
    run_cmd: Any = None,
) -> list[str]:
    if int(max_messages) < 1:
        raise RouterError("max_messages must be >= 1")
    init_db(db)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    use_command = run_cmd is not None
    run_cmd = run_cmd or subprocess.run
    dispatched: list[str] = []
    with connect_db(db) as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE status='pending' ORDER BY created_at, id LIMIT ?",
            (int(max_messages),),
        ).fetchall()
        for row in rows:
            if not dry_run:
                claimed = conn.execute(
                    "UPDATE messages SET status='dispatching', error=NULL WHERE id=? AND status='pending'",
                    (row["id"],),
                ).rowcount
                if claimed != 1:
                    continue
                row = conn.execute("SELECT * FROM messages WHERE id=?", (row["id"],)).fetchone()
            envelope = row_to_envelope(row)
            artifact_path = ARTIFACT_DIR / f"{row['id']}.json"
            artifact_path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
            event_payload: dict[str, Any] = {"artifact_path": str(artifact_path)}
            if dry_run:
                event_payload["dry_run"] = True
                _insert_event(conn, row["id"], "dispatch_dry_run", event_payload)
                dispatched.append(row["id"])
                continue

            title = f"[router:{row['id']}] {row['summary']}"
            body = build_kanban_body(envelope, artifact_path)
            idempotency_key = f"router:{row['id']}"
            try:
                if use_command:
                    cmd = COMPOSE_CMD + [
                        "run", "--rm", "-e", "TEAM_NEXUS_ROUTER_DISPATCH=1", "atlas", "kanban", "create", title,
                        "--assignee", row["recipient"],
                        "--body", body,
                        "--idempotency-key", idempotency_key,
                        "--json",
                    ]
                    event_payload["command"] = cmd
                    completed = run_cmd(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True, check=False)
                    output = (completed.stdout or "") + (completed.stderr or "")
                    event_payload["returncode"] = completed.returncode
                    event_payload["output"] = output
                    task_id = parse_kanban_task_id(output)
                    if completed.returncode != 0:
                        error = output.strip() or f"kanban command exited {completed.returncode}"
                        conn.execute(
                            "UPDATE messages SET status='pending', error=? WHERE id=?",
                            (error, row["id"]),
                        )
                        _insert_event(conn, row["id"], "kanban_failed", event_payload)
                        continue
                else:
                    task_id = create_kanban_task_direct(
                        title=title,
                        assignee=row["recipient"],
                        body=body,
                        idempotency_key=idempotency_key,
                    )
                    event_payload["direct_sql"] = True
            except Exception as exc:  # pragma: no cover - defensive
                error = str(exc)
                event_payload["error"] = error
                conn.execute(
                    "UPDATE messages SET status='pending', error=? WHERE id=?",
                    (error, row["id"]),
                )
                _insert_event(conn, row["id"], "kanban_failed", event_payload)
                continue
            conn.execute(
                "UPDATE messages SET status='dispatched', kanban_task_id=?, error=NULL WHERE id=?",
                (task_id, row["id"]),
            )
            _insert_event(conn, row["id"], "kanban_created", event_payload)
            dispatched.append(row["id"])
    return dispatched


def sync_completions(
    db: str | os.PathLike[str] | None = None,
    kanban_db: str | os.PathLike[str] | None = None,
) -> list[str]:
    """Sync completed/blocked/failed Kanban task outcomes back into router state."""
    init_db(db)
    kanban_path = Path(kanban_db) if kanban_db else DEFAULT_KANBAN_DB_PATH
    if not kanban_path.exists():
        raise RouterError(f"kanban db not found: {kanban_path}")

    synced: list[str] = []
    with connect_db(db) as router_conn, sqlite3.connect(kanban_path) as kanban_conn:
        kanban_conn.row_factory = sqlite3.Row
        rows = router_conn.execute(
            """
            SELECT id, kanban_task_id
            FROM messages
            WHERE status='dispatched' AND kanban_task_id IS NOT NULL
            ORDER BY created_at, id
            """
        ).fetchall()
        for row in rows:
            task = kanban_conn.execute(
                "SELECT id, status, assignee, title FROM tasks WHERE id=?",
                (row["kanban_task_id"],),
            ).fetchone()
            if task is None:
                continue
            run = kanban_conn.execute(
                """
                SELECT id, status, outcome, summary, error
                FROM task_runs
                WHERE task_id=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (row["kanban_task_id"],),
            ).fetchone()
            task_status = task["status"]
            run_summary = run["summary"] if run is not None and "summary" in run.keys() else None
            run_error = run["error"] if run is not None and "error" in run.keys() else None
            run_status = run["status"] if run is not None and "status" in run.keys() else None
            run_outcome = run["outcome"] if run is not None and "outcome" in run.keys() else None

            new_status: str | None = None
            error: str | None = None
            if task_status == "done" or run_outcome == "completed":
                new_status = "completed"
            elif task_status == "blocked" or run_outcome == "blocked" or run_status == "blocked":
                new_status = "blocked"
                error = run_summary or run_error or "kanban task blocked"
            elif task_status == "failed" or run_outcome == "failed" or run_status == "failed":
                new_status = "failed"
                error = run_error or run_summary or "kanban task failed"

            if new_status is None:
                continue

            payload = {
                "kanban_task_id": row["kanban_task_id"],
                "task_status": task_status,
                "task_assignee": task["assignee"],
                "task_title": task["title"],
                "run_status": run_status,
                "run_outcome": run_outcome,
                "run_summary": run_summary,
                "run_error": run_error,
            }
            router_conn.execute(
                "UPDATE messages SET status=?, error=? WHERE id=? AND status='dispatched'",
                (new_status, error, row["id"]),
            )
            _insert_event(router_conn, row["id"], "completion_synced", payload)
            synced.append(row["id"])
        update_conversation_states(router_conn)
    return synced


def update_conversation_states(conn: sqlite3.Connection) -> list[str]:
    """Refresh aggregate conversation rows and emit terminal conversation events."""
    changed: list[str] = []
    convs = conn.execute("SELECT id, status FROM conversations ORDER BY created_at, id").fetchall()
    for conv in convs:
        conv_id = conv["id"]
        previous = conv["status"]
        counts = _refresh_conversation_counts(conn, conv_id)
        expected = counts.get("expected", 0)
        terminal = counts.get("terminal", 0)
        if expected < 1 or terminal < expected or previous in {"completed", "needs_attention"}:
            continue
        blocked_or_failed = counts.get("blocked", 0) + counts.get("failed", 0)
        new_status = "needs_attention" if blocked_or_failed else "completed"
        event_kind = "conversation_needs_attention" if blocked_or_failed else "conversation_completed"
        now = now_iso()
        updated = conn.execute(
            "UPDATE conversations SET status=?, completed_at=COALESCE(completed_at, ?), updated_at=? WHERE id=? AND status NOT IN ('completed','needs_attention')",
            (new_status, now, now, conv_id),
        ).rowcount
        if updated:
            _insert_event(conn, _conversation_event_id(conv_id), event_kind, {"counts": counts})
            changed.append(conv_id)
    return changed


def _message_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {status: 0 for status in sorted(KNOWN_STATUSES)}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM messages GROUP BY status"):
        counts[row["status"]] = int(row["n"])
    counts["total"] = sum(v for k, v in counts.items() if k != "total")
    return counts


def _recent_messages(conn: sqlite3.Connection, limit: int = 10) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, conversation_id, sender, recipient, type, priority, ttl,
               created_at, summary, status, error, kanban_task_id
        FROM messages
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [dict(row) for row in rows]


def detect_direct_kanban_smells(kanban_conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Find likely multi-agent tasks that bypassed the router envelope."""
    worker_names = {"vega", "scout", "forge", "lumen", "blitz", "ledger", "sentinel"}
    smells: list[dict[str, Any]] = []
    rows = kanban_conn.execute(
        """
        SELECT id, title, assignee, status
        FROM tasks
        WHERE COALESCE(assignee, '') != 'atlas'
        ORDER BY id DESC
        LIMIT 100
        """
    ).fetchall()
    for row in rows:
        title = row["title"] or ""
        assignee = (row["assignee"] or "").lower()
        looks_multi_agent = (
            assignee in worker_names
            and (
                re.search(r"(?i)\b(introduction|introduce|all[- ]workers|team|specialist|standup)\b", title)
                or re.search(r"(?i)\b(vega|scout|forge|lumen|blitz|ledger|sentinel)\b", title)
            )
        )
        has_router_envelope = "[router:" in title or "router:" in title or "router-dispatched" in title.lower()
        if looks_multi_agent and not has_router_envelope:
            smells.append({
                "level": "warning",
                "kind": "direct_kanban_without_router",
                "message": "likely multi-agent Kanban task without router envelope/audit trail",
                "kanban_task_id": row["id"],
                "title": title,
                "assignee": row["assignee"],
                "status": row["status"],
            })
    return smells


def router_status(
    db: str | os.PathLike[str] | None = None,
    kanban_db: str | os.PathLike[str] | None = None,
    recent_limit: int = 10,
) -> dict[str, Any]:
    """Return a JSON-serializable router status snapshot."""
    init_db(db)
    router_path = db_path(db)
    kanban_path = Path(kanban_db) if kanban_db else DEFAULT_KANBAN_DB_PATH
    problems: list[dict[str, Any]] = []
    with connect_db(db) as conn:
        counts = _message_counts(conn)
        recent = _recent_messages(conn, recent_limit)
        missing_task_ids = [
            r["id"] for r in conn.execute(
                "SELECT id FROM messages WHERE status='dispatched' AND kanban_task_id IS NULL ORDER BY created_at, id"
            ).fetchall()
        ]
        if missing_task_ids:
            problems.append({
                "level": "warning",
                "kind": "missing_kanban_task_id",
                "message": "dispatched router messages missing kanban_task_id",
                "message_ids": missing_task_ids,
            })

        stale_sync: list[dict[str, Any]] = []
        if kanban_path.exists():
            with sqlite3.connect(kanban_path) as kconn:
                kconn.row_factory = sqlite3.Row
                problems.extend(detect_direct_kanban_smells(kconn))
                rows = conn.execute(
                    """
                    SELECT id, kanban_task_id FROM messages
                    WHERE status='dispatched' AND kanban_task_id IS NOT NULL
                    ORDER BY created_at, id
                    """
                ).fetchall()
                for row in rows:
                    task = kconn.execute("SELECT id, status FROM tasks WHERE id=?", (row["kanban_task_id"],)).fetchone()
                    if task is None:
                        problems.append({
                            "level": "warning",
                            "kind": "kanban_task_missing",
                            "message": "router message references a missing Kanban task",
                            "message_id": row["id"],
                            "kanban_task_id": row["kanban_task_id"],
                        })
                    elif task["status"] in {"done", "blocked", "failed"}:
                        stale_sync.append({
                            "message_id": row["id"],
                            "kanban_task_id": row["kanban_task_id"],
                            "task_status": task["status"],
                        })
        else:
            problems.append({
                "level": "warning",
                "kind": "kanban_db_missing",
                "message": f"kanban db not found: {kanban_path}",
            })
        if stale_sync:
            problems.append({
                "level": "warning",
                "kind": "sync_needed",
                "message": "Kanban outcomes are ready; run router-sync",
                "items": stale_sync,
            })
        event_count = conn.execute("SELECT COUNT(*) AS n FROM route_events").fetchone()["n"]
    return {
        "ok": not any(p.get("level") == "error" for p in problems),
        "generated_at": now_iso(),
        "router_db": str(router_path),
        "router_db_exists": router_path.exists(),
        "kanban_db": str(kanban_path),
        "kanban_db_exists": kanban_path.exists(),
        "counts": counts,
        "event_count": int(event_count),
        "recent": recent,
        "problems": problems,
    }


def router_doctor(
    db: str | os.PathLike[str] | None = None,
    kanban_db: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Return an operator-focused health report for router/Kanban linkage."""
    status = router_status(db, kanban_db, recent_limit=5)
    checks: list[dict[str, Any]] = []
    checks.append({"name": "router_db_exists", "ok": bool(status["router_db_exists"]), "detail": status["router_db"]})
    checks.append({"name": "kanban_db_exists", "ok": bool(status["kanban_db_exists"]), "detail": status["kanban_db"]})
    counts = status["counts"]
    checks.append({"name": "pending_queue_bounded", "ok": counts.get("pending", 0) <= 10, "detail": f"pending={counts.get('pending', 0)}"})
    checks.append({"name": "no_missing_kanban_task_ids", "ok": not any(p["kind"] == "missing_kanban_task_id" for p in status["problems"]), "detail": "dispatched messages should link to Kanban tasks"})
    checks.append({"name": "completion_sync_current", "ok": not any(p["kind"] == "sync_needed" for p in status["problems"]), "detail": "run make router-sync if false"})
    checks.append({"name": "no_direct_kanban_without_router", "ok": not any(p["kind"] == "direct_kanban_without_router" for p in status["problems"]), "detail": "multi-agent fanout should have router envelope evidence"})
    return {
        "ok": all(c["ok"] for c in checks),
        "generated_at": now_iso(),
        "checks": checks,
        "status": status,
    }


def router_conversation(
    db: str | os.PathLike[str] | None,
    conversation_id: str,
) -> dict[str, Any]:
    init_db(db)
    with connect_db(db) as conn:
        conv = conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at, id",
            (conversation_id,),
        ).fetchall()
        if not rows and conv is None:
            raise RouterError(f"conversation not found: {conversation_id}")
        if conv is None:
            _upsert_conversation(conn, conversation_id, rows[0]["summary"] if rows else conversation_id)
            _refresh_conversation_counts(conn, conversation_id)
            conv = conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        counts = _refresh_conversation_counts(conn, conversation_id)
        conv_events = conn.execute(
            "SELECT kind, payload_json, created_at FROM route_events WHERE message_id=? ORDER BY id",
            (_conversation_event_id(conversation_id),),
        ).fetchall()
        messages: list[dict[str, Any]] = []
        for row in rows:
            envelope = row_to_envelope(row)
            events = conn.execute(
                "SELECT kind, payload_json, created_at FROM route_events WHERE message_id=? ORDER BY id",
                (row["id"],),
            ).fetchall()
            envelope["events"] = [
                {"kind": e["kind"], "payload": json.loads(e["payload_json"]), "created_at": e["created_at"]}
                for e in events
            ]
            messages.append(envelope)
    return {
        "ok": True,
        "conversation_id": conversation_id,
        "id": conversation_id,
        "status": conv["status"],
        "summary": conv["summary"],
        "created_at": conv["created_at"],
        "updated_at": conv["updated_at"],
        "completed_at": conv["completed_at"],
        "expected_count": conv["expected_count"],
        "terminal_count": conv["terminal_count"],
        "report_task_id": conv["report_task_id"],
        "counts": counts,
        "events": [{"kind": e["kind"], "payload": json.loads(e["payload_json"]), "created_at": e["created_at"]} for e in conv_events],
        "message_count": len(messages),
        "messages": messages,
    }


def build_report_body(conversation: dict[str, Any], artifact_path: Path) -> str:
    lines = [
        "Router-supervised Team Nexus conversation is terminal.",
        "",
        f"Conversation: {conversation['conversation_id']}",
        f"Status: {conversation['status']}",
        f"Summary: {conversation.get('summary') or ''}",
        f"Router conversation artifact: {artifact_display_path(artifact_path)}",
        "",
        "Synthesize the worker outcomes for Sage. Cite router message IDs and Kanban task IDs. Do not claim a worker replied unless its message/task evidence is present.",
        "",
        "Messages:",
    ]
    for msg in conversation["messages"]:
        body = msg.get("body", {})
        lines.append(f"- {msg['id']} -> {msg['recipient']} status={msg['status']} kanban_task_id={msg.get('kanban_task_id') or 'none'} summary={msg.get('summary') or ''}")
        if msg.get("error"):
            lines.append(f"  error: {msg['error']}")
        if body.get("deliverable"):
            lines.append(f"  deliverable: {body['deliverable']}")
    return "\n".join(lines)


def create_report_tasks(
    db: str | os.PathLike[str] | None = None,
    max_conversations: int = 5,
    run_cmd: Any = None,
) -> list[str]:
    if int(max_conversations) < 1:
        raise RouterError("max_conversations must be >= 1")
    init_db(db)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    use_command = run_cmd is not None
    run_cmd = run_cmd or subprocess.run
    created: list[str] = []
    with connect_db(db) as conn:
        convs = conn.execute(
            """
            SELECT id FROM conversations
            WHERE status IN ('completed','needs_attention') AND report_task_id IS NULL
            ORDER BY completed_at, created_at, id
            LIMIT ?
            """,
            (int(max_conversations),),
        ).fetchall()
        for conv_row in convs:
            conv_id = conv_row["id"]
            conversation = router_conversation(db, conv_id)
            artifact_path = ARTIFACT_DIR / f"conversation-{conv_id}.json"
            artifact_path.write_text(json.dumps(conversation, indent=2, sort_keys=True) + "\n")
            title = f"[router-conversation:{conv_id}] Synthesize Team Nexus results"
            body = build_report_body(conversation, artifact_path)
            idempotency_key = f"router-conversation:{conv_id}:report"
            payload: dict[str, Any] = {"artifact_path": str(artifact_path)}
            try:
                if use_command:
                    cmd = COMPOSE_CMD + [
                        "run", "--rm", "-e", "TEAM_NEXUS_ROUTER_DISPATCH=1", "atlas", "kanban", "create", title,
                        "--assignee", "atlas",
                        "--body", body,
                        "--idempotency-key", idempotency_key,
                        "--json",
                    ]
                    payload["command"] = cmd
                    completed = run_cmd(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True, check=False)
                    output = (completed.stdout or "") + (completed.stderr or "")
                    payload["returncode"] = completed.returncode
                    payload["output"] = output
                    task_id = parse_kanban_task_id(output)
                    if completed.returncode != 0 or not task_id:
                        error = output.strip() or f"kanban command exited {completed.returncode}"
                        conn.execute("UPDATE conversations SET report_error=?, updated_at=? WHERE id=?", (error, now_iso(), conv_id))
                        _insert_event(conn, _conversation_event_id(conv_id), "report_task_failed", payload)
                        continue
                else:
                    task_id = create_kanban_task_direct(
                        title=title,
                        assignee="atlas",
                        body=body,
                        idempotency_key=idempotency_key,
                    )
                    payload["direct_sql"] = True
            except Exception as exc:  # pragma: no cover - defensive
                payload["error"] = str(exc)
                conn.execute("UPDATE conversations SET report_error=?, updated_at=? WHERE id=?", (str(exc), now_iso(), conv_id))
                _insert_event(conn, _conversation_event_id(conv_id), "report_task_failed", payload)
                continue
            conn.execute(
                "UPDATE conversations SET report_task_id=?, report_error=NULL, updated_at=? WHERE id=? AND report_task_id IS NULL",
                (task_id, now_iso(), conv_id),
            )
            _insert_event(conn, _conversation_event_id(conv_id), "report_task_created", {**payload, "kanban_task_id": task_id})
            created.append(conv_id)
    return created


def supervisor_pass(
    db: str | os.PathLike[str] | None = None,
    kanban_db: str | os.PathLike[str] | None = None,
    max_messages: int = 5,
    create_reports: bool = False,
    run_cmd: Any = None,
) -> dict[str, list[str]]:
    dispatched = dispatch_pending(db, max_messages=max_messages, run_cmd=run_cmd)
    synced = sync_completions(db, kanban_db)
    report_conversations = create_report_tasks(db, max_conversations=max_messages, run_cmd=run_cmd) if create_reports else []
    return {"dispatched": dispatched, "synced": synced, "report_conversations": report_conversations}


def run_supervisor(
    db: str | os.PathLike[str] | None = None,
    kanban_db: str | os.PathLike[str] | None = None,
    interval: int = 30,
    max_messages: int = 5,
    create_reports: bool = False,
    once: bool = False,
    run_cmd: Any = None,
) -> None:
    import time
    if int(interval) < 1:
        raise RouterError("interval must be >= 1")
    while True:
        print_json(supervisor_pass(db, kanban_db, max_messages, create_reports, run_cmd))
        if once:
            return
        time.sleep(int(interval))


def print_json(payload: dict[str, Any], out: Any = None) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True), file=out or sys.stdout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Team Nexus message router")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.add_argument("--db")

    p = sub.add_parser("send")
    p.add_argument("--db")
    p.add_argument("--from", dest="sender", required=True)
    p.add_argument("--to", dest="recipient", required=True)
    p.add_argument("--type", dest="msg_type", default="task.request")
    p.add_argument("--summary", required=True)
    p.add_argument("--goal", required=True)
    p.add_argument("--deliverable", required=True)
    p.add_argument("--conversation-id")
    p.add_argument("--parent-id")
    p.add_argument("--priority", default="normal")
    p.add_argument("--ttl", type=int)
    p.add_argument("--requires-response", type=parse_bool, default=True)
    p.add_argument("--allow-wide-fanout", action="store_true")

    p = sub.add_parser("list")
    p.add_argument("--db")
    p.add_argument("--status")

    p = sub.add_parser("inspect")
    p.add_argument("--db")
    p.add_argument("message_id")

    p = sub.add_parser("dispatch-pending")
    p.add_argument("--db")
    p.add_argument("--max", type=int, default=1, dest="max_messages")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("sync-completions")
    p.add_argument("--db")
    p.add_argument("--kanban-db")

    p = sub.add_parser("status")
    p.add_argument("--db")
    p.add_argument("--kanban-db")
    p.add_argument("--recent-limit", type=int, default=10)

    p = sub.add_parser("doctor")
    p.add_argument("--db")
    p.add_argument("--kanban-db")

    p = sub.add_parser("conversation")
    p.add_argument("--db")
    p.add_argument("conversation_id")

    p = sub.add_parser("create-report-tasks")
    p.add_argument("--db")
    p.add_argument("--max", type=int, default=5, dest="max_conversations")

    p = sub.add_parser("supervise")
    p.add_argument("--db")
    p.add_argument("--kanban-db")
    p.add_argument("--interval", type=int, default=30)
    p.add_argument("--max", type=int, default=5, dest="max_messages")
    p.add_argument("--create-report-tasks", action="store_true")
    p.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init_db(args.db)
            print(f"router db initialized: {db_path(args.db)}")
        elif args.command == "send":
            ids = send_messages(
                args.db, args.sender, args.recipient, args.msg_type, args.summary, args.goal, args.deliverable,
                args.conversation_id, args.parent_id, args.priority, args.ttl, args.requires_response, args.allow_wide_fanout,
            )
            for mid in ids:
                print(mid)
        elif args.command == "list":
            list_messages(args.db, args.status)
        elif args.command == "inspect":
            inspect_message(args.db, args.message_id)
        elif args.command == "dispatch-pending":
            ids = dispatch_pending(args.db, args.max_messages, args.dry_run)
            for mid in ids:
                print(mid)
        elif args.command == "sync-completions":
            ids = sync_completions(args.db, args.kanban_db)
            for mid in ids:
                print(mid)
        elif args.command == "status":
            print_json(router_status(args.db, args.kanban_db, args.recent_limit))
        elif args.command == "doctor":
            print_json(router_doctor(args.db, args.kanban_db))
        elif args.command == "conversation":
            print_json(router_conversation(args.db, args.conversation_id))
        elif args.command == "create-report-tasks":
            ids = create_report_tasks(args.db, args.max_conversations)
            for conv_id in ids:
                print(conv_id)
        elif args.command == "supervise":
            if args.once:
                print_json(supervisor_pass(args.db, args.kanban_db, args.max_messages, args.create_report_tasks))
            else:
                run_supervisor(args.db, args.kanban_db, args.interval, args.max_messages, args.create_report_tasks)
        return 0
    except (RouterError, sqlite3.Error, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
