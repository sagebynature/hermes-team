# Team Nexus Agent Message Router / Bus Implementation Plan

> Historical/superseded by ADR-0014 where it references `shared/team-agents.yaml`, per-agent Compose services, or a custom Compose dispatcher. Current Team Nexus routing should use Atlas plus native/profile-driven Kanban evidence in `profiles/team-nexus.profiles.yaml` and `docker-compose.profiles.yml`.

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a bounded, inspectable message router/bus for Team Nexus agent-to-agent coordination without letting Discord bot chatter become the coordination substrate.

**Architecture:** Keep Discord as the human mission room and keep Kanban as the execution source of truth. Add a small router layer that accepts structured agent messages, validates recipients and budgets, fans out only through registered routes, and materializes worker requests as Kanban tasks. Atlas remains the default user-facing aggregator; workers return concise deliverables through task completion artifacts/comments rather than free-form bot-to-bot chat.

**Tech Stack:** Python stdlib, SQLite, Docker Compose, existing `shared/team-agents.yaml`, existing shared Kanban board, existing Compose dispatcher, Markdown docs/ADRs, pytest.

---

## Verified Starting State

Observed on 2026-05-05:

- All Team Nexus agent gateway containers are running locally:
  - `hermes-atlas` on `127.0.0.1:8642`
  - `hermes-vega` on `127.0.0.1:8643`
  - `hermes-scout` on `127.0.0.1:8644`
  - `hermes-forge` on `127.0.0.1:8645`
  - `hermes-lumen` on `127.0.0.1:8646`
  - `hermes-blitz` on `127.0.0.1:8647`
  - `hermes-ledger` on `127.0.0.1:8648`
  - `hermes-sentinel` on `127.0.0.1:8649`
- Gateway logs confirm distinct Discord bot identities are connected:
  - `atlas#7896`, `vega#2826`, `scout#2167`, `forge#1670`, `lumen#4912`, `blitz#0840`, `ledger#2892`, `sentinel#5786`
- Each agent has an `agents/<agent>/home/.env` with a distinct `DISCORD_BOT_TOKEN`.
- `DISCORD_ALLOW_BOTS` is absent, which is good for now. We should not turn Discord into a bot-to-bot free-chat network as the primary A2A control plane.

---

## Primary Design Choice

Build the router as a control plane, not as a chat room.

The router should answer this question:

> “Given a bounded structured request from Atlas or another authorized agent, who should do what, how is it tracked, and where is the concise result returned?”

It should not answer this question:

> “How do we let every bot talk freely to every other bot until something useful emerges?”

---

## Goals

1. **Bounded agent-to-agent work dispatch**
   - Structured messages, not raw prose chains.
   - Every request has a recipient, TTL, budget, expected deliverable, and stop condition.

2. **Atlas-first orchestration**
   - User-facing synthesis flows through Atlas by default.
   - Workers may communicate only when a route is explicitly allowed.

3. **Reuse existing Kanban execution**
   - Router requests to workers become Kanban tasks assigned to agent slugs.
   - The existing Compose-aware Kanban dispatcher executes tasks.
   - Kanban remains the source of truth for work state: ready/running/done/blocked.

4. **Inspectable state**
   - Store router envelopes, decisions, fanout events, and links to Kanban tasks in SQLite under `shared/router/`.
   - Keep a human-readable event log.
   - Add CLI commands for list/inspect/send/sweep.

5. **Loop prevention and dedupe from day one**
   - Message IDs are unique and deduped.
   - TTL decrements on each hop.
   - Trace is checked before dispatch.
   - Broadcasts fan out once and never recursively broadcast.

6. **Token discipline**
   - Workers receive concise prompts.
   - Router stores summaries and artifact paths, not full transcripts.
   - Default prompts must cap output size.

7. **Safe failure behavior**
   - Invalid recipients are rejected.
   - Expired messages are blocked/dropped with an event.
   - Worker timeout remains governed by the existing dispatcher timeout.
   - Failed routes do not retry forever.

---

## Anti-Goals / Things To Avoid

1. **No free-form Discord bot swarm**
   - Do not make Discord mentions the primary agent-to-agent bus.
   - Do not set `DISCORD_ALLOW_BOTS=all` globally.
   - If bot-originated Discord messages are enabled later, use `mentions` and only for smoke tests or human-visible notifications.

