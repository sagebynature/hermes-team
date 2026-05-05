# Discord + Kanban Agent Collaboration Implementation Plan

> For Hermes: Use subagent-driven-development skill to implement this plan task-by-task.

Goal: Make Team Nexus feel collaborative in Discord while keeping Kanban as the source of truth for delegation, status, dependencies, and handoffs.

Architecture: Discord is the human-facing mission room. Atlas is the only public Discord-facing coordinator by default. Atlas converts Discord requests into structured Kanban tasks, routes them to specialists, posts readable mission updates back to Discord, and synthesizes final output. Specialist collaboration happens through Kanban comments, task links, workspace artifacts, and bounded routed requests rather than open-ended Discord chatter.

Tech Stack: Hermes Agent gateway, Discord bot adapter, Hermes Kanban, Docker Compose, shared /shared/kanban SQLite board, per-agent workspaces, small host-side helper scripts, Makefile targets.

---

## Design principles

1. Discord should create a sense of team presence, not become the actual distributed state machine.
2. Kanban is the durable coordination layer: tasks, comments, dependencies, status, handoffs, blockers, and completion summaries.
3. Atlas owns user-facing synthesis. Workers can collaborate, but final external answers go through Atlas unless user explicitly asks otherwise.
4. Specialists should have personality and visibility in Discord without freely debating forever.
5. Every cross-agent message should be bounded: recipient, objective, expected output, constraints, ttl, and next action.
6. Runtime state stays out of git. Config, scripts, docs, and templates go in git.

## Target user experience

Discord channels:

- #nexus-command: user talks to Atlas. This is the main mission intake channel.
- #nexus-status: Atlas posts mission/task graph updates, blocked tasks, completions, and final summaries.
- #nexus-handoffs: Optional read-only-ish stream of compact specialist handoff summaries.
- #nexus-social or #nexus-lab: Optional low-stakes brainstorming channel where user can explicitly invite multi-agent discussion.

Normal mission flow:

1. user posts an objective in #nexus-command.
2. Atlas replies with a mission read and proposed task graph.
3. Atlas creates Kanban tasks assigned to specialists.
4. Router/dispatcher starts the relevant agent containers for ready tasks.
5. Specialists complete or block tasks through Kanban, adding comments and artifacts.
6. Atlas posts status updates to #nexus-status.
7. Atlas synthesizes final output back in #nexus-command.
8. Important deliverables are saved under each agent's /workspace/outbox or shared project docs as appropriate.

Collaboration feel without messy routing:

- Atlas announces who is working on what.
- Specialists add short, named comments to the task thread.
- Atlas can quote compact specialist notes in Discord updates.
- Specialists can request input from another role by asking Atlas to route a follow-up task.
- For deliberate roundtable moments, Atlas creates a bounded fan-out task and posts each specialist's short answer in a Discord thread.

---

## Phase 0: Confirm current baseline

### Task 0.1: Verify shared Kanban config

Objective: Confirm all agents already mount the same board and only Atlas dispatches.

Files:

- Read: docker-compose.yml
- Read: agents/\*/home/config.yaml

Steps:

1. Check every service has:
   - HERMES_KANBAN_HOME=/shared/kanban
   - ./shared/kanban:/shared/kanban
2. Check every config has root toolsets including hermes-cli and kanban.
3. Check only agents/atlas/home/config.yaml has kanban.dispatch_in_gateway: true.
4. Check every other agent has kanban.dispatch_in_gateway: false.

Verification commands:

```bash
cd ./team-nexus
make compose-config
make kanban-init
make kanban-stats
```

Expected:

- docker compose config succeeds.
- kanban init succeeds.
- stats can be read through Atlas.

### Task 0.2: Verify Discord gateway prerequisites

Objective: Make sure Atlas can receive Discord messages and post replies.

Files:

- Read: .env.example
- Do not print: .env
- Read: agents/atlas/home/config.yaml

Steps:

1. Confirm .env.example documents:
   - DISCORD_BOT_TOKEN
   - DISCORD_ALLOWED_USERS
   - DISCORD_HOME_CHANNEL
2. Confirm the real Discord bot has Message Content Intent enabled in the Discord Developer Portal.
3. Run Atlas gateway setup only if Discord is not configured:

```bash
docker compose run --rm atlas gateway setup
```

