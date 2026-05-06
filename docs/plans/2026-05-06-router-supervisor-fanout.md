# Router-Supervisor Fanout and Completion Plan

> **For Hermes:** Use test-driven-development for code changes and keep router/Kanban behavior inspectable.

**Goal:** Make Team Nexus multi-agent requests router-first, event-driven, and self-reporting: Atlas fanout must leave router evidence, worker task outcomes must sync back automatically, and completed conversations must create an Atlas synthesis/report task.

**Architecture:** Keep Kanban as the execution ledger and the Team Nexus router as the coordination/audit ledger. Add conversation state to the router, a supervisor pass/daemon that dispatches pending messages and syncs terminal Kanban outcomes, and a conversation completion detector that emits events and optionally creates an Atlas report task. Tighten Atlas instructions and docs so direct multi-agent Kanban fanout is treated as a smell unless it has a router envelope.

**Tech Stack:** Python stdlib, SQLite, Docker Compose, Makefile targets, Hermes Kanban CLI.

---

## Task 1: Add conversation state tests

**Objective:** Prove router fanout creates a shared conversation record and conversation inspection shows aggregate status.

**Files:**
- Modify: `tests/test_team_message_router.py`
- Modify: `scripts/team-message-router.py`

**Steps:**
1. Add tests that `send_messages(..., recipient="all-workers", conversation_id="conv-intro", allow_wide_fanout=True)` creates seven messages sharing `conv-intro` and one `conversations` row.
2. Run targeted test and verify it fails because `conversations` does not exist.
3. Add `conversations` table in `init_db` and upsert it in `send_messages`.
4. Extend `router_conversation` with conversation status/counts.
5. Re-run targeted test until green.

## Task 2: Add completion sync and conversation terminal tests

**Objective:** Prove completed/blocked/failed worker tasks update both message and conversation state exactly once.

**Files:**
- Modify: `tests/test_team_message_router.py`
- Modify: `scripts/team-message-router.py`

**Steps:**
1. Add tests for all messages completed -> conversation `completed` with `conversation_completed` event.
2. Add tests for any blocked/failed terminal -> conversation `needs_attention` with `conversation_needs_attention` event.
3. Verify tests fail.
4. Implement `update_conversation_states()` and call it from `sync_completions()`.
5. Re-run targeted tests.

## Task 3: Add Atlas report task creation tests

**Objective:** Prove a completed conversation can materialize exactly one Atlas synthesis Kanban task with an idempotency key.

**Files:**
- Modify: `tests/test_team_message_router.py`
- Modify: `scripts/team-message-router.py`

**Steps:**
1. Add tests for `create_report_tasks(..., run_cmd=fake_run)` creating a Kanban task assigned to `atlas` for completed/needs_attention conversations without `report_task_id`.
2. Verify it fails because function/CLI does not exist.
3. Implement `build_report_body()` and `create_report_tasks()` using `router-conversation` evidence and `--idempotency-key router-conversation:<conversation-id>:report`.
4. Add CLI `create-report-tasks`.
5. Re-run tests.

## Task 4: Add supervisor pass/daemon tests and implementation

**Objective:** Provide one operational command that dispatches, syncs, updates conversations, and optionally creates Atlas report tasks.

**Files:**
- Modify: `tests/test_team_message_router.py`
- Modify: `scripts/team-message-router.py`
- Modify: `Makefile`
- Modify: `docker-compose.yml`

**Steps:**
1. Add tests for `supervisor_pass()` calling dispatch, sync, and report creation in order.
2. Add CLI `supervise --daemon --interval --max-messages --create-report-tasks`.
3. Add Make targets: `router-supervisor-once`, `router-supervisor-daemon`, `router-supervisor-logs`, `router-supervisor-stop`.
4. Add a `router-supervisor` Compose service under the dispatcher profile.
5. Add `KANBAN_DISPATCH_INCLUDE_ATLAS` support to the dispatcher command so Atlas report tasks can run when desired.
6. Validate `docker compose --profile dispatcher config`.

## Task 5: Add direct-Kanban smell detection

**Objective:** Make it obvious when Atlas created multi-agent Kanban tasks without router evidence.

**Files:**
- Modify: `tests/test_team_message_router.py`
- Modify: `scripts/team-message-router.py`

**Steps:**
1. Add a test with recent `tasks` rows such as `Introduction: Forge` without `idempotency_key like 'router:%'` and assert `router_doctor()` warns with `direct_kanban_without_router`.
2. Verify it fails.
3. Implement `detect_direct_kanban_smells()` and surface warnings in `router_status()`/`router_doctor()`.
4. Re-run tests.

## Task 6: Update ADR, README, and Atlas instructions

**Objective:** Document router-first fanout as the architecture and teach operators/Atlas how to run it.

**Files:**
- Modify: `docs/adr/0006-compose-aware-kanban-dispatcher.md` or create `docs/adr/0007-router-supervisor.md`
- Modify: `README.md`
- Modify: `docs/agent-message-router.md`
- Modify: `shared/router/README.md`
- Modify: `agents/atlas/home/AGENTS.md`
- Modify: `agents/atlas/home/SOUL.md`

**Steps:**
1. Record the decision: router is coordination source of truth, Kanban is execution source of truth, supervisor bridges outcomes.
2. Update operation commands and expected acknowledgement/final-report behavior.
3. Tighten Atlas rule: multi-agent fanout must use router; direct Kanban is only a labeled fallback.
4. Include immediate acknowledgement contract with router message IDs and final synthesis contract.

## Task 7: Verify

**Objective:** Ensure implementation is safe and docs are consistent.

**Commands:**
- `/Users/sage/.local/bin/pytest tests/test_team_message_router.py -q`
- `python3 -m py_compile scripts/team-message-router.py scripts/kanban-compose-dispatcher.py`
- `make check-generated`
- `make validate`
- `docker compose --profile dispatcher config >/tmp/team-nexus-dispatcher-config.yml`

**Acceptance criteria:**
- Router fanout creates inspectable message IDs and one conversation ID.
- Worker terminal outcomes create message events and conversation terminal events.
- Completed/needs-attention conversations create exactly one Atlas report task when enabled.
- Supervisor can run continuously as a Compose service.
- Router doctor flags direct multi-agent Kanban tasks without router linkage.
- Docs and Atlas instructions say multi-agent fanout is router-first.