2. **No all-to-all peer mesh**
   - Do not let any agent message any other agent by default.
   - Start with `atlas -> workers` and `workers -> atlas` only.
   - Add worker-to-worker routes only after a concrete use case exists.

3. **No recursive delegation loops**
   - Workers should not spawn broad multi-agent subtasks.
   - Router must reject messages whose `to` is already in `trace` unless an explicit route allows it.

4. **No raw transcript forwarding**
   - Workers summarize and attach artifact paths.
   - Router messages should never embed full gateway sessions, full logs, or large web captures.

5. **No shared memory/home as communication**
   - Keep agent homes isolated.
   - Use the router and Kanban artifacts for handoff.

6. **No dynamic invented recipients**
   - Valid recipients come from `shared/team-agents.yaml`.
   - Group aliases must be explicitly registered, e.g. `product`, `delivery`, `all-workers`.

7. **No unbounded fanout**
   - Default max fanout: 3 agents per message.
   - Anything broader requires Atlas to create a plan and justify it.

8. **No hidden side effects**
   - Every routed request creates an audit event.
   - Every Kanban task created by the router includes the source message ID.

---

## Proposed Message Envelope

Router messages should be JSON-serializable and stable:

```json
{
  "id": "msg_20260505_abc123",
  "conversation_id": "conv_20260505_intro_smoke",
  "parent_id": null,
  "from": "atlas",
  "to": "forge",
  "type": "task.request",
  "priority": "normal",
  "ttl": 3,
  "created_at": "2026-05-05T21:30:00Z",
  "requires_response": true,
  "reply_to": "atlas",
  "summary": "Provide engineering input on the launch plan.",
  "body": {
    "goal": "Identify engineering risks and dependencies.",
    "constraints": [
      "Keep response under 300 words",
      "No secrets or raw logs",
      "Return exactly: summary, risks, next_actions"
    ],
    "deliverable": "Concise structured response for Atlas synthesis"
  },
  "artifacts": [],
  "trace": ["atlas"]
}
```

Required fields:

- `id`
- `conversation_id`
- `from`
- `to`
- `type`
- `ttl`
- `created_at`
- `body`
- `trace`

---

## Initial Route Policy

MVP route table:

```yaml
routes:
  atlas:
    can_send_to:
      - vega
      - scout
      - forge
      - lumen
      - blitz
      - ledger
      - sentinel
      - product
      - delivery
      - all-workers
  vega:
    can_send_to: [atlas]
  scout:
    can_send_to: [atlas]
  forge:
    can_send_to: [atlas]
  lumen:
    can_send_to: [atlas]
  blitz:
    can_send_to: [atlas]
  ledger:
    can_send_to: [atlas]
  sentinel:
    can_send_to: [atlas]

groups:
  product: [vega, scout, lumen]
  delivery: [forge, sentinel]
  all-workers: [vega, scout, forge, lumen, blitz, ledger, sentinel]

limits:
  default_ttl: 3
  max_ttl: 5
  max_fanout: 3
  max_summary_chars: 240
  max_body_chars: 4000
```

For MVP, `all-workers` should be disabled by policy unless a `--allow-wide-fanout` flag is passed by a human/operator command.

---

## Files To Create

- `shared/router/.gitignore`
- `shared/router/README.md`
- `shared/router/router-policy.yaml`
- `scripts/team-message-router.py`
- `tests/test_team_message_router.py`
- `docs/adr/0013-agent-message-router-bus.md`
- `docs/agent-message-router.md`

## Files To Modify

- `Makefile`
- `README.md`
- `GETTING_STARTED.md`
- `docs/team-nexus-operations.md`
- `shared/project/team-collaboration-protocol.md`

Optional later:

- `docker-compose.yml` if we decide to run a long-lived router daemon instead of using the existing dispatcher profile.
- `shared/team-agents.yaml` if route groups should become registry-driven.

---

## Phase 0: Discovery and Safety Baseline

### Task 0.1: Capture current gateway and Discord state

**Objective:** Document the current running state without printing secrets.

**Files:**
- Modify: `docs/plans/2026-05-05-agent-message-router-bus.md`

**Steps:**

1. Run:
   ```bash
   docker ps --filter 'name=hermes-' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
   ```
2. Check gateway logs for connected identities:
   ```bash
   for a in atlas vega scout forge lumen blitz ledger sentinel; do
     echo "--- $a"
     docker compose -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml exec -T "$a" \
       bash -lc "tail -80 /opt/data/logs/gateway.log | grep -Ei 'Connected as|discord connected' | tail -5"
   done
   ```