4. Start Atlas only for the first smoke test:

```bash
docker compose up -d atlas
```

5. In Discord, send Atlas a small test message in the intended command channel.

Expected:

- Atlas responds in Discord.
- agents/atlas/home/logs/gateway.log has no Discord auth/intents errors.

---

## Phase 1: Document the collaboration model

### Task 1.1: Add Discord operating model to README

Objective: Make it obvious how Discord and Kanban are supposed to interact.

Files:

- Modify: README.md, section "Agent-to-agent comms"

Add content covering:

- Discord is the mission room, not the task database.
- #nexus-command is for user -> Atlas intake.
- #nexus-status is for Atlas progress updates.
- #nexus-handoffs is for compact specialist handoffs.
- Kanban remains the source of truth.
- Atlas is the only default public coordinator.
- Direct multi-agent debate is opt-in and bounded.

Verification:

```bash
git diff -- README.md
```

Expected:

- README explains the human workflow without implying free peer-to-peer routing.

### Task 1.2: Add a shared team collaboration protocol

Objective: Give every agent the same collaboration rules in a reusable shared document.

Files:

- Create: shared/project/team-collaboration-protocol.md

Content outline:

```markdown
# Team Nexus Collaboration Protocol

## Source of truth

Kanban is the task/source-of-truth layer. Discord is the human visibility layer.

## Roles

Atlas routes and synthesizes. Specialists execute, review, and request routed support.

## Message shape

Every inter-agent request includes id, conversation_id, from, to, objective, constraints, expected_output, ttl, and next_action.

## Collaboration modes

- Mission graph
- Specialist handoff
- Review gate
- Roundtable
- Blocked task escalation

## Discord etiquette

- Keep public updates short.
- Do not dump raw transcripts.
- Post artifacts by path and summary.
- Ask Atlas for routing rather than starting side conversations.
```

Verification:

```bash
git diff -- shared/project/team-collaboration-protocol.md
```

Expected:

- The protocol is readable by every agent through /shared/project.

### Task 1.3: Add the protocol reference to agent instructions

Objective: Ensure agents know to consult the shared protocol.

Files:

- Modify: agents/atlas/home/AGENTS.md
- Modify: agents/vega/home/AGENTS.md
- Modify: agents/scout/home/AGENTS.md
- Modify: agents/forge/home/AGENTS.md
- Modify: agents/lumen/home/AGENTS.md
- Modify: agents/blitz/home/AGENTS.md
- Modify: agents/ledger/home/AGENTS.md
- Modify: agents/sentinel/home/AGENTS.md

Add a short line to the shared Startup Team Protocol section:

```markdown
- Follow `/shared/project/team-collaboration-protocol.md`; Discord is for human-visible updates, while Kanban is the durable source of truth.
```

Verification:

```bash
grep -R "team-collaboration-protocol" agents/*/home/AGENTS.md
```

Expected:

- All eight AGENTS.md files reference the protocol.

---

## Phase 2: Make Atlas create collaborative mission updates

### Task 2.1: Add Atlas Discord mission update rules

Objective: Atlas should make work feel collaborative by narrating task graph, status, and handoffs.

Files:

- Modify: agents/atlas/home/AGENTS.md

Add rules:

```markdown
Discord collaboration rules:

- When user gives a multi-agent mission, first post a compact mission read and proposed task graph.
- After creating Kanban tasks, post assignments with assignee, objective, dependency, and expected deliverable.
- Post progress updates when tasks block or complete; keep them short and link/summarize the Kanban task ID.
- For final answers, synthesize specialist outputs into one recommendation and include who contributed.
- For deliberate roundtables, create bounded specialist tasks and summarize each viewpoint; do not let agents debate indefinitely.
```

Verification:

```bash
git diff -- agents/atlas/home/AGENTS.md
```

Expected:

- Atlas has explicit Discord collaboration behavior.

### Task 2.2: Add specialist handoff style to all workers

Objective: Specialists should produce compact handoffs that Atlas can quote in Discord.

Files:

- Modify: agents/vega/home/AGENTS.md
- Modify: agents/scout/home/AGENTS.md
- Modify: agents/forge/home/AGENTS.md
- Modify: agents/lumen/home/AGENTS.md
- Modify: agents/blitz/home/AGENTS.md
- Modify: agents/ledger/home/AGENTS.md
- Modify: agents/sentinel/home/AGENTS.md

