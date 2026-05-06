# Discord + Kanban Operations

This document explains how Team Nexus runs inter-agent collaboration through Discord and Hermes Kanban.

## Operating model

Team Nexus uses three layers:

1. Discord is the human-facing mission room.
2. Kanban is the durable coordination/source-of-truth layer.
3. Docker Compose is the execution substrate: one service per Hermes agent.

Atlas remains the default coordinator and synthesizer. Specialists receive bounded Kanban work, complete it, add handoff comments/artifacts, and let Atlas synthesize the result back to the user.

## What is already wired

Every agent service in `docker-compose.yml` sets:

```yaml
HERMES_HOME: /opt/data
HERMES_KANBAN_HOME: /shared/kanban
```

Every agent mounts:

```text
./agents/<agent>/home      -> /opt/data
./agents/<agent>/workspace -> /workspace
./shared/project           -> /shared/project:ro
./shared/project/artifacts -> /shared/project/artifacts:rw  # writable cross-agent handoffs
./shared/kanban            -> /shared/kanban:rw
./shared/skills            -> /shared/skills:ro
./shared/mcp               -> /shared/mcp:ro
```

The Compose manifest uses shorthand bind mounts with explicit `:ro` or `:rw` suffixes for these shared paths. The only writable submount under `/shared/project` is `/shared/project/artifacts`; do not make the rest of `/shared/project`, `/shared/skills`, or `/shared/mcp` writable unless you are deliberately changing the team security boundary.

The shared Kanban database lives on the host at:

```text
shared/kanban/kanban.db
```

Inside containers, that path is:

```text
/shared/kanban/kanban.db
```

Every agent has the `kanban` toolset enabled. Every embedded Hermes gateway Kanban dispatcher is disabled:

```yaml
kanban:
  dispatch_in_gateway: false
```

This is intentional. Team Nexus uses an explicit Compose-aware dispatcher instead.

## Does Kanban autostart?

Kanban itself is not a long-running server. It is a shared SQLite-backed board plus Hermes CLI/tooling.

Initialize it once from the repo root:

```bash
make kanban-init
```

That runs:

```bash
docker compose run --rm atlas kanban init
```

After initialization, the board exists as `shared/kanban/kanban.db`. If that file already exists, Kanban is already initialized.

The Kanban background services are separate. They do not run with a plain `docker compose up -d`; start them explicitly through the Docker Compose `kanban` profile. The `kanban-dispatcher` launches worker tasks, while the `kanban-notifier` tails mission events and queues or posts progress updates.

## Starting Team Nexus

From the repo root:

```bash
cd ./team-nexus
```

First-time or clean setup:

```bash
cp .env.example .env
# edit .env with real values
make workspace-init
make build
make compose-config
make kanban-init
```

Start the Hermes gateways:

```bash
make up
```

or directly:

```bash
docker compose up -d
```

Atlas and the specialists run `hermes gateway run` inside their containers. Atlas is the primary Discord-facing coordinator.

Check Kanban:

```bash
make kanban-stats
make kanban-list
```

Start automatic worker dispatch as the Dockerized dispatcher daemon:

```bash
make kanban-dispatcher-daemon
```

This starts the `kanban-dispatcher` service through the Compose `kanban` profile:

```bash
docker compose --profile kanban up -d kanban-dispatcher
```

Stop it with:

```bash
make kanban-dispatcher-stop
```

Follow logs with:

```bash
make kanban-dispatcher-logs
```

## Dispatcher modes

Safe dry-run, no worker launch and no mutation:

```bash
make kanban-dispatcher-once DRY_RUN=1
```

One real dispatcher pass:

```bash
make kanban-dispatcher-once
```

Continuous dispatcher loop:

```bash
make kanban-dispatcher-daemon
```

With explicit interval, concurrency limit, and worker timeout:

```bash
KANBAN_DISPATCH_INTERVAL=60 KANBAN_DISPATCH_MAX_TASKS=1 KANBAN_DISPATCH_WORKER_TIMEOUT=900 make kanban-dispatcher-daemon
```

Manual dispatch of one task:

```bash
make kanban-dispatch AGENT=forge TASK=<task-id>
```

The Compose-aware dispatcher reads `shared/team-agents.yaml` to map a Kanban assignee like `forge` to the Docker Compose service named `forge`.

For automatic dispatch, the dispatcher first claims the selected ready task in the shared Kanban database. That makes the lifecycle visible as:

```text
todo -> ready -> running -> done
```