3. Verify no broad bot-to-bot Discord mode is enabled:
   ```bash
   for a in atlas vega scout forge lumen blitz ledger sentinel; do
     grep -E '^DISCORD_ALLOW_BOTS=' "agents/$a/home/.env" || true
   done
   ```

**Expected:** Agents are connected; `DISCORD_ALLOW_BOTS` is absent or not `all`.

---

## Phase 1: Write the ADR and Operator Rules

### Task 1.1: Create the router ADR

**Objective:** Record why Team Nexus uses a router/bus instead of free Discord bot chatter.

**Files:**
- Create: `docs/adr/0013-agent-message-router-bus.md`

**Content outline:**

```markdown
# ADR 0013: Structured Agent Message Router / Bus

## Status
Accepted

## Context
Team Nexus runs one Hermes runtime per agent. Discord can make the team visible to the human operator, but bot-to-bot Discord chatter risks loops, duplicated work, and uncontrolled token burn.

## Decision
Use a structured router/bus as the agent-to-agent control plane. Keep Discord human-facing and keep Kanban as execution source of truth. Atlas is the default user-facing aggregator.

## Consequences
- Positive: bounded dispatch, auditability, loop prevention, cheaper execution.
- Negative: less theatrical real-time bot chatter, more explicit protocol surface.
- Follow-up: build a small SQLite-backed router and integrate it with Kanban.
```

**Verification:**

```bash
test -f docs/adr/0013-agent-message-router-bus.md
```

---

### Task 1.2: Add operator-facing design docs

**Objective:** Give future operators a concise explanation of how to use the router safely.

**Files:**
- Create: `docs/agent-message-router.md`
- Modify: `README.md`
- Modify: `GETTING_STARTED.md`
- Modify: `docs/team-nexus-operations.md`

**Required sections in `docs/agent-message-router.md`:**

- Purpose
- Goals
- Anti-goals
- Envelope fields
- Route policy
- Loop-prevention checklist
- When to use Kanban directly instead
- When not to route
- Troubleshooting

**Verification:**

```bash
grep -R "agent message router" README.md GETTING_STARTED.md docs/team-nexus-operations.md docs/agent-message-router.md
```

---

## Phase 2: Router Storage and Policy MVP

### Task 2.1: Create router workspace and policy

**Objective:** Add inspectable storage conventions and route policy.

**Files:**
- Create: `shared/router/.gitignore`
- Create: `shared/router/README.md`
- Create: `shared/router/router-policy.yaml`

**`shared/router/.gitignore`:**

```gitignore
*.db
*.db-shm
*.db-wal
*.log
runtime/
```

**`shared/router/router-policy.yaml`:**

```yaml
routes:
  atlas:
    can_send_to: [vega, scout, forge, lumen, blitz, ledger, sentinel, product, delivery]
  vega:
    can_send_to: [atlas]
  scout:
    can_send_to: [atlas]
  forge:
    can_send_to: [atlas]
  lumen:
    can_send_to: [atlas]
  blitz:
    can_send_to: [atlas]
  ledger:
    can_send_to: [atlas]
  sentinel:
    can_send_to: [atlas]

groups:
  product: [vega, scout, lumen]
  delivery: [forge, sentinel]
  all-workers: [vega, scout, forge, lumen, blitz, ledger, sentinel]

limits:
  default_ttl: 3
  max_ttl: 5
  max_fanout: 3
  max_summary_chars: 240
  max_body_chars: 4000
```

**Verification:**

```bash
test -f shared/router/router-policy.yaml
python3 - <<'PY'
from pathlib import Path
p = Path('shared/router/router-policy.yaml')
assert 'routes:' in p.read_text()
assert 'limits:' in p.read_text()
print('router policy present')
PY
```

---

### Task 2.2: Implement router database initialization

**Objective:** Create a minimal SQLite schema for messages, route events, and Kanban links.

**Files:**
- Create: `scripts/team-message-router.py`
- Create: `tests/test_team_message_router.py`

**Schema:**

```sql
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  parent_id TEXT,
  sender TEXT NOT NULL,
  recipient TEXT NOT NULL,
  type TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'normal',
  ttl INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  requires_response INTEGER NOT NULL DEFAULT 1,
  reply_to TEXT,
  summary TEXT NOT NULL,
  body_json TEXT NOT NULL,
  artifacts_json TEXT NOT NULL DEFAULT '[]',
  trace_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  kanban_task_id TEXT
);

CREATE TABLE IF NOT EXISTS route_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_events_message ON route_events(message_id);
```

