# Team Nexus operations runbook

This is the operator path for the profile-driven Team Nexus runtime. Run commands from the repo root:

```bash
cd /Users/sage/team-nexus
```

## 1. Prerequisites

- Docker Desktop or Docker Engine with Docker Compose v2.
- A checkout of this repository.
- `.env` created from `.env.example`.
- Provider keys in `.env` for the models/tools you intend to use.
- Atlas Discord credentials in `.env` if you want the v1 Discord gateway online.

## 2. First-time setup

```bash
cp .env.example .env
# edit .env and add required provider/API keys
make profile-render
make validate
make workspace-init
make build
make compose-config
make kanban-init
```

Notes:

- `profiles/team-nexus.profiles.yaml` is the source of truth for the active profile roster.
- `profiles/<profile>/` contains the source `SOUL.md`, `AGENTS.md`, and `config.yaml`; the renderer copies `SOUL.md`/`config.yaml` and composes generated `AGENTS.md` from `shared/profile/AGENTS.base.md` plus the profile fragment.
- `runtime/` is ignored because it may contain `.env`, auth, sessions, memory, logs, checkpoints, Kanban state, per-profile scratch workspaces, and credentials.
- `/workspace` is the Team Nexus control repository; profiles default terminal scratch work to `/workspaces/<profile>` so accidental ad-hoc files stay under ignored `runtime/hermes/workspaces`.
- On Linux, prefer Makefile targets so `TEAM_NEXUS_UID=$(id -u)` and `TEAM_NEXUS_GID=$(id -g)` are exported automatically.

## 3. Start and stop the runtime

Start Atlas gateway plus the dashboard:

```bash
make up
make ps
make logs SERVICE=atlas-gateway
```

Useful service commands:

```bash
make restart
make down
make doctor PROFILE=atlas
make doctor-all
```

Open a profile-scoped admin shell:

```bash
make shell PROFILE=forge
```

## 4. Dashboard

The profile-driven runtime has one dashboard function service using Atlas' profile home:

```bash
make up
open http://127.0.0.1:${TEAM_NEXUS_DASHBOARD_PORT:-9119}/
```

Dashboard assets are shared through:

```text
shared/plugins              -> /opt/data/plugins:ro and /opt/data/profiles/<active>/plugins:ro
shared/dashboard-themes    -> /opt/data/dashboard-themes:ro and /opt/data/profiles/<active>/dashboard-themes:ro
```

Restart after plugin/theme changes:

```bash
make restart
make compose-config
```

## 5. Kanban operations

Kanban is the durable coordination layer. Atlas is the v1 Discord-facing gateway and hosts native dispatch behavior. Workers are profiles, not separate long-running Discord bots.

Initialize and inspect the board:

```bash
make kanban-init
make kanban-stats
make kanban-list
```

Create a mission-scoped task:

```bash
make kanban-create TITLE='Draft launch brief' ASSIGNEE=forge CONVERSATION_ID=mission_launch_brief BODY='Implement the bounded task and report evidence.'
```

Rules:

- Use active profile names from `profiles/team-nexus.profiles.yaml` as assignees.
- Include the mission contract in task title/body through `make kanban-create`.
- Worker evidence belongs in Kanban comments, task state, artifacts, branch/PR links, and test/verdict output.
- Atlas synthesizes user-facing responses unless a task explicitly opts into direct Discord reply.

Dispatcher checks:

```bash
make kanban-dispatcher-once DRY_RUN=1
MAX_TASKS=3 make kanban-dispatcher-once DRY_RUN=1
make logs SERVICE=atlas-gateway
```

Real dispatch is hosted by `atlas-gateway`; start/stop it with the normal runtime commands:

```bash
make up
make down
```

## 6. MCP operations

Shared MCP registry templates live under `shared/mcp/registry/`.

```bash
make mcp-templates
make mcp-list PROFILE=atlas
make mcp-register-template PROFILE=forge SERVER=filesystem-workspace
make mcp-register-template-all SERVER=filesystem-workspace TARGET_AGENTS='atlas forge'
make mcp-test PROFILE=forge SERVER=filesystem-workspace
```

Profile-specific MCP changes are applied by running Hermes CLI with:

```text
HERMES_HOME=/opt/data/profiles/<profile>
```

## 7. Profile changes

Profile identity, role instructions, gateway settings, skills, checkpoints, and runtime mode defaults live in:

```text
profiles/team-nexus.profiles.yaml
profiles/<profile>/{SOUL.md,AGENTS.md,config.yaml}
shared/profile/AGENTS.base.md
shared/skills/manifests/
```

Safe edit loop:

```bash
make profile-render-dry-run
make profile-render-docker-dry-run
make profile-validate
make profile-render
make validate
```

Do not write generated profile files directly into durable Hermes homes outside the renderer without an explicit backup/migration policy.

## 8. Preflight and drift checks

Run the full local preflight:

```bash
make preflight
```

For incident-specific remediation, see the root troubleshooting guide:

```text
TROUBLESHOOTING.md
```

Or run individual checks:

```bash
make validate
make profile-render-dry-run
make profile-render-docker-dry-run
make compose-config
make profile-render
make profile-permissions-check
```

## 9. Troubleshooting

Start with the root troubleshooting guide for known Team Nexus incidents and recovery commands:

```text
TROUBLESHOOTING.md
```

Gateway logs:

```bash
make logs SERVICE=atlas-gateway
```

Dashboard logs:

```bash
make logs SERVICE=dashboard
```

Dispatcher logs:

```bash
make logs SERVICE=atlas-gateway
```

Doctor checks:

```bash
make doctor PROFILE=atlas
make doctor-all
```

Generated profile files look stale:

```bash
make profile-render-docker-dry-run
make profile-render
make validate
```

Compose validation:

```bash
make compose-config
```

## 10. Legacy runtime note

The old registry-driven runtime has been superseded by ADR-0014. The following are intentionally no longer active operator paths:

- `shared/team-agents.yaml`
- `scripts/team_registry.py`
- `generated/team-agents.mk`
- `docker-compose.yml` plus generated per-agent Compose fragments
- Nginx dashboard fan-out through `nginx/dashboards.conf`
- Removed agent lifecycle targets (`agent-add`, `agent-disable`, `agent-archive`)

Historical plans/ADRs may still mention these for context, but current operations should use the profile-driven commands above.