Add output rule:

```markdown
For Kanban handoffs, include a Discord-ready summary no longer than 5 bullets: contribution, recommendation, risks, artifact paths, and requested next reviewer if any.
```

Verification:

```bash
grep -R "Discord-ready summary" agents/*/home/AGENTS.md
```

Expected:

- Every worker has the handoff rule.

---

## Phase 3: Add Compose-aware Kanban dispatch

Context: Hermes' built-in Kanban dispatcher runs `hermes -p <assignee> ...`, which assumes assignees are profiles inside the dispatcher container. Team Nexus uses one Compose service/home per agent. We need a compatibility layer so assignee=forge routes to the forge service.

### Task 3.1: Create agent registry

Objective: Define the canonical agent names, service names, roles, and Discord visibility labels in one file.

Files:

- Create: shared/team-agents.yaml

Initial content:

```yaml
agents:
  atlas:
    service: atlas
    display_name: Atlas
    role: Orchestrator / Chief of Staff
    gateway_port: 8642
    discord_visible: true
  vega:
    service: vega
    display_name: Vega
    role: Product Strategist
    gateway_port: 8643
    discord_visible: true
  scout:
    service: scout
    display_name: Scout
    role: Market + Customer Research
    gateway_port: 8644
    discord_visible: true
  forge:
    service: forge
    display_name: Forge
    role: Engineering Lead
    gateway_port: 8645
    discord_visible: true
  lumen:
    service: lumen
    display_name: Lumen
    role: UX / Design Lead
    gateway_port: 8646
    discord_visible: true
  blitz:
    service: blitz
    display_name: Blitz
    role: Growth + GTM
    gateway_port: 8647
    discord_visible: true
  ledger:
    service: ledger
    display_name: Ledger
    role: Finance + Ops
    gateway_port: 8648
    discord_visible: true
  sentinel:
    service: sentinel
    display_name: Sentinel
    role: Code Review / QA / Security Assessment
    gateway_port: 8649
    discord_visible: true
```

Verification:

```bash
python3 - <<'PY'
import yaml
from pathlib import Path
p = Path('shared/team-agents.yaml')
data = yaml.safe_load(p.read_text())
assert set(data['agents']) == {'atlas','vega','scout','forge','lumen','blitz','ledger','sentinel'}
for slug, agent in data['agents'].items():
    assert agent['service'] == slug
print('agent registry OK')
PY
```

Expected:

- agent registry OK.

### Task 3.2: Create a dispatcher wrapper script

Objective: Provide one command that runs a Kanban task in the correct Compose service.

Files:

- Create: scripts/kanban-dispatch-compose.sh

Behavior:

- Usage: scripts/kanban-dispatch-compose.sh <assignee> <task_id>
- Validate assignee against shared/team-agents.yaml or TEAM_AGENTS in Makefile.
- Run:

```bash
docker compose run --rm <assignee> chat -q "work kanban task <task_id>"
```

- Pass HERMES_KANBAN_HOME through Compose as already configured.
- Print assignee, task ID, start time, exit code.

Verification:

```bash
scripts/kanban-dispatch-compose.sh forge TEST_TASK_ID_SHOULD_NOT_EXIST
```

Expected:

- It starts the forge service and Hermes exits cleanly or reports task not found; the script itself validates routing.

### Task 3.3: Add Makefile helper for manual dispatch smoke tests

Objective: Let user manually dispatch one task to one agent before automating.

Files:

- Modify: Makefile

Add phony target:

```make
kanban-dispatch: guard-agent ## Run one Kanban task in the assigned agent container: make kanban-dispatch AGENT=forge TASK=K...
	@if [ -z "$(TASK)" ]; then echo "TASK is required" >&2; exit 2; fi
	./scripts/kanban-dispatch-compose.sh $(AGENT) $(TASK)
```

Verification:

```bash
make help | grep kanban-dispatch
```

Expected:

- target appears in help.

### Task 3.4: Decide automation strategy

Objective: Choose between patching/upstreaming Hermes dispatch or running a sidecar dispatcher.

Preferred first implementation: sidecar dispatcher script, because it avoids modifying Hermes internals while we validate behavior.

Options:

A. Sidecar poller:

- Create `scripts/kanban-compose-dispatcher.py`.
- Poll shared Kanban DB/CLI for ready tasks.
- Claim task if assignee maps to a Compose service.
- Spawn `docker compose run --rm <service> chat -q "work kanban task <id>"`.
- Log to shared/kanban/dispatcher.log.

B. Hermes patch:

- Add config setting for dispatch command template.
- Example: `kanban.dispatch_command: docker compose run --rm {assignee} chat -q "work kanban task {task_id}"`.
- Upstream as generic feature.

Recommendation:

- Implement A first for Team Nexus.
- Later upstream B to Hermes if the pattern is stable.

Verification:

- A ready task assigned to Forge is claimed, run inside forge, and completed or blocked.

---

## Phase 4: Add Discord status publishing

### Task 4.1: Determine send-message path

Objective: Decide how Atlas posts status updates to Discord.

Options:

1. Native Hermes gateway send_message tool from Atlas when available.
2. Discord webhook URL for #nexus-status.
3. Gateway API call to Atlas' own gateway.

Recommendation:

- Use Discord webhook for automated status posts because it is simple, channel-scoped, and does not require giving every worker Discord tool access.
- Keep only Atlas connected as the interactive Discord bot.

Files:

- Modify: .env.example

Add:

```bash
DISCORD_STATUS_WEBHOOK_URL=
DISCORD_HANDOFFS_WEBHOOK_URL=
```

Do not commit real webhook values.

Verification:

```bash
git diff -- .env.example
```

Expected:

- env example documents optional webhook URLs.

### Task 4.2: Create Discord status poster helper

Objective: Let scripts/Atlas post compact updates to Discord without exposing full bot control.

Files:

- Create: scripts/discord-post-status.py

Behavior:

- Read webhook URL from DISCORD_STATUS_WEBHOOK_URL or DISCORD_HANDOFFS_WEBHOOK_URL.
- Accept stdin or --message.
- Reject messages over a safe length, e.g. 1800 chars.
- Never print webhook URL.
- Use Python stdlib urllib.request or requests if already available.

Verification:

```bash
printf 'Team Nexus status smoke test' | DISCORD_STATUS_WEBHOOK_URL='https://discord.com/api/webhooks/placeholder' python3 scripts/discord-post-status.py --dry-run
```

Expected:

- Dry run prints the message payload without secret values.

### Task 4.3: Add Makefile helper for status post dry run

Objective: Make status posting testable without memorizing script flags.

Files:

- Modify: Makefile

Add:

```make
discord-status-dry-run: ## Dry-run a Discord status post: make discord-status-dry-run MESSAGE='...'
	@if [ -z "$(MESSAGE)" ]; then echo "MESSAGE is required" >&2; exit 2; fi
	printf '%s' "$(MESSAGE)" | python3 scripts/discord-post-status.py --dry-run
```

Verification:

```bash
make discord-status-dry-run MESSAGE='hello from Team Nexus'
```

Expected:

- Dry-run payload is printed.

---

## Phase 5: Make collaboration visible but bounded

### Task 5.1: Add mission thread convention

Objective: Give each multi-agent mission a Discord thread and matching Kanban conversation ID.

Files:

- Modify: shared/project/team-collaboration-protocol.md
- Modify: agents/atlas/home/AGENTS.md

Convention:

- Atlas creates or reuses a Discord thread for each mission when possible.
- Thread title format: `mission: <short-name>`.
- Kanban task bodies include `conversation_id: mission_<slug>_<yyyymmdd>`.
- Atlas posts task graph and final synthesis in the mission thread.
- Status channel gets compact milestones only.

Verification:

```bash
git diff -- shared/project/team-collaboration-protocol.md agents/atlas/home/AGENTS.md
```

Expected:

- Mission thread convention is documented.

### Task 5.2: Define collaboration patterns

Objective: Make collaboration more than isolated assignments.

Files:

- Modify: shared/project/team-collaboration-protocol.md

Add patterns:

1. Fan-out/fan-in:
   - Atlas asks multiple specialists independently.
   - Atlas synthesizes.

2. Review gate:
   - Forge implements or proposes technical plan.
   - Sentinel reviews quality/security/release readiness.

3. Product/engineering handshake:
   - Vega defines scope.
   - Forge estimates/implements.
   - Vega accepts or cuts scope.