**Test cases:**

- `init` creates tables.
- `init` is idempotent.
- database path defaults to `shared/router/messages.db`.

**Commands:**

```bash
python3 scripts/team-message-router.py init --db /tmp/team-router-test.db
python3 -m pytest tests/test_team_message_router.py -q
```

---

## Phase 3: Envelope Validation

### Task 3.1: Validate recipients against team registry

**Objective:** Reject unknown agents and unknown groups.

**Files:**
- Modify: `scripts/team-message-router.py`
- Modify: `tests/test_team_message_router.py`

**Rules:**

- Load agent slugs from `shared/team-agents.yaml`.
- Load groups from `shared/router/router-policy.yaml`.
- Reject any recipient not in either set.
- Reject `atlas -> atlas` unless a future explicit self-route exists.

**Tests:**

- Valid: `atlas -> forge`
- Valid: `atlas -> product`
- Invalid: `atlas -> madeup`

---

### Task 3.2: Enforce route policy and fanout limits

**Objective:** Prevent all-to-all chaos.

**Files:**
- Modify: `scripts/team-message-router.py`
- Modify: `tests/test_team_message_router.py`

**Rules:**

- `sender` must be allowed to send to `recipient` by policy.
- Group expansion must not exceed `limits.max_fanout` unless operator passes `--allow-wide-fanout`.
- Default MVP should keep `all-workers` unavailable through normal sends.

**Tests:**

- `atlas -> delivery` is allowed.
- `forge -> sentinel` is rejected.
- `forge -> atlas` is allowed.
- `atlas -> all-workers` is rejected without `--allow-wide-fanout`.

---

### Task 3.3: Enforce TTL, trace, and payload size limits

**Objective:** Stop loops and token blowups before dispatch.

**Files:**
- Modify: `scripts/team-message-router.py`
- Modify: `tests/test_team_message_router.py`

**Rules:**

- TTL must be `1..max_ttl`.
- If TTL is omitted, use `limits.default_ttl`.
- Reject dispatch if recipient is already in `trace`.
- Reject `summary` longer than `max_summary_chars`.
- Reject serialized `body` longer than `max_body_chars`.

**Tests:**

- TTL default is applied.
- TTL over max is rejected.
- Trace loop is rejected.
- Oversized body is rejected.

---

## Phase 4: CLI Send/List/Inspect

### Task 4.1: Add `send` command

**Objective:** Allow Atlas/operator to create one or more pending router messages.

**Files:**
- Modify: `scripts/team-message-router.py`
- Modify: `tests/test_team_message_router.py`

**Example command:**

```bash
python3 scripts/team-message-router.py send \
  --from atlas \
  --to forge \
  --type task.request \
  --summary "Estimate engineering risks" \
  --goal "Identify implementation risks and dependencies" \
  --deliverable "summary, risks, next_actions under 300 words"
```

**Expected behavior:**

- Inserts a `messages` row with `status='pending'`.
- Inserts `route_events(kind='created')`.
- Prints message ID(s), one per recipient after group expansion.

---

### Task 4.2: Add `list` and `inspect` commands

**Objective:** Make router state operator-inspectable.

**Files:**
- Modify: `scripts/team-message-router.py`
- Modify: `tests/test_team_message_router.py`

**Commands:**

```bash
python3 scripts/team-message-router.py list --status pending
python3 scripts/team-message-router.py inspect msg_...
```

**Output:**

- `list`: compact table: ID, from, to, type, ttl, status, summary.
- `inspect`: JSON envelope plus route events.

---

## Phase 5: Kanban Materialization

### Task 5.1: Add router-to-Kanban task creation

**Objective:** Convert pending worker messages into Kanban tasks assigned to recipient agents.

**Files:**
- Modify: `scripts/team-message-router.py`
- Modify: `tests/test_team_message_router.py`

**Approach:**

Use the existing Compose command path rather than writing Kanban DB rows by hand:

```bash
docker compose -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml run --rm atlas \
  kanban create "[router:msg_...] <summary>" --assignee "<recipient>"
```

