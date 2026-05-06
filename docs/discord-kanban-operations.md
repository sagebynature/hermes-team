# Discord + Kanban operations

This document describes the current profile-driven Team Nexus collaboration model.

## Operating model

Team Nexus uses three layers:

1. Discord is the human-facing mission room.
2. Kanban is the durable coordination/source-of-truth layer.
3. Docker Compose provides functional runtime services for Hermes profiles.

Atlas is the only Discord-facing gateway in v1. Forge, Sentinel, Scribe, and Curator are specialist Hermes profiles dispatched through Kanban. Workers do not chat with each other in Discord by default.

Flow:

```text
User -> Atlas Discord gateway -> Kanban task graph -> worker profiles -> Kanban evidence -> Atlas synthesis -> User
```

## What is wired

The profile-driven Compose runtime is `docker-compose.profiles.yml`.

Core service:

```text
atlas-gateway  HERMES_HOME=/opt/data/profiles/atlas  command=gateway run
```

Optional function services:

```text
dashboard           Atlas profile dashboard/control plane
admin-shell         operator shell with a selected profile home
kanban-dispatcher   one-shot native dispatcher nudge
```

Runtime mounts:

```text
runtime/hermes             -> /opt/data
repo root                  -> /workspace
shared/skills              -> /shared/skills:ro
shared/mcp                 -> /shared/mcp:ro
shared/plugins             -> /opt/data/plugins:ro
shared/dashboard-themes    -> /opt/data/dashboard-themes:ro
```

The shared Kanban database lives under the ignored runtime tree:

```text
runtime/hermes/kanban/kanban.db
```

Inside containers, that path is resolved through:

```text
HERMES_KANBAN_HOME=/opt/data/kanban
```

## Does Kanban autostart?

Kanban itself is not a long-running server. It is a shared SQLite-backed board plus Hermes CLI/tooling.

Initialize it once:

```bash
make kanban-init
```

Inspect it:

```bash
make kanban-stats
make kanban-list
make kanban-watch
```

The Atlas gateway is the long-running process. Start it with:

```bash
make up
```

## Dispatcher modes

Preview one native dispatch pass without worker launch:

```bash
make kanban-dispatcher-once DRY_RUN=1
```

Run one dispatch pass:

```bash
make kanban-dispatcher-once
```

Start/stop the gateway-hosted dispatcher runtime:

```bash
make kanban-dispatcher-daemon
make kanban-dispatcher-stop
```

Follow logs:

```bash
make kanban-dispatcher-logs
```

`KANBAN_DISPATCH_MAX_TASKS` controls the one-shot cap:

```bash
MAX_TASKS=3 make kanban-dispatcher-once
```

## Mission task contract

Team Nexus treats the mission contract as required evidence, not prompt style. Use `make kanban-create` so title/body include the required identifiers.

Required title shape:

```text
[mission:<conversation_id>] <short objective>
```

Required body fields:

```text
conversation_id: <conversation_id>
reply_mode: kanban_only
reply_expected: false
from: atlas
to: <profile>
assignee: <profile>
<objective and constraints>
```

Create a task:

```bash
make kanban-create TITLE='Implement login guard' ASSIGNEE=forge CONVERSATION_ID=mission_login_guard BODY='Implement the bounded change, run tests, and report branch/PR evidence.'
```

Optional direct Discord reply mode is reserved for explicit cases:

```bash
make kanban-create TITLE='Answer docs question' ASSIGNEE=scribe CONVERSATION_ID=mission_docs_q DISCORD_THREAD_ID=<thread-id> REPLY_MODE=direct_discord BODY='Draft a concise user-facing answer and cite files changed.'
```

## Worker evidence rules

Workers should leave synthesis-ready evidence in durable places:

- Kanban task status and comments.
- Artifact files under `shared/project/artifacts/` when needed.
- Branch names, commit SHAs, PR URLs, and test commands for code work.
- Sentinel verdict comments for review-gated work.

Atlas should not claim a worker replied or completed work unless Kanban, PR, artifact, or logs provide observable evidence.

## Mission notifier and fan-in

`scripts/kanban-mission-notifier.py` remains the lightweight fan-in bridge. It tails Kanban task events, maintains a cursor/outbox in the shared board, and can create one Atlas synthesis task when worker tasks for a mission reach terminal states.

Useful commands:

```bash
make kanban-notifier-once
make kanban-notifier-dry-run
make kanban-notifier-deliver
```

Status webhook dry-run:

```bash
make discord-status-dry-run MESSAGE='Team Nexus status check'
```

## Safety boundaries

- Discord is for human mission intake and final response, not worker-to-worker chat.
- Worker handoffs should be Kanban-only by default.
- `runtime/` may contain auth, sessions, memory, logs, checkpoints, and Kanban data; do not commit it.
- Profile files are rendered from `profiles/team-nexus.profiles.yaml`; use renderer dry-runs before staging.
- Checkpoints are enabled for editing profiles but do not replace Git for repo changes.

## Legacy runtime note

Older docs and ADRs may describe one Docker Compose service per agent, `shared/team-agents.yaml`, and the custom Compose-aware dispatcher scripts. Those paths are superseded by the profile-driven runtime and should not be used for current operations.
