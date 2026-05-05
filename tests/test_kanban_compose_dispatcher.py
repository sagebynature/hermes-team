from __future__ import annotations

import argparse
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
DISPATCHER_PATH = REPO_ROOT / "scripts" / "kanban-compose-dispatcher.py"


def load_dispatcher_module():
    spec = importlib.util.spec_from_file_location("kanban_compose_dispatcher", DISPATCHER_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_args(db: Path, *, dry_run: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        db=str(db),
        dry_run=dry_run,
        include_atlas=False,
        max_tasks=1,
        daemon=False,
    )


def init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                assignee TEXT,
                status TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL,
                started_at INTEGER,
                completed_at INTEGER,
                claim_lock TEXT,
                claim_expires INTEGER,
                worker_pid INTEGER,
                current_run_id INTEGER
            );
            CREATE TABLE task_links (
                parent_id TEXT NOT NULL,
                child_id TEXT NOT NULL
            );
            CREATE TABLE task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT,
                created_at INTEGER NOT NULL,
                run_id INTEGER
            );
            CREATE TABLE task_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                profile TEXT,
                status TEXT,
                outcome TEXT,
                started_at INTEGER NOT NULL,
                ended_at INTEGER,
                summary TEXT,
                error TEXT,
                metadata TEXT,
                worker_pid INTEGER
            );
            INSERT INTO tasks (id, title, assignee, status, priority, created_at)
            VALUES ('t_ready', 'Ready smoke task', 'scout', 'ready', 0, 1000);
            """
        )
        conn.commit()
    finally:
        conn.close()


class KanbanComposeDispatcherTests(unittest.TestCase):
    def test_real_dispatch_claims_ready_task_before_spawning_worker(self):
        dispatcher = load_dispatcher_module()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            db = tmp / "kanban.db"
            init_db(db)
            log_path = tmp / "dispatcher.log"
            observed_during_spawn = []

            def fake_dispatch(task_id: str, assignee: str, dry_run: bool, log_path: Path) -> int:
                with sqlite3.connect(db) as conn:
                    task = conn.execute(
                        "SELECT status, started_at, claim_lock, claim_expires, current_run_id FROM tasks WHERE id = ?",
                        (task_id,),
                    ).fetchone()
                    observed_during_spawn.append((task_id, assignee, dry_run, task))
                    run_id = task[4]
                    conn.execute(
                        "UPDATE tasks SET status = 'done', completed_at = 2000, claim_lock = NULL, claim_expires = NULL, current_run_id = NULL WHERE id = ?",
                        (task_id,),
                    )
                    conn.execute(
                        "UPDATE task_runs SET status = 'done', outcome = 'completed', ended_at = 2000 WHERE id = ?",
                        (run_id,),
                    )
                    conn.execute(
                        "INSERT INTO task_events(task_id, kind, payload, created_at, run_id) VALUES (?, 'completed', '{}', 2000, ?)",
                        (task_id, run_id),
                    )
                    conn.commit()
                return 0

            with mock.patch.object(dispatcher, "dispatch", fake_dispatch):
                code = dispatcher.run_pass(make_args(db), {"scout": "scout"}, log_path)

            self.assertEqual(code, 0)
            self.assertEqual(len(observed_during_spawn), 1)
            self.assertEqual(observed_during_spawn[0][0:3], ("t_ready", "scout", False))
            task_during_spawn = observed_during_spawn[0][3]
            self.assertEqual(task_during_spawn[0], "running")
            self.assertIsNotNone(task_during_spawn[1])
            self.assertTrue(task_during_spawn[2])
            self.assertIsNotNone(task_during_spawn[3])
            self.assertIsNotNone(task_during_spawn[4])
            with sqlite3.connect(db) as conn:
                final_task = conn.execute(
                    "SELECT status, claim_lock, claim_expires, current_run_id FROM tasks WHERE id = 't_ready'"
                ).fetchone()
                events = conn.execute("SELECT kind, run_id FROM task_events WHERE task_id = 't_ready' ORDER BY id").fetchall()
                runs = conn.execute("SELECT task_id, profile, status, outcome, ended_at FROM task_runs").fetchall()

            self.assertEqual(final_task, ("done", None, None, None))
            self.assertEqual([kind for kind, _ in events], ["claimed", "completed"])
            self.assertEqual(runs, [("t_ready", "scout", "done", "completed", 2000)])

    def test_failed_worker_spawn_requeues_task_but_preserves_failed_run(self):
        dispatcher = load_dispatcher_module()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            db = tmp / "kanban.db"
            init_db(db)
            log_path = tmp / "dispatcher.log"

            def failing_dispatch(task_id: str, assignee: str, dry_run: bool, log_path: Path) -> int:
                return 17

            with mock.patch.object(dispatcher, "dispatch", failing_dispatch):
                code = dispatcher.run_pass(make_args(db), {"scout": "scout"}, log_path)

            self.assertEqual(code, 17)
            with sqlite3.connect(db) as conn:
                task = conn.execute(
                    "SELECT status, claim_lock, claim_expires, current_run_id FROM tasks WHERE id = 't_ready'"
                ).fetchone()
                events = conn.execute("SELECT kind, run_id FROM task_events WHERE task_id = 't_ready' ORDER BY id").fetchall()
                runs = conn.execute("SELECT status, outcome, ended_at FROM task_runs WHERE task_id = 't_ready'").fetchall()

            self.assertEqual(task, ("ready", None, None, None))
            self.assertEqual([kind for kind, _ in events], ["claimed", "dispatch_failed"])
            self.assertEqual(runs[0][0:2], ("failed", "spawn_failed"))
            self.assertIsNotNone(runs[0][2])

    def test_dry_run_does_not_claim_or_dispatch_ready_task(self):
        dispatcher = load_dispatcher_module()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            db = tmp / "kanban.db"
            init_db(db)
            log_path = tmp / "dispatcher.log"

            def fail_dispatch(*args, **kwargs):
                raise AssertionError("dry-run must not dispatch")

            with mock.patch.object(dispatcher, "dispatch", fail_dispatch):
                code = dispatcher.run_pass(make_args(db, dry_run=True), {"scout": "scout"}, log_path)

            self.assertEqual(code, 0)
            with sqlite3.connect(db) as conn:
                task = conn.execute("SELECT status, started_at, claim_lock, current_run_id FROM tasks WHERE id = 't_ready'").fetchone()
                event_count = conn.execute("SELECT COUNT(*) FROM task_events WHERE task_id = 't_ready'").fetchone()[0]
                run_count = conn.execute("SELECT COUNT(*) FROM task_runs WHERE task_id = 't_ready'").fetchone()[0]

            self.assertEqual(task, ("ready", None, None, None))
            self.assertEqual(event_count, 0)
            self.assertEqual(run_count, 0)


if __name__ == "__main__":
    unittest.main()
