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
./shared/kanban            -> /shared/kanban
./shared/skills            -> /shared/skills:ro
./shared/mcp               -> /shared/mcp:ro
```

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

The automatic dispatcher is separate. It does not run with the plain gateway stack; start it explicitly through the Docker Compose `dispatcher` profile.

## Starting Team Nexus

From the repo root:

```bash
cd /Users/sage/team-nexus
```

First-time or clean setup:

```bash
cp .env.example .env
# edit .env with real values
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

This starts the `kanban-dispatcher` service through the Compose `dispatcher` profile:

```bash
docker compose --profile dispatcher up -d kanban-dispatcher
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

With explicit interval and concurrency limit:

```bash
KANBAN_DISPATCH_INTERVAL=60 KANBAN_DISPATCH_MAX_TASKS=1 make kanban-dispatcher-daemon
```

Manual dispatch of one task:

```bash
make kanban-dispatch AGENT=forge TASK=<task-id>
```

The Compose-aware dispatcher reads `shared/team-agents.yaml` to map a Kanban assignee like `forge` to the Docker Compose service named `forge`, then runs:

```bash
docker compose run --rm forge chat -q "work kanban task <task-id>"
```

The `kanban-dispatcher` container uses Docker-outside-of-Docker: it mounts the host Docker socket and the repo at `/Users/sage/team-nexus`, then runs nested `docker compose run --rm <agent> ...` commands against the host Docker daemon.

Dispatcher logs go to:

```text
shared/kanban/dispatcher.log
```

## Creating and watching tasks

Create a task:

```bash
make kanban-create TITLE="Draft public dashboard scope" ASSIGNEE=vega
```

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
```

These tune the Dockerized `kanban-dispatcher` service. They are optional; defaults are 60 seconds and 1 task per pass.

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
