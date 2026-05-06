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
    convs = rows(db, "SELECT DISTINCT conversation_id FROM messages WHERE id IN (%s)" % ",".join("?" * len(ids)), tuple(ids))
    assert len(convs) == 1
    conv = rows(db, "SELECT expected_count FROM conversations WHERE id=?", (convs[0]["conversation_id"],))[0]
    assert conv["expected_count"] == 7


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
    assert "-e" in cmd
    assert "TEAM_NEXUS_ROUTER_DISPATCH=1" in cmd
    assert "--body" in cmd
    body = cmd[cmd.index("--body") + 1]
    assert "Router artifact:" in body
    assert f"{ids[0]}.json" in body
    assert "goal" in body
    assert "deliverable" in body
    assert "--idempotency-key" in cmd
    assert f"router:{ids[0]}" in cmd


def test_dispatch_pending_default_writes_kanban_sql_without_compose_run(db, tmp_path, monkeypatch):
    monkeypatch.setattr(router, "ARTIFACT_DIR", tmp_path / "artifacts")
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db)
    monkeypatch.setattr(router, "DEFAULT_KANBAN_DB_PATH", kanban_db)

    ids = router.send_messages(db, "atlas", "forge", "task.request", "dispatch me", "goal", "deliverable")
    dispatched = router.dispatch_pending(db, max_messages=1)

    assert dispatched == ids
    msg = rows(db, "SELECT status, kanban_task_id, error FROM messages WHERE id=?", (ids[0],))[0]
    assert msg["status"] == "dispatched"
    assert msg["kanban_task_id"].startswith("t_")
    assert msg["error"] is None
    tasks = rows(kanban_db, "SELECT title, assignee, status, idempotency_key, created_by FROM tasks WHERE id=?", (msg["kanban_task_id"],))
    assert tasks[0]["title"] == f"[router:{ids[0]}] dispatch me"
    assert tasks[0]["assignee"] == "forge"
    assert tasks[0]["status"] == "ready"
    assert tasks[0]["idempotency_key"] == f"router:{ids[0]}"
    assert tasks[0]["created_by"] == "router"
    events = rows(db, "SELECT kind, payload_json FROM route_events WHERE message_id=? ORDER BY id", (ids[0],))
    assert [e["kind"] for e in events] == ["created", "kanban_created"]
    assert json.loads(events[-1]["payload_json"])["direct_sql"] is True


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


