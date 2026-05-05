import contextlib
import importlib.util
import io
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "team-message-router.py"
spec = importlib.util.spec_from_file_location("team_message_router", SCRIPT)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "messages.db"


def rows(db_path, query, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def test_init_creates_tables_and_is_idempotent(db):
    router.init_db(db)
    router.init_db(db)
    names = {r["name"] for r in rows(db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"messages", "route_events"}.issubset(names)


def test_default_db_path_constant():
    assert router.DEFAULT_DB_PATH == REPO_ROOT / "shared" / "router" / "messages.db"


def test_valid_atlas_to_forge_send_creates_pending_row_and_event(db):
    ids = router.send_messages(db, "atlas", "forge", "task.request", "summary", "goal", "deliverable")
    assert len(ids) == 1
    msg = rows(db, "SELECT * FROM messages WHERE id=?", (ids[0],))[0]
    assert msg["sender"] == "atlas"
    assert msg["recipient"] == "forge"
    assert msg["status"] == "pending"
    assert msg["ttl"] == 3
    assert msg["reply_to"] == "atlas"
    events = rows(db, "SELECT * FROM route_events WHERE message_id=?", (ids[0],))
    assert [e["kind"] for e in events] == ["created"]


def test_atlas_to_product_expands_to_three_messages(db):
    ids = router.send_messages(db, "atlas", "product", "task.request", "summary", "goal", "deliverable")
    recipients = {r["recipient"] for r in rows(db, "SELECT recipient FROM messages")}
    assert len(ids) == 3
    assert recipients == {"vega", "scout", "lumen"}


def test_unknown_recipient_rejected(db):
    with pytest.raises(router.RouterError, match="unknown recipient"):
        router.send_messages(db, "atlas", "nobody", "task.request", "summary", "goal", "deliverable")


def test_forge_to_sentinel_rejected(db):
    with pytest.raises(router.RouterError, match="may not send"):
        router.send_messages(db, "forge", "sentinel", "task.request", "summary", "goal", "deliverable")


def test_forge_to_atlas_accepted(db):
    ids = router.send_messages(db, "forge", "atlas", "task.request", "summary", "goal", "deliverable")
    assert len(ids) == 1


def test_all_workers_requires_allow_wide_fanout(db):
    with pytest.raises(router.RouterError, match="all-workers"):
        router.send_messages(db, "atlas", "all-workers", "task.request", "summary", "goal", "deliverable")
    ids = router.send_messages(db, "atlas", "all-workers", "task.request", "summary", "goal", "deliverable", allow_wide_fanout=True)
    assert len(ids) == 7


def test_ttl_over_max_trace_loop_oversized_summary_and_body_rejected(db):
    with pytest.raises(router.RouterError, match="ttl"):
        router.send_messages(db, "atlas", "forge", "task.request", "summary", "goal", "deliverable", ttl=6)
    ids = router.send_messages(db, "atlas", "forge", "task.request", "summary", "goal", "deliverable", ttl=5)
    assert rows(db, "SELECT ttl FROM messages WHERE id=?", (ids[0],))[0]["ttl"] == 5
    with pytest.raises(router.RouterError, match="trace"):
        router.validate_and_expand("atlas", "forge", "summary", {"goal": "g", "deliverable": "d"}, trace=["forge"])
    with pytest.raises(router.RouterError, match="summary"):
        router.send_messages(db, "atlas", "forge", "task.request", "x" * 241, "goal", "deliverable")
    with pytest.raises(router.RouterError, match="body_json"):
        router.send_messages(db, "atlas", "forge", "task.request", "summary", "g" * 5000, "deliverable")


def test_list_and_inspect_basic_behavior(db):
    ids = router.send_messages(db, "atlas", "forge", "task.request", "hello", "goal", "deliverable")
    out = io.StringIO()
    router.list_messages(db, out=out)
    text = out.getvalue()
    assert ids[0] in text
    assert "hello" in text
    out = io.StringIO()
    payload = router.inspect_message(db, ids[0], out=out)
    printed = json.loads(out.getvalue())
    assert payload["id"] == ids[0]
    assert payload["from"] == "atlas"
    assert payload["to"] == "forge"
    assert printed["events"][0]["kind"] == "created"


def test_main_list_and_inspect_basic_behavior(db):
    ids = router.send_messages(db, "atlas", "forge", "task.request", "hello", "goal", "deliverable")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert router.main(["list", "--db", str(db)]) == 0
    assert ids[0] in out.getvalue()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert router.main(["inspect", "--db", str(db), ids[0]]) == 0
    assert json.loads(out.getvalue())["id"] == ids[0]


def test_dispatch_pending_dry_run_writes_artifact_without_consuming_message(db, tmp_path, monkeypatch):
    monkeypatch.setattr(router, "ARTIFACT_DIR", tmp_path / "artifacts")
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("docker should not be called in dry-run")

    ids = router.send_messages(db, "atlas", "forge", "task.request", "dispatch me", "goal", "deliverable")
    dispatched = router.dispatch_pending(db, max_messages=1, dry_run=True, run_cmd=fake_run)
    assert dispatched == ids
    assert called is False
    msg = rows(db, "SELECT status FROM messages WHERE id=?", (ids[0],))[0]
    assert msg["status"] == "pending"
    artifact = tmp_path / "artifacts" / f"{ids[0]}.json"
    assert artifact.exists()
    assert json.loads(artifact.read_text())["id"] == ids[0]
    events = rows(db, "SELECT kind, payload_json FROM route_events WHERE message_id=? ORDER BY id", (ids[0],))
    assert [e["kind"] for e in events] == ["created", "dispatch_dry_run"]
    assert json.loads(events[-1]["payload_json"])["artifact_path"] == str(artifact)


def test_dispatch_pending_success_creates_kanban_task_with_body_and_idempotency(db, tmp_path, monkeypatch):
    monkeypatch.setattr(router, "ARTIFACT_DIR", tmp_path / "artifacts")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout='''Fixing ownership of /opt/data to hermes (501)
{
  "id": "t_123abc",
  "title": "[router:msg] dispatch me",
  "status": "ready"
}
 Container team-nexus-atlas-run Created
''', stderr="")

    ids = router.send_messages(db, "atlas", "forge", "task.request", "dispatch me", "goal", "deliverable")
    dispatched = router.dispatch_pending(db, max_messages=1, run_cmd=fake_run)

    assert dispatched == ids
    msg = rows(db, "SELECT status, kanban_task_id, error FROM messages WHERE id=?", (ids[0],))[0]
    assert msg["status"] == "dispatched"
    assert msg["kanban_task_id"] == "t_123abc"
    assert msg["error"] is None
    cmd = calls[0]
    assert "--body" in cmd
    body = cmd[cmd.index("--body") + 1]
    assert "Router artifact:" in body
    assert f"{ids[0]}.json" in body
    assert "goal" in body
    assert "deliverable" in body
    assert "--idempotency-key" in cmd
    assert f"router:{ids[0]}" in cmd


def test_dispatch_pending_failure_keeps_message_pending_and_records_failure(db, tmp_path, monkeypatch):
    monkeypatch.setattr(router, "ARTIFACT_DIR", tmp_path / "artifacts")

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="kanban exploded")

    ids = router.send_messages(db, "atlas", "forge", "task.request", "dispatch me", "goal", "deliverable")
    dispatched = router.dispatch_pending(db, max_messages=1, run_cmd=fake_run)

    assert dispatched == []
    msg = rows(db, "SELECT status, error FROM messages WHERE id=?", (ids[0],))[0]
    assert msg["status"] == "pending"
    assert "kanban exploded" in msg["error"]
    events = rows(db, "SELECT kind FROM route_events WHERE message_id=? ORDER BY id", (ids[0],))
    assert [e["kind"] for e in events] == ["created", "kanban_failed"]


