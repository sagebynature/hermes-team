from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NOTIFIER_PATH = REPO_ROOT / "scripts" / "kanban-mission-notifier.py"


def load_notifier_module():
    spec = importlib.util.spec_from_file_location("kanban_mission_notifier", NOTIFIER_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT,
                assignee TEXT,
                status TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                created_by TEXT,
                created_at INTEGER NOT NULL,
                started_at INTEGER,
                completed_at INTEGER,
                workspace_kind TEXT NOT NULL DEFAULT 'scratch',
                workspace_path TEXT,
                claim_lock TEXT,
                claim_expires INTEGER,
                tenant TEXT,
                result TEXT,
                idempotency_key TEXT UNIQUE,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                worker_pid INTEGER,
                last_failure_error TEXT,
                max_runtime_seconds INTEGER,
                last_heartbeat_at INTEGER,
                current_run_id INTEGER,
                workflow_template_id TEXT,
                current_step_key TEXT,
                skills TEXT,
                spawn_failures INTEGER NOT NULL DEFAULT 0,
                last_spawn_error TEXT
            );
            CREATE TABLE task_links (
                parent_id TEXT NOT NULL,
                child_id TEXT NOT NULL,
                PRIMARY KEY(parent_id, child_id)
            );
            CREATE TABLE task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                run_id INTEGER,
                kind TEXT NOT NULL,
                payload TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE task_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                profile TEXT,
                status TEXT NOT NULL,
                outcome TEXT,
                started_at INTEGER NOT NULL,
                ended_at INTEGER,
                summary TEXT,
                metadata TEXT,
                error TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def insert_task(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    assignee: str,
    status: str,
    conversation_id: str = "mission_demo_20260506",
    title: str | None = None,
    body: str | None = None,
    result: str | None = None,
    idempotency_key: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO tasks (id, title, body, assignee, status, created_at, result, idempotency_key)
        VALUES (?, ?, ?, ?, ?, 1000, ?, ?)
        """,
        (
            task_id,
            title or f"[mission:{conversation_id}] worker task",
            body or f"conversation_id: {conversation_id}\nobjective: do useful work",
            assignee,
            status,
            result,
            idempotency_key,
        ),
    )


def append_event(conn: sqlite3.Connection, task_id: str, kind: str, payload: str = "{}") -> None:
    conn.execute(
        "INSERT INTO task_events(task_id, kind, payload, created_at) VALUES (?, ?, ?, 2000)",
        (task_id, kind, payload),
    )


class KanbanMissionNotifierTests(unittest.TestCase):
    def test_blocked_task_creates_one_human_blocker_notification(self):
        notifier = load_notifier_module()
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "kanban.db"
            init_db(db)
            with sqlite3.connect(db) as conn:
                insert_task(conn, "t_blocked", assignee="forge", status="blocked")
                append_event(conn, "t_blocked", "blocked", '{"reason":"Need repo URL","requires_human":true}')
                conn.commit()

            first = notifier.run_once(db)
            second = notifier.run_once(db)

            self.assertEqual(first.processed_events, 1)
            self.assertEqual(second.processed_events, 0)
            with sqlite3.connect(db) as conn:
                rows = conn.execute(
                    "SELECT conversation_id, task_id, kind, status, message FROM mission_notification_outbox"
                ).fetchall()
                cursor = conn.execute(
                    "SELECT value FROM mission_notifier_state WHERE key = 'last_event_id'"
                ).fetchone()[0]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0:4], ("mission_demo_20260506", "t_blocked", "human_blocker", "pending"))
            self.assertIn("Forge", rows[0][4])
            self.assertIn("Need repo URL", rows[0][4])
            self.assertEqual(cursor, "1")

    def test_worker_completion_notifies_and_creates_one_atlas_synthesis_task_when_mission_ready(self):
        notifier = load_notifier_module()
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "kanban.db"
            init_db(db)
            with sqlite3.connect(db) as conn:
                insert_task(conn, "t_scout", assignee="scout", status="done", result="Scout artifact ready")
                insert_task(conn, "t_forge", assignee="forge", status="done", result="Forge artifact ready")
                append_event(conn, "t_forge", "completed", '{"summary":"Forge artifact ready"}')
                conn.commit()

            first = notifier.run_once(db)
            second = notifier.run_once(db)

            self.assertEqual(first.created_synthesis_tasks, 1)
            self.assertEqual(second.created_synthesis_tasks, 0)
            with sqlite3.connect(db) as conn:
                synth_tasks = conn.execute(
                    "SELECT id, assignee, status, title, body, idempotency_key FROM tasks WHERE assignee = 'atlas'"
                ).fetchall()
                outbox = conn.execute(
                    "SELECT kind, task_id, target, status, message FROM mission_notification_outbox ORDER BY id"
                ).fetchall()
                created_events = conn.execute(
                    "SELECT kind FROM task_events WHERE task_id = ?",
                    (synth_tasks[0][0],),
                ).fetchall()
            self.assertEqual(len(synth_tasks), 1)
            self.assertEqual(synth_tasks[0][1:3], ("atlas", "ready"))
            self.assertIn("[mission:mission_demo_20260506]", synth_tasks[0][3])
            self.assertIn("Read completed worker outputs", synth_tasks[0][4])
            self.assertIn("Worker task summaries available at synthesis time", synth_tasks[0][4])
            self.assertIn("t_forge (forge, done): Forge artifact ready", synth_tasks[0][4])
            self.assertEqual(synth_tasks[0][5], "mission:mission_demo_20260506:atlas-synthesis")
            self.assertEqual([row[0] for row in outbox], ["human_update", "mission_ready_for_synthesis"])
            self.assertEqual([row[2] for row in outbox], ["atlas:mission", "atlas:kanban"])
            self.assertEqual([row[3] for row in outbox], ["queued", "queued"])
            self.assertEqual(created_events, [("created",)])

    def test_worker_completion_waits_when_another_worker_task_is_not_terminal(self):
        notifier = load_notifier_module()
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "kanban.db"
            init_db(db)
            with sqlite3.connect(db) as conn:
                insert_task(conn, "t_scout", assignee="scout", status="done")
                insert_task(conn, "t_forge", assignee="forge", status="running")
                append_event(conn, "t_scout", "completed", '{"summary":"Scout done"}')
                conn.commit()

            result = notifier.run_once(db)

            self.assertEqual(result.created_synthesis_tasks, 0)
            with sqlite3.connect(db) as conn:
                atlas_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE assignee = 'atlas'").fetchone()[0]
                outbox_kinds = conn.execute("SELECT kind, target, status FROM mission_notification_outbox ORDER BY id").fetchall()
            self.assertEqual(atlas_count, 0)
            self.assertEqual(outbox_kinds, [("human_update", "atlas:mission", "queued")])

    def test_completed_atlas_synthesis_creates_final_response_notification(self):
        notifier = load_notifier_module()
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "kanban.db"
            init_db(db)
            with sqlite3.connect(db) as conn:
                insert_task(
                    conn,
                    "t_synth",
                    assignee="atlas",
                    status="done",
                    title="[mission:mission_demo_20260506] synthesize final answer",
                    result="Final answer for the user.",
                    idempotency_key="mission:mission_demo_20260506:atlas-synthesis",
                )
                append_event(conn, "t_synth", "completed", '{"summary":"Final answer for the user."}')
                conn.commit()

            first = notifier.run_once(db)
            second = notifier.run_once(db)

            self.assertEqual(first.final_responses_ready, 1)
            self.assertEqual(second.final_responses_ready, 0)
            with sqlite3.connect(db) as conn:
                rows = conn.execute(
                    "SELECT conversation_id, task_id, kind, message FROM mission_notification_outbox"
                ).fetchall()
            self.assertEqual(rows[0][0:3], ("mission_demo_20260506", "t_synth", "final_response_ready"))
            self.assertIn("Final answer for the user", rows[0][3])


if __name__ == "__main__":
    unittest.main()