The claim writes a `claimed` event, sets `tasks.started_at`, creates a running `task_runs` row, and moves the task to `running` / IN PROGRESS before the worker container starts. Then the dispatcher runs:

```bash
docker compose run --rm forge chat -q "work kanban task <task-id>"
```

If the worker command exits non-zero while the dispatcher-created claim is still active, the dispatcher records a `dispatch_failed` event, closes the failed run as `spawn_failed`, and requeues the task back to `ready` for a later retry.

If a worker exceeds `KANBAN_DISPATCH_WORKER_TIMEOUT` / `--worker-timeout` (default 900 seconds), the dispatcher kills the named one-off worker container, records a `dispatch_timed_out` event, closes the run as `timed_out`, and moves the task to `blocked` instead of requeueing it. This prevents an agent/model/tool loop from being relaunched forever; an operator should inspect, split, or unblock the task deliberately.

The `kanban-dispatcher` container uses Docker-outside-of-Docker: it mounts the host Docker socket and the repo at `./team-nexus`, then runs nested `docker compose run --rm <agent> ...` commands against the host Docker daemon.

Dispatcher logs go to:

```text
shared/kanban/dispatcher.log
```

## Mission notifier and Atlas fan-in

Do not make Atlas periodically scan the whole board. Team Nexus uses Kanban events as the progress signal. `scripts/kanban-mission-notifier.py` tails new `task_events` rows by cursor, writes idempotent rows to `mission_notification_outbox`, and creates one Atlas synthesis task when all worker tasks in a mission are terminal.

A mission task must include a conversation ID in its title or body:

```text
[mission:mission_<slug>_<yyyymmdd>] <short objective>

conversation_id: mission_<slug>_<yyyymmdd>
objective: ...
expected_output: ...
artifact_path: /shared/project/artifacts/missions/mission_<slug>_<yyyymmdd>/<agent>.md
```

Process newly appended events once:

```bash
make kanban-notifier-once
```

Preview pending Discord status deliveries without posting:

```bash
make kanban-notifier-dry-run
```

Deliver pending outbox rows through `scripts/discord-post-status.py` and `DISCORD_STATUS_WEBHOOK_URL`:

```bash
make kanban-notifier-deliver
```

Run the notifier as a lightweight Dockerized daemon:

```bash
make kanban-notifier-daemon
```

That starts the `kanban-notifier` service through the Compose `kanban` profile:

```bash
docker compose --profile kanban up -d kanban-notifier
```

The daemon is intentionally separate from the worker dispatcher. The dispatcher launches workers; the notifier tails mission events, queues status updates, and optionally delivers those updates. The notifier service does not mount the Docker socket and cannot spawn workers.

### Notifier setup checklist

1. Initialize the shared board if needed:

   ```bash
   make kanban-init
   test -f shared/kanban/kanban.db
   ```

2. Decide whether the daemon should only queue outbox rows or also post Discord status updates.

   Queue-only mode is the safest default. It requires no webhook secret and is what the Compose service does unless configured otherwise:

   ```bash
   make kanban-notifier-daemon
   make kanban-notifier-dry-run
   make kanban-notifier-deliver
   ```

   Auto-delivery mode requires `DISCORD_STATUS_WEBHOOK_URL` in repo-root `.env` and `KANBAN_NOTIFIER_DELIVER=1` for the daemon environment. Do not print the webhook value.

   ```bash
   # .env
   DISCORD_STATUS_WEBHOOK_URL=<redacted Discord webhook URL>
   KANBAN_NOTIFIER_DELIVER=1
   KANBAN_NOTIFIER_INTERVAL=10
   KANBAN_NOTIFIER_LIMIT=100
   ```

3. Start or restart the daemon after changing `.env`:

   ```bash
   make kanban-notifier-daemon
   # or, after env changes:
   docker compose --profile kanban up -d --force-recreate kanban-notifier
   ```

4. Verify the service and log file:

   ```bash
   docker compose --profile kanban ps kanban-notifier
   make kanban-notifier-logs
   tail -f shared/kanban/mission-notifier.log
   ```

5. Stop it when needed:

   ```bash
   make kanban-notifier-stop
   ```

The default daemon interval is 10 seconds. Override with `KANBAN_NOTIFIER_INTERVAL=<seconds>` in `.env`. The default per-pass event limit is 100. Override with `KANBAN_NOTIFIER_LIMIT=<count>` in `.env`.

The notifier reacts to:

- `blocked` / `dispatch_timed_out`: queue a human blocker update.
- `completed` / `done` on worker tasks: queue a compact completion update.
- all non-Atlas worker tasks for a `conversation_id` reaching `done` or `archived`: create exactly one ready Atlas task with idempotency key `mission:<conversation_id>:atlas-synthesis`.
- `completed` / `done` on the Atlas synthesis task: queue a final-response-ready update.

The notifier is deterministic infrastructure. It does not invent specialist conclusions; Atlas still owns final synthesis from Kanban task results/comments and artifacts.

The operational skill for this workflow is tracked in the repo at `shared/skills/team-nexus-kanban-ops/SKILL.md`. It is an operator/developer runbook, not an Atlas runtime skill: Atlas runs inside Docker and should not be expected to run host `make` or `docker compose` commands. Atlas-facing behavior belongs in `agents/atlas/home/AGENTS.md` and in the Kanban task bodies it receives.

Notifier state and outbox rows live in the shared Kanban DB:

```text
mission_notifier_state
mission_notification_outbox
```

Notifier logs go to:

```text
shared/kanban/mission-notifier.log
```

## Creating and watching tasks

Create a task:

```bash
make kanban-create TITLE="Draft public dashboard scope" ASSIGNEE=vega
```

Link an existing parent task to a child task dependency:

```bash
make kanban-link PARENT=<parent-task-id> CHILD=<child-task-id>
```

Atlas should use task dependencies for mission routes rather than only describing order in Discord. Parent work should produce a compact `[handoff]` comment and artifact path before child work starts.

List tasks:

```bash
make kanban-list
```

Watch Kanban events:

```bash
make kanban-watch
```

Show summary counts:

```bash
make kanban-stats
```

## Atlas deep interview and mission routes

Atlas should classify each meaningful new Discord mission before acting:

- `direct-answer`: answer directly; no Kanban fan-out.
- `clarify-first`: ask a bounded set of numbered questions before routing.
- `route-ready`: draft a mission route and ask for approval, or proceed if user already authorized execution.
- `user-decision-required`: ask user to choose between meaningful tradeoffs.

For ambiguous missions, Atlas asks 3-7 numbered questions in one pass, labels each as required or optional, and proposes defaults for low-stakes choices. Atlas should stop interviewing once it can safely route the work, then record any remaining assumptions in the route.

For multi-agent work, Atlas should post a compact mission route before creating tasks. The route should include:

- `conversation_id`, usually `mission_<slug>_<yyyymmdd>`.
- Objective, success criteria, assumptions, and excluded scope.
- Task graph with assignee, objective, dependency, expected output, artifact path, and review gate.
- Specialist rationale: why each selected agent is involved.
- Final synthesis plan owned by Atlas.

Template:

```text
Mission route proposed: <mission>
conversation_id: <id>
Tasks:
- Vega: <objective> (depends: none, artifact: /shared/project/artifacts/<mission>/vega-*.md)
- Scout: <objective> (depends: Vega, artifact: /shared/project/artifacts/<mission>/scout-*.md)
- Forge: <objective> (depends: Vega, artifact: /shared/project/artifacts/<mission>/forge-*.md)
- Sentinel: <review objective> (depends: Forge, artifact: /shared/project/artifacts/<mission>/sentinel-*.md)
Final: Atlas synthesis after required handoffs land.
```

Shared route template for durable artifacts:

```text
shared/project/atlas-mission-route-template.md
```

When executing a route, Atlas can create child tasks with parents directly:

```bash
docker compose run --rm atlas kanban create "Define scope" --assignee vega --body "..." --json
docker compose run --rm atlas kanban create "Design implementation" --assignee forge --parent <vega-task-id> --body "..." --json
```

Or link tasks after creation:

```bash
make kanban-link PARENT=<parent-task-id> CHILD=<child-task-id>
```

Remember: the board exists after `make kanban-init`, but automatic worker dispatch only runs when the kanban profile is started with `make kanban-dispatcher-daemon` or an equivalent `docker compose --profile kanban ...` command.

## Discord setup

In the Discord Developer Portal:

1. Create or select the Team Nexus bot.
2. Copy the bot token into `.env` as `DISCORD_BOT_TOKEN`.
3. Enable Message Content Intent.
4. Invite the bot to the Team Nexus server.
5. Get your Discord user ID and set `DISCORD_ALLOWED_USERS`.
6. Get the `#nexus-command` channel ID and set `DISCORD_HOME_CHANNEL`.

Recommended channels:

```text
#nexus-command   user talks to Atlas
#nexus-status    compact status updates
#nexus-handoffs  optional specialist handoffs/escalations
#nexus-lab       optional bounded roundtables/brainstorming
```

Status and handoff webhooks are optional. They mirror important events to Discord, but Kanban remains the source of truth.

## Kanban comment prefixes

Use these prefixes consistently so Atlas can reconstruct a mission from the board and quote compact updates back into Discord:

```text
[handoff] producer=<agent> consumer=<agent|atlas> artifact=/shared/project/artifacts/<file> summary=<one sentence> next=<optional task/reviewer>
[decision] owner=<atlas|user> decision=<one sentence> rationale=<why> artifact=/shared/project/artifacts/<optional memo>
```

Rules:

- Use `[handoff]` whenever one agent creates something another agent should consume.
- Cross-agent handoff artifacts must live under `/shared/project/artifacts`; private `/workspace` files are not sufficient for downstream agents.
- Use `[decision]` for Atlas/user decisions, especially final syntheses or scope calls.
- If the rationale is longer than one sentence, write a memo or synthesis artifact and point the `[decision]` comment at it.
- Keep Discord posts short; link the Kanban task and artifact path instead of dumping long content.

## Environment variables

Values live in the repo-root `.env`, loaded by every Compose service via `env_file: ./.env`.

Do not commit real secret values.

### Minimum practical set

```bash
OPENROUTER_API_KEY=
DISCORD_BOT_TOKEN=
DISCORD_ALLOWED_USERS=
DISCORD_HOME_CHANNEL=
```

`OPENROUTER_API_KEY` is required because the current agent configs use OpenRouter as the model provider.

`DISCORD_BOT_TOKEN` lets the Hermes Discord gateway log in as the bot.

`DISCORD_ALLOWED_USERS` restricts who can command the bot.

`DISCORD_HOME_CHANNEL` sets the default Discord command channel.

### Optional provider/model keys

```bash
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
```

Use these if agent configs switch providers or auxiliary tooling needs them.

### Optional Discord webhook keys

```bash
DISCORD_STATUS_WEBHOOK_URL=
DISCORD_HANDOFFS_WEBHOOK_URL=
```

These are used by `scripts/discord-post-status.py` for compact status/handoff posts. They are not required for the bot itself.

Test webhook payload formatting without sending:

```bash
make discord-status-dry-run MESSAGE='hello from Team Nexus'
```

### Optional dispatcher tuning keys

```bash
KANBAN_DISPATCH_INTERVAL=60
KANBAN_DISPATCH_MAX_TASKS=1
KANBAN_DISPATCH_WORKER_TIMEOUT=900
```

These tune the Dockerized `kanban-dispatcher` service. They are optional; defaults are 60 seconds, 1 task per pass, and a 900-second worker timeout.

### Optional tool/integration keys

```bash
GITHUB_TOKEN=
GATEWAY_API_KEY=
EXA_API_KEY=
PARALLEL_API_KEY=
TAVILY_API_KEY=
FIRECRAWL_API_KEY=
FIRECRAWL_API_URL=
TINKER_API_KEY=
WANDB_API_KEY=
```

Set only what the team needs.

`GITHUB_TOKEN` is needed for GitHub API/repo operations.

`GATEWAY_API_KEY` protects or authenticates gateway API access if configured.

The search/extraction/ML keys are optional integrations.

## First live test

1. Start gateways:

   ```bash
   make up
   ```

2. Confirm board health:

   ```bash
   make kanban-stats
   ```

3. Start dispatcher:

   ```bash
   make kanban-dispatcher-daemon
   ```

4. In Discord `#nexus-command`, ask Atlas for a bounded test mission:

   ```text
   Atlas, run a bounded Team Nexus roundtable: Should we prioritize a public dashboard for Team Nexus next? Ask Vega, Forge, Lumen, Blitz, Ledger, and Sentinel for 5-bullet input, then synthesize a recommendation. Keep this as a dry-run planning mission; no code changes.
   ```

5. Watch progress:

   ```bash
   make kanban-list
   make kanban-watch
   ```

## Important guardrails

- Discord is the radio, not the database.
- Kanban and workspace files are the record.
- Atlas owns user-facing synthesis by default.
- Specialists should produce bounded handoffs, not endless peer debate.
- Do not enable Hermes embedded Kanban gateway dispatch while the Compose-aware dispatcher is active.
- Do not expose tokens, webhook URLs, auth files, or private logs in Discord or committed docs.
