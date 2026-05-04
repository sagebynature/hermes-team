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
from typing import Dict, Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
KANBAN_DB = REPO_ROOT / "shared" / "kanban" / "kanban.db"
REGISTRY = REPO_ROOT / "shared" / "team-agents.yaml"
DISPATCH_SCRIPT = REPO_ROOT / "scripts" / "kanban-dispatch-compose.sh"
DEFAULT_LOG = REPO_ROOT / "shared" / "kanban" / "dispatcher.log"


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
        code = dispatch(task_id, assignee, args.dry_run, log_path)
        if not args.dry_run:
            with sqlite3.connect(db) as conn:
                row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            status = row[0] if row else "missing"
            if status == "ready":
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
