#!/usr/bin/env python3
"""Compose-aware Team Nexus Kanban dispatcher.

This dispatcher bridges Hermes Kanban tasks whose assignees are Team Nexus
agent slugs (forge, vega, etc.) to the matching Docker Compose service.

It intentionally dispatches through scripts/kanban-dispatch-compose.sh instead
of Hermes' built-in profile dispatcher because Team Nexus uses one container and
one HERMES_HOME per agent, not one shared Hermes profile tree.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from typing import Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
KANBAN_DB = REPO_ROOT / "shared" / "kanban" / "kanban.db"
REGISTRY = REPO_ROOT / "shared" / "team-agents.yaml"
DISPATCH_SCRIPT = REPO_ROOT / "scripts" / "kanban-dispatch-compose.sh"
DEFAULT_LOG = REPO_ROOT / "shared" / "kanban" / "dispatcher.log"
DEFAULT_CLAIM_TTL_SECONDS = 15 * 60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch ready Team Nexus Kanban tasks to Compose services")
    parser.add_argument("--db", default=str(KANBAN_DB), help="Path to kanban.db")
    parser.add_argument("--registry", default=str(REGISTRY), help="Path to shared/team-agents.yaml")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="Dispatcher log path")
    parser.add_argument("--max-tasks", type=int, default=1, help="Maximum tasks to dispatch per pass")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between daemon passes")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be dispatched")
    parser.add_argument("--include-atlas", action="store_true", help="Also dispatch tasks assigned to atlas")
    return parser.parse_args()


def log(path: Path, message: str) -> None:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"{timestamp} {message}"
    print(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_agents(registry: Path) -> Dict[str, str]:
    """Parse the simple shared/team-agents.yaml structure without PyYAML."""
    if not registry.exists():
        raise SystemExit(f"missing registry: {registry}")
    agents: Dict[str, str] = {}
    current = None
    for raw in registry.read_text(encoding="utf-8").splitlines():
        if raw.startswith("  ") and raw.endswith(":") and not raw.startswith("    "):
            current = raw.strip()[:-1]
            agents[current] = current
        elif current and raw.startswith("    service:"):
            agents[current] = raw.split(":", 1)[1].strip()
    return agents


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def append_event(conn: sqlite3.Connection, task_id: str, kind: str, payload: dict, *, run_id: Optional[int] = None) -> None:
    conn.execute(
        "INSERT INTO task_events(task_id, kind, payload, created_at, run_id) VALUES (?, ?, ?, ?, ?)",
        (task_id, kind, json.dumps(payload), int(time.time()), run_id),
    )


def promotable_todo_ids(conn: sqlite3.Connection) -> List[str]:
    """Return todo tasks whose parents are all done."""
    rows = conn.execute(
        """
        SELECT t.id
          FROM tasks t
         WHERE t.status = 'todo'
           AND NOT EXISTS (
             SELECT 1
               FROM task_links l
               JOIN tasks p ON p.id = l.parent_id
              WHERE l.child_id = t.id
                AND p.status != 'done'
           )
        """
    ).fetchall()
    return [task_id for (task_id,) in rows]


def promote_unblocked_todo(conn: sqlite3.Connection) -> int:
    """Promote todo tasks whose parents are all done to ready.

    Hermes normally does this inside its dispatcher pass. The Compose dispatcher
    does the small dependency promotion locally so parent/child graphs still move
    without invoking the profile-based built-in dispatcher.
    """
    now = int(time.time())
    task_ids = promotable_todo_ids(conn)
    for task_id in task_ids:
        conn.execute("UPDATE tasks SET status = 'ready' WHERE id = ? AND status = 'todo'", (task_id,))
        conn.execute(
            "INSERT INTO task_events(task_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
            (task_id, "promoted", json.dumps({"by": "team-nexus-compose-dispatcher"}), now),
        )
    conn.commit()
    return len(task_ids)


def ready_tasks(conn: sqlite3.Connection, known_agents: Iterable[str], include_atlas: bool, limit: int) -> List[Tuple[str, str, str]]:
    agents = list(known_agents)
    if not include_atlas:
        agents = [a for a in agents if a != "atlas"]
    if not agents:
        return []
    placeholders = ",".join("?" for _ in agents)
    return conn.execute(
        f"""
        SELECT id, assignee, title
          FROM tasks
         WHERE status = 'ready'
           AND assignee IN ({placeholders})
         ORDER BY priority DESC, created_at ASC
         LIMIT ?
        """,
        [*agents, limit],
    ).fetchall()


def claim_for_dispatch(conn: sqlite3.Connection, task_id: str, assignee: str) -> Optional[Tuple[str, int]]:
    """Atomically claim a ready task so it is visible as running before spawn.

    Hermes' profile dispatcher uses hermes_cli.kanban_db.claim_task(). Team Nexus
    cannot use that dispatcher directly because assignees are Compose services, so
    this mirrors the same ready -> running state transition locally against the
    shared SQLite board before launching the worker container.
    """
    now = int(time.time())
    expires = now + DEFAULT_CLAIM_TTL_SECONDS
    lock = f"team-nexus-compose-dispatcher:{os.getpid()}:{task_id}"
    cur = conn.execute(
        """
        UPDATE tasks
           SET status        = 'running',
               claim_lock    = ?,
               claim_expires = ?,
               started_at    = COALESCE(started_at, ?)
         WHERE id = ?
           AND status = 'ready'
           AND claim_lock IS NULL
        """,
        (lock, expires, now, task_id),
    )
    if cur.rowcount != 1:
        conn.rollback()
        return None

    task_cols = table_columns(conn, "tasks")
    run_cols = table_columns(conn, "task_runs")
    select_cols = ["assignee"]
    if "current_step_key" in task_cols:
        select_cols.append("current_step_key")
    if "max_runtime_seconds" in task_cols:
        select_cols.append("max_runtime_seconds")
    trow = conn.execute(f"SELECT {', '.join(select_cols)} FROM tasks WHERE id = ?", (task_id,)).fetchone()
    task_values = dict(zip(select_cols, trow or []))

    insert_cols = ["task_id", "profile", "status", "started_at"]
    values: List[object] = [task_id, task_values.get("assignee") or assignee, "running", now]
    optional_values = {
        "step_key": task_values.get("current_step_key"),
        "claim_lock": lock,
        "claim_expires": expires,
        "max_runtime_seconds": task_values.get("max_runtime_seconds"),
    }
    for col, value in optional_values.items():
        if col in run_cols:
            insert_cols.append(col)
            values.append(value)
    placeholders = ", ".join("?" for _ in insert_cols)
    run_cur = conn.execute(f"INSERT INTO task_runs ({', '.join(insert_cols)}) VALUES ({placeholders})", values)
    run_id = int(run_cur.lastrowid)
    conn.execute("UPDATE tasks SET current_run_id = ? WHERE id = ?", (run_id, task_id))
    append_event(
        conn,
        task_id,
        "claimed",
        {"lock": lock, "expires": expires, "run_id": run_id, "by": "team-nexus-compose-dispatcher"},
        run_id=run_id,
    )
    conn.commit()
    return lock, run_id


def requeue_failed_spawn(conn: sqlite3.Connection, task_id: str, claim_lock: str, run_id: int, exit_code: int) -> bool:
    """Release the dispatcher-created claim if the worker container fails.

    The task returns to ready for a later retry. The failed run row and
    dispatch_failed event preserve why the running state was abandoned.
    """
    now = int(time.time())
    cur = conn.execute(
        """
        UPDATE tasks
           SET status = 'ready',
               claim_lock = NULL,
               claim_expires = NULL,
               worker_pid = NULL,
               current_run_id = NULL
         WHERE id = ?
           AND status = 'running'
           AND claim_lock = ?
        """,
        (task_id, claim_lock),
    )
    if cur.rowcount != 1:
        conn.rollback()
        return False
    run_cols = table_columns(conn, "task_runs")
    assignments = ["status = ?", "outcome = ?", "ended_at = ?"]
    values: List[object] = ["failed", "spawn_failed", now]
    if "error" in run_cols:
        assignments.append("error = ?")
        values.append(f"Compose dispatch exited with code {exit_code}")
    values.append(run_id)
    conn.execute(f"UPDATE task_runs SET {', '.join(assignments)} WHERE id = ?", values)
    append_event(conn, task_id, "dispatch_failed", {"exit_code": exit_code, "requeued": True}, run_id=run_id)
    conn.commit()
    return True


def dispatch(task_id: str, assignee: str, dry_run: bool, log_path: Path) -> int:
    if dry_run:
        log(log_path, f"dry-run dispatch assignee={assignee} task={task_id}")
        return 0
    log(log_path, f"dispatch start assignee={assignee} task={task_id}")
    proc = subprocess.run([str(DISPATCH_SCRIPT), assignee, task_id], cwd=str(REPO_ROOT))
    log(log_path, f"dispatch end assignee={assignee} task={task_id} exit_code={proc.returncode}")
    return proc.returncode


def run_pass(args: argparse.Namespace, agents: Dict[str, str], log_path: Path) -> int:
    db = Path(args.db)
    if not db.exists():
        raise SystemExit(f"missing Kanban DB: {db}; run `make kanban-init` first")
    with sqlite3.connect(db) as conn:
        if args.dry_run:
            promotable = promotable_todo_ids(conn)
            if promotable:
                log(log_path, f"dry-run would promote {len(promotable)} unblocked todo task(s) to ready")
        else:
            promoted = promote_unblocked_todo(conn)
            if promoted:
                log(log_path, f"promoted {promoted} unblocked todo task(s) to ready")
        tasks = ready_tasks(conn, agents.keys(), args.include_atlas, args.max_tasks)
    if not tasks:
        log(log_path, "no ready Compose-dispatchable tasks")
        return 0
    exit_code = 0
    for task_id, assignee, title in tasks:
        log(log_path, f"selected task={task_id} assignee={assignee} title={title!r}")
        if args.dry_run:
            log(log_path, f"dry-run would claim and dispatch assignee={assignee} task={task_id}")
            continue

        with sqlite3.connect(db) as conn:
            claim = claim_for_dispatch(conn, task_id, assignee)
        if claim is None:
            code = 1
            log(log_path, f"dispatch skipped task={task_id}; task could not be claimed")
            exit_code = code
            if not args.daemon:
                break
            continue

        log(log_path, f"claimed task={task_id} assignee={assignee} run_id={claim[1]}")
        code = dispatch(task_id, assignee, args.dry_run, log_path)
        with sqlite3.connect(db) as conn:
            row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            status = row[0] if row else "missing"
            if code != 0 and status == "running":
                if requeue_failed_spawn(conn, task_id, claim[0], claim[1], code):
                    status = "ready"
                    log(log_path, f"dispatch failed for task={task_id}; requeued from running to ready")
                else:
                    log(log_path, f"dispatch failed for task={task_id}; claim already changed, status={status}")
            elif status == "ready":
                log(log_path, f"dispatch failed to advance task={task_id}; status is still ready")
                code = code or 1
        if code != 0:
            exit_code = code
            if not args.daemon:
                break
    return exit_code


def main() -> int:
    args = parse_args()
    log_path = Path(args.log)
    agents = load_agents(Path(args.registry))
    if not DISPATCH_SCRIPT.exists():
        raise SystemExit(f"missing dispatch script: {DISPATCH_SCRIPT}")
    while True:
        code = run_pass(args, agents, log_path)
        if not args.daemon:
            return code
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