def test_dispatch_pending_rejects_invalid_max(db):
    with pytest.raises(router.RouterError, match="max_messages"):
        router.dispatch_pending(db, max_messages=0)
    with pytest.raises(router.RouterError, match="max_messages"):
        router.dispatch_pending(db, max_messages=-1)


def test_sensitive_payloads_are_rejected_before_storage(db):
    with pytest.raises(router.RouterError, match="sensitive"):
        router.send_messages(db, "atlas", "forge", "task.request", "review token", "OPENAI_API_KEY=sk-test", "deliverable")
    assert not db.exists()


def test_list_rejects_unknown_status(db):
    router.init_db(db)
    with pytest.raises(router.RouterError, match="status"):
        router.list_messages(db, status="wat")


def test_main_send_and_list_status_paths(db):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert router.main([
            "send", "--db", str(db), "--from", "atlas", "--to", "forge",
            "--summary", "cli smoke", "--goal", "goal", "--deliverable", "deliverable",
        ]) == 0
    mid = out.getvalue().strip()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert router.main(["list", "--db", str(db), "--status", "pending"]) == 0
    assert mid in out.getvalue()


def test_main_rejects_sensitive_payload(db):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert router.main([
            "send", "--db", str(db), "--from", "atlas", "--to", "forge",
            "--summary", "bad", "--goal", "DISCORD_BOT_TOKEN=abc", "--deliverable", "deliverable",
        ]) == 2
    assert "sensitive" in err.getvalue()
