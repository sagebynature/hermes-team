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
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
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
DEFAULT_WORKER_TIMEOUT_SECONDS = 15 * 60
DISPATCH_TIMEOUT_EXIT_CODE = 124
DIRECT_REPLY_MODE_RE = re.compile(r"^\s*reply_mode\s*[:=]\s*direct_discord\s*$", re.IGNORECASE | re.MULTILINE)
REPLY_TARGET_RE = re.compile(r"^\s*reply_target\s*[:=]\s*(discord:[^\s]+)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch ready Team Nexus Kanban tasks to Compose services")
    parser.add_argument("--db", default=str(KANBAN_DB), help="Path to kanban.db")
    parser.add_argument("--registry", default=str(REGISTRY), help="Path to shared/team-agents.yaml")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="Dispatcher log path")
    parser.add_argument("--max-tasks", type=int, default=1, help="Maximum tasks to claim and dispatch concurrently per pass")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between daemon passes")
    parser.add_argument(
        "--worker-timeout",
        type=int,
        default=int(os.environ.get("KANBAN_DISPATCH_WORKER_TIMEOUT", DEFAULT_WORKER_TIMEOUT_SECONDS)),
        help="Seconds before a worker dispatch is killed and the task is blocked; use 0 to disable",
    )
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


def task_body(conn: sqlite3.Connection, task_id: str) -> str:
    cols = table_columns(conn, "tasks")
    if "body" not in cols:
        return ""
    row = conn.execute("SELECT body FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row or row[0] is None:
        return ""
    return str(row[0])


def direct_reply_target(body: str) -> Optional[str]:
    match = REPLY_TARGET_RE.search(body or "")
    return match.group(1).strip() if match else None


def task_requires_direct_discord_reply(conn: sqlite3.Connection, task_id: str) -> bool:
    """Return True only for tasks explicitly allowed to send public Discord replies.

    This keeps `messaging` out of ordinary worker fan-out runs. Atlas synthesis
    tasks and deliberate direct-specialist tasks receive the messaging tool only
    when their task body carries both the reply mode and an explicit Discord
    target, e.g. `reply_mode: direct_discord` and
    `reply_target: discord:<channel-or-thread>`.
    """
    body = task_body(conn, task_id)
    if not body:
        return False
    return bool(DIRECT_REPLY_MODE_RE.search(body) and direct_reply_target(body))


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


def block_incomplete_dispatch(conn: sqlite3.Connection, task_id: str, claim_lock: str, run_id: int) -> bool:
    """Block a task when the worker exited cleanly but never completed/blocked it.

    Some agent failures still exit with code 0 because the final assistant response
    described a blocker instead of calling kanban_block/kanban_complete. Leaving the
    dispatcher-created claim in `running` hides the task from future passes forever,
    so convert it to an operator-visible blocked task with durable evidence.
    """
    now = int(time.time())
    summary = "Worker exited with code 0 but left the task running; task blocked for operator review."
    cur = conn.execute(
        """
        UPDATE tasks
           SET status = 'blocked',
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
    values: List[object] = ["blocked", "incomplete", now]
    if "summary" in run_cols:
        assignments.append("summary = ?")
        values.append(summary)
    if "error" in run_cols:
        assignments.append("error = ?")
        values.append(summary)
    values.append(run_id)
    conn.execute(f"UPDATE task_runs SET {', '.join(assignments)} WHERE id = ?", values)
    append_event(conn, task_id, "dispatch_incomplete", {"blocked": True, "exit_code": 0}, run_id=run_id)
    conn.commit()
    return True


def block_timed_out_dispatch(conn: sqlite3.Connection, task_id: str, claim_lock: str, run_id: int, worker_timeout: int) -> bool:
    """Stop retrying a worker that exceeded its runtime budget.

    Timeouts usually mean the worker is stuck in an agent/model/tool loop or a
    task is too broad. Re-queueing immediately would recreate the same loop, so
    leave the task blocked for an operator to inspect or split into smaller work.
    """
    now = int(time.time())
    summary = f"Worker dispatch timed out after {worker_timeout} seconds; task blocked for operator review."
    cur = conn.execute(
        """
        UPDATE tasks
           SET status = 'blocked',
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
    values: List[object] = ["blocked", "timed_out", now]
    if "summary" in run_cols:
        assignments.append("summary = ?")
        values.append(summary)
    if "error" in run_cols:
        assignments.append("error = ?")
        values.append(summary)
    values.append(run_id)
    conn.execute(f"UPDATE task_runs SET {', '.join(assignments)} WHERE id = ?", values)
    append_event(
        conn,
        task_id,
        "dispatch_timed_out",
        {"timeout_seconds": worker_timeout, "blocked": True},
        run_id=run_id,
    )
    conn.commit()
    return True


def dispatch_container_name(task_id: str, assignee: str) -> str:
    safe_task = "".join(ch if ch.isalnum() or ch in "_.-" else "-" for ch in task_id)
    safe_assignee = "".join(ch if ch.isalnum() or ch in "_.-" else "-" for ch in assignee)
    return f"team-nexus-{safe_assignee}-task-{safe_task}"


def cleanup_timed_out_container(task_id: str, assignee: str, log_path: Path) -> None:
    name = dispatch_container_name(task_id, assignee)
    try:
        subprocess.run(["docker", "rm", "-f", name], cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(log_path, f"timeout cleanup attempted container={name}")
    except Exception as exc:  # pragma: no cover - defensive logging only
        log(log_path, f"timeout cleanup failed container={name} error={exc}")


def dispatch(task_id: str, assignee: str, dry_run: bool, log_path: Path, worker_timeout: int, direct_reply: bool = False) -> int:
    if dry_run:
        suffix = " direct_reply=true" if direct_reply else ""
        log(log_path, f"dry-run dispatch assignee={assignee} task={task_id}{suffix}")
        return 0
    suffix = " direct_reply=true" if direct_reply else ""
    log(log_path, f"dispatch start assignee={assignee} task={task_id}{suffix}")
    timeout = worker_timeout if worker_timeout and worker_timeout > 0 else None
    cmd = [str(DISPATCH_SCRIPT), assignee, task_id]
    if direct_reply:
        cmd.append("--direct-reply")
    try:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), timeout=timeout)
    except subprocess.TimeoutExpired:
        log(log_path, f"dispatch timed out assignee={assignee} task={task_id} timeout_seconds={worker_timeout}")
        cleanup_timed_out_container(task_id, assignee, log_path)
        return DISPATCH_TIMEOUT_EXIT_CODE
    log(log_path, f"dispatch end assignee={assignee} task={task_id} exit_code={proc.returncode}")
    return proc.returncode


def _latest_run_metadata(conn: sqlite3.Connection, run_id: int) -> dict:
    row = conn.execute("SELECT metadata FROM task_runs WHERE id = ?", (run_id,)).fetchone()
    if not row or not row[0]:
        return {}
    try:
        parsed = json.loads(row[0])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _direct_reply_has_verified_message(metadata: dict) -> bool:
    return bool(metadata.get("discord_message_id") or metadata.get("message_id"))


def _discord_thread_from_reply_target(target: str) -> Optional[str]:
    if not target.startswith("discord:"):
        return None
    parts = target.split(":")
    if len(parts) == 2:
        return parts[1]
    if len(parts) >= 3:
        return parts[-1]
    return None


def _deliver_direct_reply_fallback(conn: sqlite3.Connection, task_id: str, run_id: int, log_path: Path) -> bool:
    """Post task.result into the reply thread when the agent claimed but did not prove delivery.

    This is a deterministic safety net for direct-reply tasks. The preferred path
    is still an agent `send_message` call with returned message_id in run
    metadata. If the model records `discord_reply_sent` without a message_id, use
    the existing Discord webhook sender to deliver the already-computed result to
    the explicit task reply_target, then record durable evidence.
    """
    task_cols = table_columns(conn, "tasks")
    select_cols = ["body"]
    if "result" in task_cols:
        select_cols.append("result")
    row = conn.execute(f"SELECT {', '.join(select_cols)} FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return False
    values = dict(zip(select_cols, row))
    target = direct_reply_target(str(values.get("body") or ""))
    thread_id = _discord_thread_from_reply_target(target or "")
    result = str(values.get("result") or "").strip()
    if not thread_id or not result:
        append_event(
            conn,
            task_id,
            "direct_reply_unverified",
            {"fallback_sent": False, "reason": "missing_thread_or_result", "reply_target": target},
            run_id=run_id,
        )
        conn.commit()
        return False
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "discord-post-status.py"), "--thread-id", thread_id, "--message", result],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    if proc.returncode == 0:
        metadata = _latest_run_metadata(conn, run_id)
        metadata.update(
            {
                "discord_reply_sent": True,
                "reply_target": target,
                "direct_reply_fallback": "discord_webhook",
            }
        )
        conn.execute("UPDATE task_runs SET metadata = ? WHERE id = ?", (json.dumps(metadata), run_id))
        append_event(conn, task_id, "direct_reply_fallback_sent", {"reply_target": target}, run_id=run_id)
        conn.commit()
        log(log_path, f"direct reply fallback sent task={task_id} target={target}")
        return True
    append_event(
        conn,
        task_id,
        "direct_reply_unverified",
        {"fallback_sent": False, "reply_target": target, "exit_code": proc.returncode, "stderr": proc.stderr[-500:]},
        run_id=run_id,
    )
    conn.commit()
    log(log_path, f"direct reply unverified task={task_id}; fallback failed exit_code={proc.returncode}")
    return False


