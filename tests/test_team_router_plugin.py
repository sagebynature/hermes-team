import importlib.util
import sqlite3
import sys
import types
from pathlib import Path

fastapi_stub = types.ModuleType("fastapi")

class HTTPException(Exception):
    def __init__(self, status_code=None, detail=None):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

class APIRouter:
    def get(self, *_args, **_kwargs):
        def deco(fn):
            return fn
        return deco

class Query:
    def __init__(self, default=None, **_kwargs):
        self.default = default

fastapi_stub.APIRouter = APIRouter
fastapi_stub.HTTPException = HTTPException
fastapi_stub.Query = Query
sys.modules.setdefault("fastapi", fastapi_stub)

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTER_SCRIPT = REPO_ROOT / "scripts" / "team-message-router.py"
PLUGIN_API = REPO_ROOT / "shared" / "plugins" / "team-router" / "dashboard" / "plugin_api.py"
PLUGIN_JS = REPO_ROOT / "shared" / "plugins" / "team-router" / "dashboard" / "dist" / "index.js"

router_spec = importlib.util.spec_from_file_location("team_message_router_for_plugin_tests", ROUTER_SCRIPT)
router_cli = importlib.util.module_from_spec(router_spec)
router_spec.loader.exec_module(router_cli)

plugin_spec = importlib.util.spec_from_file_location("team_router_plugin_api", PLUGIN_API)
plugin = importlib.util.module_from_spec(plugin_spec)
plugin_spec.loader.exec_module(plugin)


def create_kanban_db(path, *, task_id="t_done", status="done"):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE tasks(id TEXT PRIMARY KEY, title TEXT, body TEXT, assignee TEXT, status TEXT);
        CREATE TABLE task_runs(id INTEGER PRIMARY KEY, task_id TEXT, profile TEXT, status TEXT, outcome TEXT, summary TEXT, error TEXT);
        """
    )
    conn.execute("INSERT INTO tasks(id, title, body, assignee, status) VALUES(?, ?, ?, ?, ?)", (task_id, "router task", "body", "scout", status))
    conn.execute("INSERT INTO task_runs(task_id, profile, status, outcome, summary, error) VALUES(?, ?, ?, ?, ?, ?)", (task_id, "scout", "done", "completed", "ok", None))
    conn.commit()
    conn.close()


def configure_paths(tmp_path, monkeypatch):
    router_db = tmp_path / "messages.db"
    kanban_db = tmp_path / "kanban.db"
    monkeypatch.setattr(plugin, "ROUTER_DB", router_db)
    monkeypatch.setattr(plugin, "KANBAN_DB", kanban_db)
    return router_db, kanban_db


def test_plugin_status_reports_counts_and_recent(tmp_path, monkeypatch):
    router_db, kanban_db = configure_paths(tmp_path, monkeypatch)
    ids = router_cli.send_messages(router_db, "atlas", "scout", "task.request", "plugin smoke", "goal", "deliverable")
    create_kanban_db(kanban_db)

    payload = plugin.status(recent_limit=10)

    assert payload["ok"] is True
    assert payload["counts"]["pending"] == 1
    assert payload["recent"][0]["id"] == ids[0]
    assert payload["router_db_exists"] is True
    assert payload["kanban_db_exists"] is True


def test_plugin_doctor_flags_sync_needed(tmp_path, monkeypatch):
    router_db, kanban_db = configure_paths(tmp_path, monkeypatch)
    ids = router_cli.send_messages(router_db, "atlas", "scout", "task.request", "sync", "goal", "deliverable")
    conn = sqlite3.connect(router_db)
    conn.execute("UPDATE messages SET status='dispatched', kanban_task_id=? WHERE id=?", ("t_done", ids[0]))
    conn.commit()
    conn.close()
    create_kanban_db(kanban_db)

    report = plugin.doctor()

    assert report["ok"] is False
    assert any(c["name"] == "completion_sync_current" and c["ok"] is False for c in report["checks"])


def test_plugin_conversation_returns_events(tmp_path, monkeypatch):
    router_db, kanban_db = configure_paths(tmp_path, monkeypatch)
    ids = router_cli.send_messages(router_db, "atlas", "scout", "task.request", "conv", "goal", "deliverable", conversation_id="conv-plugin")
    create_kanban_db(kanban_db)

    payload = plugin.conversation("conv-plugin")

    assert payload["conversation_id"] == "conv-plugin"
    assert payload["messages"][0]["id"] == ids[0]
    assert payload["messages"][0]["events"][0]["kind"] == "created"


def test_plugin_frontend_uses_dashboard_registry_api():
    script = PLUGIN_JS.read_text()

    assert "window.__HERMES_PLUGINS__.register(\"team-router\", App)" in script
    assert "SDK.registerPlugin" not in script
