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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "shared" / "router" / "messages.db"
DEFAULT_POLICY_PATH = REPO_ROOT / "shared" / "router" / "router-policy.yaml"
DEFAULT_AGENTS_PATH = REPO_ROOT / "shared" / "team-agents.yaml"
ARTIFACT_DIR = REPO_ROOT / "shared" / "project" / "artifacts" / "router"
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
            CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_route_events_message_id ON route_events(message_id);
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
    init_db(db)
    ids: list[str] = []
    created = now_iso()
    with connect_db(db) as conn:
        for rec in recipients:
            mid = new_message_id()
            ids.append(mid)
            conv = conversation_id or mid
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
            cmd = COMPOSE_CMD + [
                "run", "--rm", "atlas", "kanban", "create", title,
                "--assignee", row["recipient"],
                "--body", body,
                "--idempotency-key", f"router:{row['id']}",
                "--json",
            ]
            event_payload["command"] = cmd
            try:
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
        return 0
    except (RouterError, sqlite3.Error, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