If Hermes Kanban supports descriptions/comments in the installed CLI, include the full bounded prompt there. If not, create the task title with source message ID and add router details as an artifact under `shared/project/artifacts/router/<message-id>.json`.

**Task prompt content:**

```text
[router]
message_id: msg_...
conversation_id: conv_...
from: atlas
to: forge
reply_to: atlas

Goal: ...
Constraints:
- Keep response under 300 words
- No secrets or raw logs
- Return exactly: summary, risks, next_actions

Deliverable: ...

When done, mark this Kanban task done and include the concise deliverable in the task completion/comment/handoff artifact.
```

**Expected behavior:**

- Message status moves from `pending` to `dispatched`.
- `kanban_task_id` is recorded when discoverable.
- A `route_events(kind='kanban_created')` event is recorded.

**Important:** If task ID cannot be parsed reliably from CLI output, add a follow-up task to query the Kanban DB by title prefix. Do not guess task IDs.

---

### Task 5.2: Add `dispatch-pending` command

**Objective:** Let the operator or daemon materialize pending messages into Kanban tasks.

**Files:**
- Modify: `scripts/team-message-router.py`
- Modify: `tests/test_team_message_router.py`
- Modify: `Makefile`

**Make targets:**

```make
router-init:
	python3 scripts/team-message-router.py init

router-send:
	python3 scripts/team-message-router.py send --from "$(FROM)" --to "$(TO)" --summary "$(SUMMARY)" --goal "$(GOAL)" --deliverable "$(DELIVERABLE)"

router-dispatch:
	python3 scripts/team-message-router.py dispatch-pending --max "$(MAX_MESSAGES)"

router-list:
	python3 scripts/team-message-router.py list
```

**Verification:**

```bash
make router-init
make router-send FROM=atlas TO=forge SUMMARY='router smoke test' GOAL='respond with one sentence' DELIVERABLE='one sentence under 40 words'
make router-list
make router-dispatch MAX_MESSAGES=1
make kanban-list
```

---

## Phase 6: Dispatcher / Daemon Integration

### Task 6.1: Decide whether router dispatch should be daemonized

**Objective:** Avoid adding a long-lived service before it is necessary.

**Recommendation:** Start without a daemon. Use explicit `make router-dispatch` during development and optionally have Atlas create Kanban tasks through the router script. Add a daemon only after the protocol is stable.

**If daemon is needed later:**

- Add a `message-router` Compose service under a profile, e.g. `router`.
- Mount repo and Docker socket only if it must create Kanban tasks through Compose.
- Keep interval slow, e.g. 30-60 seconds.
- Default max messages per pass: 1-3.

**Files if daemon is added:**

- Modify: `docker-compose.yml`
- Modify: `Makefile`
- Modify: `docs/agent-message-router.md`

---

## Phase 7: Atlas Workflow Integration

### Task 7.1: Update Atlas instructions to prefer router over Discord bot summons

**Objective:** Prevent Atlas from theatrically ordering agents in Discord without actually dispatching work.

**Files:**
- Modify: `agents/atlas/home/AGENTS.md`
- Modify: `shared/project/team-collaboration-protocol.md`

**Instruction to add:**

```markdown
When the operator asks you to involve other Team Nexus agents, do not rely on Discord bot mentions as the work dispatch mechanism. Use the message router or Kanban. Keep Discord replies user-facing and summarize what was dispatched, to whom, and how the operator can inspect progress.
```

**Verification:**

```bash
grep -R "message router\|Discord bot mentions" agents/atlas/home/AGENTS.md shared/project/team-collaboration-protocol.md
```

---

## Phase 8: Smoke Tests

### Task 8.1: Router-only smoke test

**Objective:** Prove envelope validation and storage work without touching Kanban.

**Command:**

```bash
rm -f /tmp/team-router-smoke.db
python3 scripts/team-message-router.py init --db /tmp/team-router-smoke.db
python3 scripts/team-message-router.py send --db /tmp/team-router-smoke.db --from atlas --to forge --summary 'smoke' --goal 'say ok' --deliverable 'ok'
python3 scripts/team-message-router.py list --db /tmp/team-router-smoke.db
```

**Expected:** One pending message to Forge.

---

### Task 8.2: Router-to-Kanban smoke test

**Objective:** Prove the router can materialize a bounded request into existing Kanban execution.

**Command:**

