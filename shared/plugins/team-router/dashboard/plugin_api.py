"""Team Nexus Router dashboard plugin API.

Read-only dashboard endpoints for the structured Atlas-first router. The plugin
intentionally avoids mutation endpoints; operators should still use the checked
CLI/Make targets for send/dispatch/sync operations.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

ROUTER_DB = Path(os.environ.get("TEAM_NEXUS_ROUTER_DB", "/shared/router/messages.db"))
KANBAN_DB = Path(os.environ.get("TEAM_NEXUS_KANBAN_DB", "/shared/kanban/kanban.db"))
KNOWN_STATUSES = {"pending", "dispatching", "dispatched", "blocked", "failed", "completed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _require_router_db() -> None:
    if not ROUTER_DB.exists():
        raise HTTPException(status_code=404, detail=f"router db not found: {ROUTER_DB}")


def _json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {status: 0 for status in sorted(KNOWN_STATUSES)}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM messages GROUP BY status"):
        counts[row["status"]] = int(row["n"])
    counts["total"] = sum(v for k, v in counts.items() if k != "total")
    return counts


def _recent(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
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
    return [dict(r) for r in rows]


def _problems(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    missing = [
        r["id"] for r in conn.execute(
            "SELECT id FROM messages WHERE status='dispatched' AND kanban_task_id IS NULL ORDER BY created_at, id"
        ).fetchall()
    ]
    if missing:
        problems.append({
            "level": "warning",
            "kind": "missing_kanban_task_id",
            "message": "dispatched router messages missing kanban_task_id",
            "message_ids": missing,
        })
    if not KANBAN_DB.exists():
        problems.append({"level": "warning", "kind": "kanban_db_missing", "message": f"kanban db not found: {KANBAN_DB}"})
        return problems
    stale: list[dict[str, Any]] = []
    with _connect(KANBAN_DB) as kconn:
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
                stale.append({"message_id": row["id"], "kanban_task_id": row["kanban_task_id"], "task_status": task["status"]})
    if stale:
        problems.append({"level": "warning", "kind": "sync_needed", "message": "Kanban outcomes are ready; run router-sync", "items": stale})
    return problems


def _message_payload(row: sqlite3.Row, events: list[sqlite3.Row] | None = None) -> dict[str, Any]:
    payload = {
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
        "body": _json(row["body_json"], {}),
        "artifacts": _json(row["artifacts_json"], []),
        "trace": _json(row["trace_json"], []),
        "status": row["status"],
        "error": row["error"],
        "kanban_task_id": row["kanban_task_id"],
    }
    if events is not None:
        payload["events"] = [
            {"kind": e["kind"], "payload": _json(e["payload_json"], {}), "created_at": e["created_at"]}
            for e in events
        ]
    return payload


@router.get("/status")
def status(recent_limit: int = Query(10, ge=0, le=100)) -> dict[str, Any]:
    _require_router_db()
    with _connect(ROUTER_DB) as conn:
        problems = _problems(conn)
        event_count = conn.execute("SELECT COUNT(*) AS n FROM route_events").fetchone()["n"]
        return {
            "ok": not any(p.get("level") == "error" for p in problems),
            "generated_at": now_iso(),
            "router_db_exists": ROUTER_DB.exists(),
            "router_db": str(ROUTER_DB),
            "kanban_db_exists": KANBAN_DB.exists(),
            "kanban_db": str(KANBAN_DB),
            "counts": _counts(conn),
            "event_count": int(event_count),
            "recent": _recent(conn, recent_limit),
            "problems": problems,
        }


@router.get("/doctor")
def doctor() -> dict[str, Any]:
    snapshot = status(recent_limit=5)
    counts = snapshot["counts"]
    checks = [
        {"name": "router_db_exists", "ok": bool(snapshot["router_db_exists"]), "detail": snapshot["router_db"]},
        {"name": "kanban_db_exists", "ok": bool(snapshot["kanban_db_exists"]), "detail": snapshot["kanban_db"]},
        {"name": "pending_queue_bounded", "ok": counts.get("pending", 0) <= 10, "detail": f"pending={counts.get('pending', 0)}"},
        {"name": "no_missing_kanban_task_ids", "ok": not any(p["kind"] == "missing_kanban_task_id" for p in snapshot["problems"]), "detail": "dispatched messages should link to Kanban tasks"},
        {"name": "completion_sync_current", "ok": not any(p["kind"] == "sync_needed" for p in snapshot["problems"]), "detail": "run make router-sync if false"},
    ]
    return {"ok": all(c["ok"] for c in checks), "generated_at": now_iso(), "checks": checks, "status": snapshot}


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str) -> dict[str, Any]:
    _require_router_db()
    with _connect(ROUTER_DB) as conn:
        rows = conn.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at, id", (conversation_id,)).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"conversation not found: {conversation_id}")
        messages = []
        for row in rows:
            events = conn.execute("SELECT kind, payload_json, created_at FROM route_events WHERE message_id=? ORDER BY id", (row["id"],)).fetchall()
            messages.append(_message_payload(row, events))
    return {"ok": True, "conversation_id": conversation_id, "message_count": len(messages), "messages": messages}