4. Design/product/growth loop:
   - Lumen designs concept.
   - Vega checks product fit.
   - Blitz checks GTM/message fit.

5. Blocked-task escalation:
   - Specialist blocks task with exact question.
   - Atlas asks user or routes to another specialist.

6. Roundtable:
   - Atlas creates one short task per relevant role.
   - Each answer limited to 5 bullets.
   - Atlas summarizes disagreements and recommends a decision.

Verification:

```bash
git diff -- shared/project/team-collaboration-protocol.md
```

Expected:

- Protocol describes reusable collaboration patterns.

### Task 5.3: Add Kanban comment conventions

Objective: Make the board readable as a collaboration transcript.

Files:

- Modify: shared/project/team-collaboration-protocol.md

Comment types:

```text
[handoff] Summary of completed contribution and artifact paths.
[question] Specific question that blocks progress.
[review] Approval, requested changes, or risk note.
[decision] Decision made by Atlas or user.
[status] Short progress update.
```

Verification:

```bash
git diff -- shared/project/team-collaboration-protocol.md
```

Expected:

- Agents have a predictable comment vocabulary.

---

## Phase 6: End-to-end validation mission

### Task 6.1: Create a synthetic cross-functional mission

Objective: Test Discord intake, Atlas decomposition, Kanban tasks, worker dispatch, comments, status updates, and final synthesis.

Mission prompt in Discord #nexus-command:

```text
Atlas, run a bounded Team Nexus roundtable: Should we prioritize a public dashboard for Team Nexus next? Ask Vega, Forge, Lumen, Blitz, Ledger, and Sentinel for 5-bullet input, then synthesize a recommendation. Keep this as a dry-run planning mission; no code changes.
```

Expected task graph:

- Vega: product value and scope
- Forge: implementation effort and architecture risks
- Lumen: UX implications
- Blitz: positioning and adoption angle
- Ledger: cost/ops impact
- Sentinel: security/privacy/release risks
- Atlas: synthesis

Verification:

```bash
make kanban-list
make kanban-stats
```

Expected:

- Tasks are visible on the shared board.
- Workers complete or block with compact summaries.
- Atlas posts a synthesis in Discord.

### Task 6.2: Review logs and tighten rules

Objective: Catch loops, noisy posts, missing handoffs, or unclear ownership.

Files:

- Read: agents/\*/home/logs/gateway.log
- Read: shared/kanban/dispatcher.log if sidecar exists
- Modify: shared/project/team-collaboration-protocol.md if needed
- Modify: agents/\*/home/AGENTS.md if needed

Checks:

- Did any agent talk directly to Discord when it should not?
- Did any specialist request another specialist through Atlas?
- Were comments useful and compact?
- Did Atlas synthesize rather than paste raw output?
- Did any task lack expected_output or next_action?

Verification:

```bash
git diff
```

Expected:

- Any protocol fixes are small and explicit.

---

## Rollout order

1. Confirm Discord works with Atlas only.
2. Document collaboration model and update agent instructions.
3. Add registry + manual Compose dispatch helper.
4. Run one manual Kanban task assigned to Forge.
5. Add sidecar dispatch automation.
6. Add Discord status webhook helper.
7. Run synthetic roundtable mission.
8. Tune protocol based on the observed behavior.

## Open decisions

1. Should all specialists have Discord bot connectivity, or should only Atlas be Discord-facing?
   - Recommendation: only Atlas interactive at first; webhook status posts can represent the team.

2. Should status updates go to one channel or separate status/handoffs channels?
   - Recommendation: start with #nexus-status only; add #nexus-handoffs if updates get noisy.

3. Should Compose dispatch be implemented as a sidecar first or upstream Hermes command-template support?
   - Recommendation: sidecar first, upstream later.

4. How much personality should specialists show in public updates?
   - Recommendation: named, concise, and opinionated summaries; no autonomous banter unless user asks for a roundtable.

## Success criteria

- user can ask Atlas for a multi-agent mission in Discord.
- Atlas creates a visible task graph with real specialist assignments.
- At least one specialist task runs in the correct Compose service from the shared Kanban board.
- Specialists produce Discord-ready handoffs and durable artifact paths.
- Atlas posts progress and final synthesis to Discord.
- The shared Kanban board remains the authoritative record.
- No uncontrolled peer-to-peer loops or duplicate task claims occur.
