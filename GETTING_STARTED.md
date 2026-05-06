# Getting Started with Team Nexus

Team Nexus now uses the Hermes-native profile-driven runtime. This guide is the short operator path; deeper design/rationale lives in `docs/architecture/profile-driven-team-nexus.md` and `docs/adr/0014-profile-driven-team-nexus.md`.

## 1. Prepare secrets

```bash
cp .env.example .env
# edit .env
```

Rules:

- Do not commit `.env`.
- At least one model provider key is required for live agent runs, usually `OPENROUTER_API_KEY`.
- `DISCORD_BOT_TOKEN`, `DISCORD_ALLOWED_USERS`, and `DISCORD_HOME_CHANNEL` are required when running the Atlas Discord gateway.
- Worker Discord gateways are disabled in v1; specialists coordinate through Kanban unless a task explicitly opts into direct Discord reply.
- `TEAM_NEXUS_DASHBOARD_PORT` defaults to the value in `.env.example`; open the dashboard at `http://127.0.0.1:${TEAM_NEXUS_DASHBOARD_PORT}` after `make up`.

## 2. Render profile homes

```bash
make profile-runtime-stage
```

This renders Docker-mode profile files into:

```text
runtime/hermes/profiles/<profile>/
```

`runtime/` is ignored because it can contain profile state, auth, memory, logs, checkpoints, Kanban data, and other user/customer state.

Canonical source files are:

```text
profiles/team-nexus.profiles.yaml
profiles/templates/
shared/skills/manifests/
```

## 3. Validate

Fast validation:

```bash
make validate
make compose-config
```

Full preflight before committing or starting from a clean checkout:

```bash
make preflight
```

`make preflight` runs profile validation, host/Docker render dry-runs, Compose config validation, and Docker runtime staging.

Optional previews:

```bash
make profile-render-dry-run
make profile-render-docker-dry-run
```

## 4. Build and start

```bash
make build
make up
```

Default function services from `docker-compose.profiles.yml`:

| Service | Purpose |
| --- | --- |
| `atlas-gateway` | Atlas Discord gateway and native Kanban dispatcher host |
| `dashboard` | Light inspection/control plane at `http://127.0.0.1:${TEAM_NEXUS_DASHBOARD_PORT}` |
| `admin-shell` | Operator shell with selected profile home |
| `kanban-dispatcher` | Optional one-shot native dispatcher nudge |

Notes:

- Profiles are the identity boundary; Docker services are functional runtime processes.
- Atlas is the only v1 gateway profile. Forge, Sentinel, Scribe, and Curator run as Kanban-dispatched profiles.
- The old generated per-agent Compose files, registry generator, nginx dashboard fan-out, and Compose-aware dispatcher have been removed.

## 5. Operate

```bash
make ps
make logs SERVICE=atlas-gateway
make shell PROFILE=forge
make doctor PROFILE=atlas
make doctor-all
```

Kanban:

```bash
make kanban-init
make kanban-list
make kanban-stats
make kanban-create TITLE='Example task' ASSIGNEE=forge CONVERSATION_ID=example BODY='Implement the bounded task and report evidence.'
make kanban-dispatcher-once DRY_RUN=1
```

MCP:

```bash
make mcp-list PROFILE=atlas
make mcp-register-template PROFILE=forge SERVER=filesystem-workspace
make mcp-register-template-all SERVER=filesystem-workspace TARGET_AGENTS='atlas forge'
```

Stop/restart:

```bash
make restart
make down
```

## Architecture references

- `README.md`
- `docs/team-nexus-operations.md`
- `docs/discord-kanban-operations.md`
- `docs/architecture/profile-driven-team-nexus.md`
- `docs/adr/0014-profile-driven-team-nexus.md`
- `profiles/team-nexus.profiles.yaml`
- `shared/config/profile-spec-schema.md`
- `docker-compose.profiles.yml`