def create_kanban_db(path, *, task_id="t_done", task_status="done", run_status="done", outcome="completed", summary="router smoke ok"):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE tasks(
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT,
            assignee TEXT,
            status TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            created_by TEXT,
            created_at INTEGER DEFAULT 0,
            workspace_kind TEXT NOT NULL DEFAULT 'scratch',
            idempotency_key TEXT
        );
        CREATE TABLE task_events(
            id INTEGER PRIMARY KEY,
            task_id TEXT,
            run_id INTEGER,
            kind TEXT,
            payload TEXT,
            created_at INTEGER
        );
        CREATE TABLE task_runs(
            id INTEGER PRIMARY KEY,
            task_id TEXT,
            profile TEXT,
            status TEXT,
            outcome TEXT,
            summary TEXT,
            error TEXT
        );
    """)
    conn.execute(
        "INSERT INTO tasks(id, title, body, assignee, status) VALUES(?, ?, ?, ?, ?)",
        (task_id, "[router:msg] done", "body", "scout", task_status),
    )
    conn.execute(
        "INSERT INTO task_runs(task_id, profile, status, outcome, summary, error) VALUES(?, ?, ?, ?, ?, ?)",
        (task_id, "scout", run_status, outcome, summary, None),
    )
    conn.commit()
    conn.close()


def test_sync_completions_marks_dispatched_message_completed_and_records_result(db, tmp_path):
    router.init_db(db)
    ids = router.send_messages(db, "atlas", "scout", "task.request", "sync me", "goal", "deliverable")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE messages SET status='dispatched', kanban_task_id=? WHERE id=?", ("t_done", ids[0]))
    conn.commit()
    conn.close()
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db)

    synced = router.sync_completions(db, kanban_db)

    assert synced == [ids[0]]
    msg = rows(db, "SELECT status, error FROM messages WHERE id=?", (ids[0],))[0]
    assert msg["status"] == "completed"
    assert msg["error"] is None
    events = rows(db, "SELECT kind, payload_json FROM route_events WHERE message_id=? ORDER BY id", (ids[0],))
    assert [e["kind"] for e in events] == ["created", "completion_synced"]
    payload = json.loads(events[-1]["payload_json"])
    assert payload["kanban_task_id"] == "t_done"
    assert payload["task_status"] == "done"
    assert payload["run_summary"] == "router smoke ok"


def test_sync_completions_marks_dispatched_message_blocked(db, tmp_path):
    router.init_db(db)
    ids = router.send_messages(db, "atlas", "scout", "task.request", "sync block", "goal", "deliverable")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE messages SET status='dispatched', kanban_task_id=? WHERE id=?", ("t_blocked", ids[0]))
    conn.commit()
    conn.close()
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db, task_id="t_blocked", task_status="blocked", run_status="blocked", outcome="blocked", summary="need input")

    synced = router.sync_completions(db, kanban_db)

    assert synced == [ids[0]]
    msg = rows(db, "SELECT status, error FROM messages WHERE id=?", (ids[0],))[0]
    assert msg["status"] == "blocked"
    assert "need input" in msg["error"]


def test_main_sync_completions_cli_prints_synced_ids(db, tmp_path):
    router.init_db(db)
    ids = router.send_messages(db, "atlas", "scout", "task.request", "sync cli", "goal", "deliverable")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE messages SET status='dispatched', kanban_task_id=? WHERE id=?", ("t_done", ids[0]))
    conn.commit()
    conn.close()
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db)

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert router.main(["sync-completions", "--db", str(db), "--kanban-db", str(kanban_db)]) == 0

    assert ids[0] in out.getvalue()


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



def test_router_status_reports_counts_and_sync_needed(db, tmp_path):
    router.init_db(db)
    ids = router.send_messages(db, "atlas", "scout", "task.request", "status me", "goal", "deliverable")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE messages SET status='dispatched', kanban_task_id=? WHERE id=?", ("t_done", ids[0]))
    conn.commit()
    conn.close()
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db)

    status = router.router_status(db, kanban_db)

    assert status["ok"] is True
    assert status["counts"]["dispatched"] == 1
    assert status["counts"]["total"] == 1
    assert status["recent"][0]["id"] == ids[0]
    assert any(p["kind"] == "sync_needed" for p in status["problems"])


def test_router_doctor_flags_missing_task_id(db, tmp_path):
    router.init_db(db)
    ids = router.send_messages(db, "atlas", "scout", "task.request", "doctor me", "goal", "deliverable")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE messages SET status='dispatched' WHERE id=?", (ids[0],))
    conn.commit()
    conn.close()
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db)

    report = router.router_doctor(db, kanban_db)

    assert report["ok"] is False
    missing = [c for c in report["checks"] if c["name"] == "no_missing_kanban_task_ids"][0]
    assert missing["ok"] is False


def test_router_conversation_returns_messages_and_events(db):
    ids = router.send_messages(db, "atlas", "scout", "task.request", "conv", "goal", "deliverable", conversation_id="conv-1")

    payload = router.router_conversation(db, "conv-1")

    assert payload["ok"] is True
    assert payload["conversation_id"] == "conv-1"
    assert payload["message_count"] == 1
    assert payload["messages"][0]["id"] == ids[0]
    assert payload["messages"][0]["events"][0]["kind"] == "created"


def test_main_status_doctor_conversation_emit_json(db, tmp_path):
    ids = router.send_messages(db, "atlas", "scout", "task.request", "cli status", "goal", "deliverable", conversation_id="conv-cli")
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db)
    for command in [
        ["status", "--db", str(db), "--kanban-db", str(kanban_db)],
        ["doctor", "--db", str(db), "--kanban-db", str(kanban_db)],
        ["conversation", "--db", str(db), "conv-cli"],
    ]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert router.main(command) == 0
        assert json.loads(out.getvalue())


def test_all_workers_fanout_creates_conversation_record_and_aggregate_status(db):
    ids = router.send_messages(
        db,
        "atlas",
        "all-workers",
        "task.request",
        "Team introduction",
        "Introduce yourself to Sage",
        "role, expertise, contribution",
        conversation_id="conv-intro",
        allow_wide_fanout=True,
    )

    assert len(ids) == 7
    conv_rows = rows(db, "SELECT id, status, expected_count FROM conversations WHERE id=?", ("conv-intro",))
    assert len(conv_rows) == 1
    assert conv_rows[0]["status"] == "open"
    assert conv_rows[0]["expected_count"] == 7
    payload = router.router_conversation(db, "conv-intro")
    assert payload["status"] == "open"
    assert payload["counts"]["pending"] == 7
    assert payload["expected_count"] == 7


def test_sync_completions_marks_conversation_completed_once(db, tmp_path):
    ids = router.send_messages(db, "atlas", "product", "task.request", "sync product", "goal", "deliverable", conversation_id="conv-product")
    conn = sqlite3.connect(db)
    for idx, mid in enumerate(ids):
        conn.execute("UPDATE messages SET status='dispatched', kanban_task_id=? WHERE id=?", (f"t_done_{idx}", mid))
    conn.commit()
    conn.close()
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db, task_id="t_done_0", task_status="done", run_status="done", outcome="completed", summary="vega ok")
    conn = sqlite3.connect(kanban_db)
    for idx, assignee in [(1, "scout"), (2, "lumen")]:
        conn.execute("INSERT INTO tasks(id, title, body, assignee, status) VALUES(?, ?, ?, ?, ?)", (f"t_done_{idx}", f"task {idx}", "body", assignee, "done"))
        conn.execute("INSERT INTO task_runs(task_id, profile, status, outcome, summary, error) VALUES(?, ?, ?, ?, ?, ?)", (f"t_done_{idx}", assignee, "done", "completed", f"{assignee} ok", None))
    conn.commit(); conn.close()

    synced = router.sync_completions(db, kanban_db)
    synced_again = router.sync_completions(db, kanban_db)

    assert set(synced) == set(ids)
    assert synced_again == []
    conv = rows(db, "SELECT status, terminal_count, completed_at FROM conversations WHERE id=?", ("conv-product",))[0]
    assert conv["status"] == "completed"
    assert conv["terminal_count"] == 3
    assert conv["completed_at"] is not None
    events = rows(db, "SELECT kind FROM route_events WHERE message_id=?", ("conversation:conv-product",))
    assert [e["kind"] for e in events] == ["conversation_completed"]


def test_sync_completions_marks_conversation_needs_attention_for_blocked(db, tmp_path):
    ids = router.send_messages(db, "atlas", "product", "task.request", "sync product", "goal", "deliverable", conversation_id="conv-blocked")
    conn = sqlite3.connect(db)
    for idx, mid in enumerate(ids):
        conn.execute("UPDATE messages SET status='dispatched', kanban_task_id=? WHERE id=?", (f"t_mix_{idx}", mid))
    conn.commit(); conn.close()
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db, task_id="t_mix_0", task_status="done", run_status="done", outcome="completed", summary="ok")
    conn = sqlite3.connect(kanban_db)
    for idx, status, outcome in [(1, "blocked", "blocked"), (2, "done", "completed")]:
        conn.execute("INSERT INTO tasks(id, title, body, assignee, status) VALUES(?, ?, ?, ?, ?)", (f"t_mix_{idx}", f"task {idx}", "body", "scout", status))
        conn.execute("INSERT INTO task_runs(task_id, profile, status, outcome, summary, error) VALUES(?, ?, ?, ?, ?, ?)", (f"t_mix_{idx}", "scout", status, outcome, "needs input" if status == "blocked" else "ok", None))
    conn.commit(); conn.close()

    router.sync_completions(db, kanban_db)

    conv = rows(db, "SELECT status, terminal_count FROM conversations WHERE id=?", ("conv-blocked",))[0]
    assert conv["status"] == "needs_attention"
    assert conv["terminal_count"] == 3
    events = rows(db, "SELECT kind FROM route_events WHERE message_id=?", ("conversation:conv-blocked",))
    assert [e["kind"] for e in events] == ["conversation_needs_attention"]


def test_create_report_tasks_creates_single_atlas_kanban_task_for_terminal_conversation(db, tmp_path, monkeypatch):
    monkeypatch.setattr(router, "ARTIFACT_DIR", tmp_path / "artifacts")
    ids = router.send_messages(db, "atlas", "scout", "task.request", "intro", "goal", "deliverable", conversation_id="conv-report")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE messages SET status='completed', kanban_task_id='t_worker' WHERE id=?", (ids[0],))
    conn.execute("UPDATE conversations SET status='completed', terminal_count=1, completed_at='2026-05-06T00:00:00Z' WHERE id='conv-report'")
    conn.commit(); conn.close()
    calls = []
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout='{"id":"t_report","status":"ready"}', stderr="")

    created = router.create_report_tasks(db, max_conversations=5, run_cmd=fake_run)
    created_again = router.create_report_tasks(db, max_conversations=5, run_cmd=fake_run)

    assert created == ["conv-report"]
    assert created_again == []
    conv = rows(db, "SELECT report_task_id FROM conversations WHERE id=?", ("conv-report",))[0]
    assert conv["report_task_id"] == "t_report"
    cmd = calls[0]
    assert "TEAM_NEXUS_ROUTER_DISPATCH=1" in cmd
    assert "atlas" in cmd
    assert "--assignee" in cmd
    assert cmd[cmd.index("--assignee") + 1] == "atlas"
    assert "router-conversation:conv-report:report" in cmd


def test_supervisor_pass_dispatches_syncs_and_creates_reports(db, tmp_path, monkeypatch):
    monkeypatch.setattr(router, "ARTIFACT_DIR", tmp_path / "artifacts")
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db, task_id="t_worker")
    calls = []
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "[router:" in " ".join(cmd):
            return SimpleNamespace(returncode=0, stdout='{"id":"t_worker","status":"ready"}', stderr="")
        return SimpleNamespace(returncode=0, stdout='{"id":"t_report","status":"ready"}', stderr="")
    ids = router.send_messages(db, "atlas", "scout", "task.request", "intro", "goal", "deliverable", conversation_id="conv-supervisor")

    first = router.supervisor_pass(db, kanban_db, max_messages=1, create_reports=True, run_cmd=fake_run)
    second = router.supervisor_pass(db, kanban_db, max_messages=1, create_reports=True, run_cmd=fake_run)

    assert first["dispatched"] == ids
    assert first["synced"] == ids
    assert first["report_conversations"] == ["conv-supervisor"]
    assert second["dispatched"] == []
    assert second["synced"] == []
    assert second["report_conversations"] == []


def test_router_doctor_warns_about_direct_multi_agent_kanban_without_router(db, tmp_path):
    router.init_db(db)
    kanban_db = tmp_path / "kanban.db"
    create_kanban_db(kanban_db, task_id="t_direct", task_status="ready", run_status="", outcome="", summary="")
    conn = sqlite3.connect(kanban_db)
    conn.execute("UPDATE tasks SET title='Introduction: Forge', assignee='forge' WHERE id='t_direct'")
    conn.commit(); conn.close()

    report = router.router_doctor(db, kanban_db)

    assert report["ok"] is False
    assert any(p["kind"] == "direct_kanban_without_router" for p in report["status"]["problems"])