```bash
make router-init
make router-send FROM=atlas TO=forge SUMMARY='router smoke test' GOAL='reply with: router smoke ok' DELIVERABLE='exact phrase: router smoke ok'
make router-dispatch MAX_MESSAGES=1
make kanban-dispatcher-once DRY_RUN=1
```

**Expected:**

- Router message becomes `dispatched`.
- Kanban board contains a Forge task with `[router:<message-id>]` in the title.
- Dispatcher dry-run sees the task as dispatchable.

Do not run the worker until this dry-run passes.

---

### Task 8.3: Full one-agent execution smoke test

**Objective:** Prove a worker can consume a router-created Kanban task and return a bounded result.

**Command:**

```bash
make kanban-dispatcher-once MAX_TASKS=1
make kanban-list
```

**Expected:**

- Forge executes one small task.
- Task completes or blocks with a clear reason.
- No other agents are spawned.
- No Discord bot-to-bot chatter is required.

---

## Phase 9: Documentation and Guardrails

### Task 9.1: Update troubleshooting docs

**Objective:** Make the “Atlas summoned everyone but nobody answered” failure mode explicit.

**Files:**
- Modify: `README.md`
- Modify: `GETTING_STARTED.md`
- Modify: `docs/discord-kanban-operations.md`
- Modify: `docs/agent-message-router.md`

**Text to include:**

```markdown
If Atlas writes `@Vega @Forge ...` in Discord, that is not itself guaranteed work dispatch. Team Nexus uses the router/Kanban path for agent-to-agent work. Discord bot-to-bot message handling is intentionally not the primary bus because it can create loops and waste tokens.
```

---

### Task 9.2: Add validation to prevent unsafe Discord bot mode

**Objective:** Warn if `DISCORD_ALLOW_BOTS=all` appears in an agent env.

**Files:**
- Modify: `scripts/team_registry.py` or add a small validation helper if that is cleaner.
- Modify: tests for registry validation if present.

**Rule:**

- `DISCORD_ALLOW_BOTS=all` should fail validation or at least warn loudly.
- `DISCORD_ALLOW_BOTS=mentions` can pass with a warning that router/Kanban is preferred.

**Verification:**

```bash
make validate
```

---

## Acceptance Criteria

The router MVP is complete when:

1. `make router-init` creates `shared/router/messages.db`.
2. `make router-send FROM=atlas TO=forge ...` creates a pending message.
3. Invalid recipients and invalid routes are rejected.
4. TTL, trace, summary length, and body length limits are enforced.
5. `make router-dispatch MAX_MESSAGES=1` creates exactly one Kanban task for the target worker.
6. The router stores the Kanban task ID or a reliable source-message link.
7. `make kanban-dispatcher-once DRY_RUN=1` sees the generated task.
8. A full smoke test can complete one worker request without enabling Discord bot-to-bot chat.
9. Docs explain when to use router, when to use Kanban directly, and why Discord bot chatter is not the primary bus.
10. `make validate`, `make check-generated`, and `python3 -m pytest tests/test_team_message_router.py -q` pass.

---

## Open Questions To Resolve During Implementation

1. Does the installed Hermes `kanban create` support body/description/comment fields through CLI flags?
   - If yes, store the router prompt directly in the Kanban task.
   - If no, write `shared/project/artifacts/router/<message-id>.json` and put that path in the task title/body.

2. Should the route policy live in `shared/router/router-policy.yaml` or be folded into `shared/team-agents.yaml`?
   - Start separate to avoid bloating the registry.
   - Fold into the registry only if route policy becomes a first-class team property.

3. Should Atlas call `scripts/team-message-router.py` directly via terminal tools, or should the router become a Hermes tool/MCP later?
   - Start with CLI script for auditability.
   - Consider MCP/tool integration only after the protocol is stable.

4. Should worker-to-worker messages be allowed?
   - Not in MVP.
   - Add only specific routes backed by a use case, e.g. `forge -> sentinel` for code review requests.

---

## Recommended Execution Order

1. ADR and docs first.
2. Router policy and DB init.
3. Validation tests.
4. Send/list/inspect CLI.
5. Kanban materialization.
6. Make targets.
7. Atlas instruction updates.
8. Smoke tests.
9. Validation rule against unsafe Discord bot mode.

Keep commits small:

```bash
git commit -m "docs: record agent router architecture"
git commit -m "feat: add team message router storage"
git commit -m "feat: validate team message routes"
git commit -m "feat: materialize router messages as kanban tasks"
git commit -m "docs: document agent message router operations"
```