def finalize_dispatch_result(
    db: Path,
    task_id: str,
    assignee: str,
    claim: Tuple[str, int],
    code: int,
    log_path: Path,
    worker_timeout: int,
    direct_reply: bool = False,
) -> int:
    """Reconcile task/run state after a worker container exits."""
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        status = row[0] if row else "missing"
        if code == DISPATCH_TIMEOUT_EXIT_CODE and status == "running":
            if block_timed_out_dispatch(conn, task_id, claim[0], claim[1], worker_timeout):
                status = "blocked"
                log(log_path, f"dispatch timed out for task={task_id}; blocked for operator review")
            else:
                log(log_path, f"dispatch timed out for task={task_id}; claim already changed, status={status}")
        elif code != 0 and status == "running":
            if requeue_failed_spawn(conn, task_id, claim[0], claim[1], code):
                status = "ready"
                log(log_path, f"dispatch failed for task={task_id}; requeued from running to ready")
            else:
                log(log_path, f"dispatch failed for task={task_id}; claim already changed, status={status}")
        elif code == 0 and status == "running":
            if block_incomplete_dispatch(conn, task_id, claim[0], claim[1]):
                status = "blocked"
                code = 1
                log(log_path, f"dispatch incomplete for task={task_id}; blocked because worker exited without completing")
            else:
                log(log_path, f"dispatch incomplete for task={task_id}; claim already changed, status={status}")
        elif status == "ready":
            log(log_path, f"dispatch failed to advance task={task_id}; status is still ready")
            code = code or 1
        if direct_reply and code == 0 and status == "done":
            metadata = _latest_run_metadata(conn, claim[1])
            if not _direct_reply_has_verified_message(metadata):
                _deliver_direct_reply_fallback(conn, task_id, claim[1], log_path)
    return code


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
    dispatch_jobs: List[Tuple[str, str, Tuple[str, int], bool]] = []
    for task_id, assignee, title in tasks:
        log(log_path, f"selected task={task_id} assignee={assignee} title={title!r}")
        if args.dry_run:
            log(log_path, f"dry-run would claim and dispatch assignee={assignee} task={task_id}")
            continue

        with sqlite3.connect(db) as conn:
            claim = claim_for_dispatch(conn, task_id, assignee)
            direct_reply = task_requires_direct_discord_reply(conn, task_id) if claim is not None else False
        if claim is None:
            code = 1
            log(log_path, f"dispatch skipped task={task_id}; task could not be claimed")
            exit_code = code
            if not args.daemon:
                break
            continue

        log(log_path, f"claimed task={task_id} assignee={assignee} run_id={claim[1]}")
        if direct_reply:
            log(log_path, f"direct Discord reply enabled task={task_id} assignee={assignee}")
        dispatch_jobs.append((task_id, assignee, claim, direct_reply))

    if args.dry_run or not dispatch_jobs:
        return exit_code

    max_workers = max(1, min(args.max_tasks, len(dispatch_jobs)))
    log(log_path, f"dispatching {len(dispatch_jobs)} claimed task(s) with max_workers={max_workers}")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(dispatch, task_id, assignee, args.dry_run, log_path, args.worker_timeout, direct_reply): (
                task_id,
                assignee,
                claim,
                direct_reply,
            )
            for task_id, assignee, claim, direct_reply in dispatch_jobs
        }
        for future in as_completed(futures):
            task_id, assignee, claim, direct_reply = futures[future]
            try:
                code = future.result()
            except Exception as exc:  # pragma: no cover - defensive; dispatch normally returns codes
                log(log_path, f"dispatch crashed assignee={assignee} task={task_id} error={exc!r}")
                code = 1
            code = finalize_dispatch_result(db, task_id, assignee, claim, code, log_path, args.worker_timeout, direct_reply)
            if code != 0:
                exit_code = code
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
