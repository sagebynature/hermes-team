# Team Nexus operations runbook

This is the operator path for registry-driven Team Nexus. Run commands from the repo root:

```bash
cd /Users/sage/team-nexus
```

## 1. Prerequisites

- Docker Desktop or Docker Engine with Docker Compose v2.
- A checkout of this repository.
- `.env` created from `.env.example`.
- Provider keys in `.env` for the models/tools you intend to use.
- Local ports free for the enabled registry agents. Check suggested new ports with `make registry-next-ports`.

## 2. First-time setup

```bash
cd /Users/sage/team-nexus
cp .env.example .env
# edit .env and add required provider/API keys
make generate
make validate
make workspace-init
make build
make compose-config
make kanban-init
```

Notes:

- `shared/team-agents.yaml` is the source of truth for the active roster.
- Generated files include `generated/team-agents.mk`, `docker-compose.agents.generated.yml`, `docker-compose.dashboards.generated.yml`, `nginx/dashboards.conf`, and `shared/project/generated/team-roster.md`.
- On Linux, prefer Makefile targets so `TEAM_NEXUS_UID=$(id -u)` and `TEAM_NEXUS_GID=$(id -g)` are exported automatically. If running `docker compose` directly, set those variables in `.env` or prefix the command so bind-mounted agent homes stay owned by the host operator.
- If `make validate` reports unknown Kanban assignees from an existing `shared/kanban/kanban.db`, do not rewrite the DB blindly. Reassign or close those tasks deliberately through Kanban operations.

## 3. Start core gateways

```bash
make up
make ps
make logs AGENT=atlas
```

Useful service commands:

```bash
make restart
make down
make doctor AGENT=atlas
make doctor-all
```

## 4. Start dashboards

```bash
make dashboards-up
open http://127.0.0.1:${NGINX_PORT:-9130}/atlas/
```

Dashboard helpers:

```bash
make dashboards-restart
make compose-config
```

Direct dashboard ports and gateway ports are read from `shared/team-agents.yaml`. The Nginx dashboard reverse proxy is generated at `nginx/dashboards.conf`.

## 5. Kanban dispatch

Inspect a dry run before automatic worker spawning:

```bash
make kanban-dispatcher-once DRY_RUN=1
```

Run and stop the daemon:

```bash
make kanban-dispatcher-daemon
make kanban-dispatcher-logs
make kanban-dispatcher-stop
```

The dispatcher is Compose-aware and dispatches to enabled agents listed in the registry. Agent configs keep `kanban.dispatch_in_gateway: false` so gateway processes do not compete with the Compose dispatcher.

## 6. Create and inspect Kanban tasks

```bash
make kanban-create TITLE='Draft launch brief' ASSIGNEE=vega
make kanban-list
make kanban-stats
```

Rules:

- Use only enabled assignees in `shared/project/generated/team-roster.md`.
- Do not assign work to disabled or archived agents.
- Let Atlas route multi-agent missions unless the user directly instructs otherwise.

## 7. Add common/shared plugins

Shared plugins live under:

```text
shared/plugins/<plugin-name>/
```

This path is mounted read-only into each agent at `/opt/data/plugins`. Plugins placed here are team-wide. Agent-local plugins, if ever needed, belong under `agents/<agent>/home/plugins`, but the current Compose mount of shared plugins onto `/opt/data/plugins` may hide local plugin directories. Prefer shared plugins unless the Compose mount strategy changes.

Common plugin add flow:

```bash
mkdir -p shared/plugins/<plugin-name>
# copy plugin files into shared/plugins/<plugin-name>
make validate-plugins
make restart
make dashboards-restart
```

For dashboard plugins, use this layout when applicable:

```text
shared/plugins/<plugin-name>/dashboard/manifest.json
shared/plugins/<plugin-name>/dashboard/<entry assets>
```

Then verify:

```bash
make validate-plugins
open http://127.0.0.1:${NGINX_PORT:-9130}/atlas/plugins
```

## 8. Add an agent

Preview next ports:

```bash
make registry-next-ports
```

Create the registry entry and scaffold files:

```bash
make agent-add SLUG=raven NAME=Raven ROLE='Legal / Compliance'
```

Optional explicit ports:

```bash
make agent-add SLUG=raven NAME=Raven ROLE='Legal / Compliance' GATEWAY_PORT=8650 DASHBOARD_PORT=9127
```

The lifecycle command:

- Updates `shared/team-agents.yaml`.
- Creates `agents/<slug>/home/config.yaml`, `SOUL.md`, and `AGENTS.md` from templates.
- Creates `agents/<slug>/workspace/inbox`, `outbox`, `artifacts`, and `notes`.
- Creates an optional `agents/<slug>/workspace/.mise.toml` placeholder.
- Runs generation and validation through the Make wrapper.

After adding:

```bash
make compose-config
make up
make dashboards-up
```

## 9. Disable an agent safely

```bash
make agent-disable SLUG=raven
make validate
make restart
```

Disabling sets these registry fields false:

- `enabled`
- `dashboard_visible`
- `discord_visible`
- `dispatch_enabled`

Files and durable state under `agents/<slug>` are preserved. If `shared/kanban/kanban.db` exists, the command warns about open tasks still assigned to the disabled agent.

## 10. Archive an agent

Archive only after disabling:

```bash
make agent-disable SLUG=raven
make agent-archive SLUG=raven
make validate
```

`agent-archive` refuses enabled agents unless forced:

```bash
make agent-archive SLUG=raven FORCE=1
```

Archiving moves `agents/<slug>` to `agents/.archived/<slug>-YYYYMMDD` and marks the registry entry with `enabled: false` and `archived: true`. It does not delete durable state. Review archived homes for auth files or secrets before sharing.

## 11. Preflight and drift checks

Run the safe local preflight:

```bash
make preflight
```

Or run individual checks:

```bash
make generate
python3 scripts/team_registry.py validate-registry
make check-generated
make registry-next-ports
make validate-plugins
make compose-config
```

## 12. Troubleshooting

Gateway logs:

```bash
make logs AGENT=atlas
```

Dashboard logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml --profile dashboard logs -f atlas-dashboard dashboard-nginx
```

Dispatcher logs:

```bash
make kanban-dispatcher-logs
```

Doctor checks:

```bash
make doctor AGENT=atlas
make doctor-all
```

Generated files stale:

```bash
make generate
make check-generated
```

Port collision:

- Check `shared/team-agents.yaml` for duplicate `gateway_port` or `dashboard_port`.
- Run `make registry-next-ports` and edit through lifecycle commands where possible.

Unknown Kanban assignee:

- Run `make registry-list` and inspect `shared/project/generated/team-roster.md`.
- Reassign or close tasks deliberately; do not mutate `shared/kanban/kanban.db` by hand unless you have a backup and understand the schema.

Plugin not visible:

- Confirm files are under `shared/plugins/<plugin-name>`.
- Run `make validate-plugins`.
- Restart gateways and dashboards.
- Remember shared plugins are mounted read-only into `/opt/data/plugins`.

Config changes not visible:

- Restart the relevant gateway/dashboard after changing config, plugins, themes, or `.env`.
