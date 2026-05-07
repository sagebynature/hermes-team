from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "scripts" / "kanban-mission-contract.py"


def load_contract_module():
    spec = importlib.util.spec_from_file_location("kanban_mission_contract", CONTRACT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def init_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
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
                idempotency_key TEXT UNIQUE
            );
            """
        )


class KanbanMissionContractTests(unittest.TestCase):
    def test_default_db_points_at_profile_runtime_kanban_home(self):
        contract = load_contract_module()
        self.assertEqual(
            contract.KANBAN_DB,
            REPO_ROOT / "runtime" / "hermes" / "kanban" / "kanban.db",
        )

    def test_installed_trigger_rejects_task_without_mission_marker(self):
        contract = load_contract_module()
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "kanban.db"
            init_db(db)
            with sqlite3.connect(db) as conn:
                contract.install_triggers(conn)
                with self.assertRaisesRegex(sqlite3.IntegrityError, "every task must include a mission marker"):
                    conn.execute(
                        """
                        INSERT INTO tasks (id, title, body, assignee, status, created_at)
                        VALUES ('t_bad', 'Readiness Check: Vega', 'no mission here', 'vega', 'ready', 1)
                        """
                    )

    def test_installed_trigger_allows_task_with_conversation_id_body(self):
        contract = load_contract_module()
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "kanban.db"
            init_db(db)
            with sqlite3.connect(db) as conn:
                contract.install_triggers(conn)
                conn.execute(
                    """
                    INSERT INTO tasks (id, title, body, assignee, status, created_at)
                    VALUES (
                        't_good',
                        '[mission:mission_readiness_20260506] Readiness Check: Vega',
                        'conversation_id: mission_readiness_20260506\nobjective: readiness check',
                        'vega',
                        'ready',
                        1
                    )
                    """
                )
                self.assertEqual(conn.execute("SELECT count(*) FROM tasks").fetchone()[0], 1)

    def test_check_reports_existing_non_compliant_tasks(self):
        contract = load_contract_module()
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "kanban.db"
            init_db(db)
            with sqlite3.connect(db) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute(
                    """
                    INSERT INTO tasks (id, title, body, assignee, status, created_at)
                    VALUES ('t_bad', 'Readiness Check: Vega', NULL, 'vega', 'done', 1)
                    """
                )
                conn.execute(
                    """
                    INSERT INTO tasks (id, title, body, assignee, status, created_at)
                    VALUES ('t_good', '[mission:mission_demo] Readiness Check: Scout', NULL, 'scout', 'done', 2)
                    """
                )
                rows = contract.non_compliant_tasks(conn)
                self.assertEqual([row["id"] for row in rows], ["t_bad"])


if __name__ == "__main__":
    unittest.main()
