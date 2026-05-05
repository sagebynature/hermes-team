# Getting Started with Team Nexus

This guide walks you from a fresh checkout to a running Team Nexus stack with gateways, dashboards, Kanban coordination, and the shared dashboard identity system.

Team Nexus is a Dockerized Hermes Agent virtual team. Each agent runs in its own container with its own Hermes home, workspace, memory, sessions, logs, and dashboard identity. Shared project context, skills, plugins, MCP registry files, dashboard themes, and Kanban state are mounted into every agent.

Use this file when you want the practical step-by-step path. For deeper operational notes, see:

- README.md
- docs/team-nexus-operations.md
- docs/discord-kanban-operations.md
- docs/agent-message-router.md
- docs/adr/README.md

---

## 0. Mental model

Team Nexus runs these layers:

1. Docker Compose
   - Starts one Hermes gateway per agent.
   - Starts one dashboard service per agent when the dashboard profile is enabled.
   - Starts an optional Nginx reverse proxy for all dashboards.
   - Starts an optional Compose-aware Kanban dispatcher.

2. Hermes Agent homes
   - Each agent has a durable home at `agents/<agent>/home`.
   - Inside containers, that same directory is mounted as `/opt/data`.
   - This is where Hermes config, sessions, memory, auth state, logs, profile image, and local state live.

3. Agent workspaces
   - Each agent has a private workspace at `agents/<agent>/workspace`.
   - Inside containers, that same directory is mounted as `/workspace`.
   - Terminal tools run from `/workspace` by default.

4. Shared context and coordination
   - `shared/project` is mounted read-only into all agents.
   - `shared/project/artifacts` is writable and is the preferred handoff area.
   - `shared/kanban` stores the shared Kanban database.
   - `shared/skills`, `shared/mcp`, `shared/plugins`, and `shared/dashboard-themes` are shared team resources.

5. Atlas as default coordinator
   - Atlas is the default mission coordinator.
   - Specialists should receive bounded work through Kanban or explicit operator instruction.
   - Discord bot mentions are not guaranteed dispatch; the agent message router (`docs/agent-message-router.md`) and Kanban are the A2A work path.
   - Atlas synthesizes specialist output for the user.

---

## 1. Prerequisites

Install or verify:

- Docker Desktop or Docker Engine.
- Docker Compose v2.
- make.
- git.
- A shell with standard Unix tools.
- At least one LLM provider key, usually `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GOOGLE_API_KEY`.

Recommended host ports must be free:

Gateway API ports:

| Agent | Host port |
| --- | ---: |
| Atlas | 8642 |
| Vega | 8643 |
| Scout | 8644 |
| Forge | 8645 |
| Lumen | 8646 |
| Blitz | 8647 |
| Ledger | 8648 |
| Sentinel | 8649 |

Dashboard direct ports:

| Agent | Direct dashboard URL |
| --- | --- |
| Atlas | http://127.0.0.1:9119 |
| Vega | http://127.0.0.1:9120 |
| Scout | http://127.0.0.1:9121 |
| Forge | http://127.0.0.1:9122 |
| Lumen | http://127.0.0.1:9123 |
| Blitz | http://127.0.0.1:9124 |
| Ledger | http://127.0.0.1:9125 |
| Sentinel | http://127.0.0.1:9126 |

Dashboard reverse proxy:

| Purpose | Default URL |
| --- | --- |
| Dashboard proxy | http://127.0.0.1:9130 |

If ports collide, edit `shared/team-agents.yaml` and regenerate files with `make generate`, or inspect the next suggested values with:

```bash
make registry-next-ports
```

---

## 2. Clone and enter the repo

```bash
git clone <repo-url> team-nexus
cd team-nexus
```

If this repo is already checked out locally:

```bash
cd /Users/sage/team-nexus
```

All commands in this guide assume you are running from the repo root.

---

## 3. Create the shared environment file

Copy the template:

```bash
cp .env.example .env
```

Edit `.env` and add only the credentials you intend to use.

Minimum useful model setup:

```env
OPENROUTER_API_KEY=...
```

or:

```env
ANTHROPIC_API_KEY=...
```

or:

```env
OPENAI_API_KEY=...
```

Optional Discord setup:

```env
DISCORD_BOT_TOKEN=...
DISCORD_ALLOWED_USERS=...
DISCORD_HOME_CHANNEL=...
DISCORD_STATUS_WEBHOOK_URL=...
DISCORD_HANDOFFS_WEBHOOK_URL=...
DISCORD_COMMAND_SYNC_POLICY=off
```

Optional dashboard reverse-proxy port:

```env
NGINX_PORT=9130
```

Optional dispatcher tuning:

```env
KANBAN_DISPATCH_INTERVAL=60
KANBAN_DISPATCH_MAX_TASKS=1
KANBAN_DISPATCH_WORKER_TIMEOUT=900
```

Optional Linux bind-mount ownership setup:

```env
TEAM_NEXUS_UID=1000
TEAM_NEXUS_GID=1000
```

If you use the Makefile targets (`make up`, `make doctor`, `make dashboards-up`, etc.), these values are exported automatically from `id -u` and `id -g`. If you run `docker compose ...` directly on Ubuntu, add them to `.env` or prefix the command:

```bash
TEAM_NEXUS_UID=$(id -u) TEAM_NEXUS_GID=$(id -g) docker compose -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml --profile dashboard up -d
```

This keeps files created under `agents/<agent>/home`, `shared/kanban`, and `shared/project/artifacts` owned by your host account instead of Docker image UID/GID 10000.

Important:

- Do not commit `.env`.
- The repo-root `.env` is loaded into all agent services.
- Per-agent durable auth state belongs in `agents/<agent>/home`, not in the image.

---

## 4. Generate registry-driven files

The active roster lives in:

```text
shared/team-agents.yaml
```

Generated files are derived from that registry. Generate them before building or starting the stack:

```bash
make generate
```

This writes or refreshes:

```text
generated/team-agents.mk
docker-compose.agents.generated.yml
docker-compose.dashboards.generated.yml
nginx/dashboards.conf
shared/project/generated/team-roster.md
```

Do not hand-edit generated files. Change `shared/team-agents.yaml` or templates, then run `make generate` again.

---

## 5. Validate the repo before starting

Run:

```bash
make validate
```

Useful narrower checks:

```bash
make registry-validate
make check-generated
make validate-plugins
make compose-config
```

Recommended first-time validation sequence:

```bash
make generate
make validate
make compose-config
```

If validation reports stale generated files:

```bash
make generate
make check-generated
```

If validation reports port collisions:

```bash
make registry-next-ports
```

Then update `shared/team-agents.yaml`, regenerate, and validate again.

---

## 6. Initialize shared writable directories

Create shared writable handoff and Kanban directories:

```bash
make workspace-init
```

This initializes:

```text
shared/project/artifacts
shared/kanban
```

The intended shared write boundary is narrow:

- Writable: `shared/project/artifacts`
- Writable: `shared/kanban`
- Read-only in containers: `shared/project`, except the artifacts submount
- Read-only in containers: `shared/skills`
- Read-only in containers: `shared/mcp`
- Read-only in containers: `shared/plugins`
- Read-only in containers: `shared/dashboard-themes`

---

## 7. Build the Team Nexus image

Build the shared local image:

```bash
make build
```

The image name is:

```text
team-nexus-agent:latest
```

Only Atlas has the Compose build stanza. The other agents reuse the same image. This avoids exporting the same image eight times.

The image includes Hermes Agent plus team runtime conveniences such as:

- mise
- node LTS
- npm / npx
- uv / uvx
- jq
- ripgrep
- git
- openssh-client
- zip / unzip
- voice dependencies used by the current Team Nexus image

---

## 8. Initialize Kanban

Initialize the shared Kanban board once:

```bash
make kanban-init
```

The host database path is:

```text
shared/kanban/kanban.db
```

Inside containers it appears as:

```text
/shared/kanban/kanban.db
```

Check the board:

```bash
make kanban-stats
make kanban-list
```

Kanban is a SQLite-backed board plus Hermes CLI/tooling. It is not a separate long-running server.

---

## 9. Start Team Nexus

Start gateways, dashboards, Nginx, and the dispatcher profile services declared by the Makefile:

```bash
make up
```

Then inspect service status:

```bash
make ps
```

Follow Atlas logs:

```bash
make logs AGENT=atlas
```

Follow another agent:

```bash
make logs AGENT=forge
```

Restart everything managed by the standard profiles:

```bash
make restart
```

Stop the stack:

```bash
make down
```

---

## 10. Open the dashboards

Start or refresh the dashboard profile:

```bash
make dashboards-up
```

Open the reverse-proxied dashboards:

| Agent | Reverse-proxy URL |
| --- | --- |
| Atlas | http://127.0.0.1:9130/atlas/ |
| Vega | http://127.0.0.1:9130/vega/ |
| Scout | http://127.0.0.1:9130/scout/ |
| Forge | http://127.0.0.1:9130/forge/ |
| Lumen | http://127.0.0.1:9130/lumen/ |
| Blitz | http://127.0.0.1:9130/blitz/ |
| Ledger | http://127.0.0.1:9130/ledger/ |
| Sentinel | http://127.0.0.1:9130/sentinel/ |

If you changed `NGINX_PORT` in `.env`, replace `9130` with that value.

Direct dashboard ports are also available:

| Agent | Direct URL |
| --- | --- |
| Atlas | http://127.0.0.1:9119 |
| Vega | http://127.0.0.1:9120 |
| Scout | http://127.0.0.1:9121 |
| Forge | http://127.0.0.1:9122 |
| Lumen | http://127.0.0.1:9123 |
| Blitz | http://127.0.0.1:9124 |
| Ledger | http://127.0.0.1:9125 |
| Sentinel | http://127.0.0.1:9126 |

Restart dashboards after changing dashboard config, plugins, themes, profile images, or plugin backend code:

```bash
make dashboards-restart
```

If Nginx returns 502 after containers were recreated, restart the dashboard profile or Nginx so Docker DNS is re-resolved:

```bash
make dashboards-restart
```

---

## 11. Understand dashboard identity and colors

The shared dashboard theme is:

```text
shared/dashboard-themes/team-nexus.yaml
```

Each agent selects it in its config:

```yaml
dashboard:
  theme: team-nexus
```

The shared identity plugin is:

```text
shared/plugins/agent-identity-dashboard
```

It provides:

- `TEAM NEXUS` sidebar brand replacement.
- A portrait-friendly profile card near the sidebar System section.
- Agent name and role from config/environment.
- Profile image from `agents/<agent>/home/profile.jpg`.
- Per-agent dashboard accent colors.

Per-agent colors are configured in each agent config under `dashboard.accent_colors`:

```yaml
dashboard:
  accent_colors:
    primary: "#4F7FC5"
    secondary: "#6FE6F2"
```

The canonical source of those colors is the registry:

```yaml
agents:
  atlas:
    dashboard_primary_color: "#4F7FC5"
    dashboard_secondary_color: "#6FE6F2"
```

Current profile-derived color map:

| Agent | Primary | Secondary |
| --- | --- | --- |
| Atlas | #4F7FC5 | #6FE6F2 |
| Vega | #8B5CF6 | #5EEAD4 |
| Scout | #F47A1F | #20D6C0 |
| Forge | #6CFF9A | #FF4E57 |
| Lumen | #7EF7F2 | #2FA6A3 |
| Blitz | #E1262F | #FF5A5F |
| Ledger | #22C7F2 | #0B3A63 |
| Sentinel | #FFD35A | #5F6670 |

After changing registry colors:

```bash
make generate
make validate
make dashboards-restart
```

The frontend plugin writes these CSS variables at runtime:

```css
--agent-primary-color
--agent-secondary-color
--agent-primary-rgb
--agent-secondary-rgb
```

The shared `team-nexus` dashboard theme consumes those variables while preserving a default green/orange fallback.

---

## 12. Verify dashboard plugin API behavior

After dashboards are running, verify one direct dashboard endpoint:

```bash
curl -sS http://127.0.0.1:9119/api/plugins/agent-identity-dashboard/identity
```

Expected shape:

```json
{
  "agent_name": "Atlas",
  "agent_role": "Orchestrator / Chief of Staff",
  "profile_image": {
    "exists": true,
    "url": "/api/plugins/agent-identity-dashboard/profile.jpg"
  },
  "dashboard_colors": {
    "primary": "#4F7FC5",
    "secondary": "#6FE6F2"
  }
}
```

If you are using the Nginx reverse proxy, also test through the prefix:

```bash
curl -sS http://127.0.0.1:9130/atlas/api/plugins/agent-identity-dashboard/identity
```

If you receive the dashboard HTML instead of JSON, the plugin API route is not mounted or the proxy rewrite is wrong. Restart dashboards and check plugin layout:

```bash
make validate-plugins
make dashboards-restart
```

---

## 13. Use Kanban manually

Create a task:

```bash
make kanban-create TITLE='Draft launch brief' ASSIGNEE=vega
```

List tasks:

```bash
make kanban-list
```

Show stats:

```bash
make kanban-stats
```

Watch events:

```bash
make kanban-watch
```

Link dependencies:

```bash
make kanban-link PARENT=<parent-task-id> CHILD=<child-task-id>
```

Manual dispatch of one task to its assigned agent:

```bash
make kanban-dispatch AGENT=forge TASK=<task-id>
```

Rules:

- Use enabled assignees from `shared/project/generated/team-roster.md`.
- Prefer Atlas for decomposition and synthesis.
- Parent tasks should produce a `[handoff]` comment and artifact path before child work starts.
- Durable decisions should be recorded as `[decision]` comments.
- Cross-agent deliverables should be written under `shared/project/artifacts`.

---

## 14. Use the automatic Kanban dispatcher

First run a safe dry run:

```bash
make kanban-dispatcher-once DRY_RUN=1
```

Run one real dispatcher pass:

```bash
make kanban-dispatcher-once
```

Start the dispatcher daemon:

```bash
make kanban-dispatcher-daemon
```

Follow dispatcher logs:

```bash
make kanban-dispatcher-logs
```

Stop the dispatcher daemon:

```bash
make kanban-dispatcher-stop
```

Tune dispatcher behavior with environment values:

```bash
KANBAN_DISPATCH_INTERVAL=60 \
KANBAN_DISPATCH_MAX_TASKS=1 \
KANBAN_DISPATCH_WORKER_TIMEOUT=900 \
make kanban-dispatcher-daemon
```

The dispatcher claims tasks before launching worker containers. A normal lifecycle is:

```text
todo -> ready -> running -> done
```

If a worker times out, the dispatcher blocks the task rather than relaunching it forever. Inspect, split, or unblock the task deliberately.

---

## 15. Run one-off agent commands

Open a shell inside an agent container:

```bash
make shell AGENT=atlas
```

Run Hermes doctor for one agent:

```bash
make doctor AGENT=atlas
```

Run doctor for every agent:

```bash
make doctor-all
```

List MCP servers for one agent:

```bash
make mcp-list AGENT=atlas
```

List MCP servers for all agents:

```bash
make mcp-list-all
```

Test one MCP server:

```bash
make mcp-test AGENT=atlas SERVER=time
```

---

## 16. Register MCP servers

Team Nexus has shared MCP registry templates under:

```text
shared/mcp/registry
```

List available templates:

```bash
make mcp-templates
```

Show a template:

```bash
make mcp-show-template SERVER=time
```

Register a template for one agent:

```bash
make mcp-register-template AGENT=atlas SERVER=time
```

Register a template for multiple agents:

```bash
make mcp-register-template-all SERVER=filesystem-workspace TARGET_AGENTS='atlas forge'
```

Add a command-based MCP server directly:

```bash
make mcp-add-command AGENT=forge SERVER=filesystem COMMAND='npx -y @modelcontextprotocol/server-filesystem /workspace'
```

Add an HTTP MCP server directly:

```bash
make mcp-add-url AGENT=atlas SERVER=my-server URL='https://example.com/mcp'
```

Remove a server:

```bash
make mcp-remove AGENT=atlas SERVER=time
```

---

## 17. Add a new agent

Preview available ports:

```bash
make registry-next-ports
```

Add the agent through the lifecycle target:

```bash
make agent-add SLUG=raven NAME=Raven ROLE='Legal / Compliance'
```

Optional explicit ports:

```bash
make agent-add SLUG=raven NAME=Raven ROLE='Legal / Compliance' GATEWAY_PORT=8650 DASHBOARD_PORT=9127
```

This updates or creates:

- `shared/team-agents.yaml`
- `agents/raven/home/config.yaml`
- `agents/raven/home/SOUL.md`
- `agents/raven/home/AGENTS.md`
- `agents/raven/workspace/inbox`
- `agents/raven/workspace/outbox`
- `agents/raven/workspace/artifacts`
- `agents/raven/workspace/notes`
- generated Compose, Nginx, roster, and Make files

After adding an agent:

```bash
make generate
make validate
make compose-config
make up
make dashboards-up
```

Then add a profile image if desired:

```text
agents/raven/home/profile.jpg
```

Add dashboard colors in `shared/team-agents.yaml`:

```yaml
dashboard_primary_color: "#RRGGBB"
dashboard_secondary_color: "#RRGGBB"
```

Then regenerate and restart dashboards:

```bash
make generate
make validate
make dashboards-restart
```

---

## 18. Disable or archive an agent

Disable without deleting state:

```bash
make agent-disable SLUG=raven
make validate
make restart
```

Disabling preserves files under `agents/raven` and sets registry flags such as:

- `enabled: false`
- `dashboard_visible: false`
- `discord_visible: false`
- `dispatch_enabled: false`

Archive after disabling:

```bash
make agent-disable SLUG=raven
make agent-archive SLUG=raven
make validate
```

Archiving moves agent state under:

```text
agents/.archived/<slug>-YYYYMMDD
```

Do not archive or share agent homes without reviewing for auth files, logs, memory, sessions, and other sensitive data.

---

## 19. Update shared plugins or themes

Shared plugins live under:

```text
shared/plugins/<plugin-name>
```

Dashboard plugin layout:

```text
shared/plugins/<plugin-name>/dashboard/manifest.json
shared/plugins/<plugin-name>/dashboard/dist/index.js
shared/plugins/<plugin-name>/dashboard/dist/style.css
```

Shared dashboard themes live under:

```text
shared/dashboard-themes/*.yaml
```

The active Team Nexus theme is:

```text
shared/dashboard-themes/team-nexus.yaml
```

After plugin or theme changes:

```bash
make validate-plugins
make dashboards-restart
```

If the plugin has backend API changes, restart the dashboard containers. A frontend-only plugin rescan may not be enough.

---

## 20. Regenerate and preflight before committing

Before committing operational changes, run:

```bash
make preflight
```

If you want the expanded individual steps:

```bash
make generate
make registry-validate
make check-generated
make validate-plugins
make compose-config
make validate
```

For dashboard-related JavaScript/Python changes, also run targeted checks:

```bash
node --check shared/plugins/agent-identity-dashboard/dashboard/dist/index.js
python3 -m py_compile shared/plugins/agent-identity-dashboard/dashboard/plugin_api.py
```

If your host Python lacks PyYAML, use the repo's available validation path or container-based checks rather than assuming all YAML validation commands will work locally.

---

## 21. Common operating workflows

### Start everything for a normal work session

```bash
cd /Users/sage/team-nexus
make generate
make validate
make up
make dashboards-up
make ps
```

Open:

```text
http://127.0.0.1:9130/atlas/
```

### Restart after config, plugin, theme, or .env changes

```bash
make restart
make dashboards-restart
```

### Check the board and dispatchers

```bash
make kanban-stats
make kanban-list
make kanban-dispatcher-logs
```

### Give a specialist a task manually

```bash
make kanban-create TITLE='Compare top 5 competitors' ASSIGNEE=scout
make kanban-dispatcher-once DRY_RUN=1
make kanban-dispatcher-once
```

### Ask Atlas to coordinate

Use Atlas through your configured gateway channel or dashboard. The expected operating path is:

```text
User -> Atlas -> specialists -> Atlas -> User
```

Atlas should clarify ambiguous missions, decompose work, route tasks, collect handoffs, and synthesize the final answer.

---

## 22. Troubleshooting

### Docker Compose config fails

Run:

```bash
make generate
make compose-config
```

If generated files are stale:

```bash
make check-generated
```

### A port is already in use

Inspect the registry:

```bash
make registry-next-ports
```

Then edit `shared/team-agents.yaml`, regenerate, and validate:

```bash
make generate
make validate
```

### Dashboard returns 502 through Nginx

Restart dashboard services so Nginx re-resolves Compose service IPs:

```bash
make dashboards-restart
```

Then try direct ports, for example:

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9119/
```

### Dashboard plugin route returns HTML instead of JSON

The plugin API route is probably not mounted, or the proxy path rewrite is wrong.

Run:

```bash
make validate-plugins
make dashboards-restart
curl -sS http://127.0.0.1:9119/api/plugins/agent-identity-dashboard/identity
```

### Profile image or accent colors do not update

Check the agent config and profile path:

```text
agents/<agent>/home/config.yaml
agents/<agent>/home/profile.jpg
```

Regenerate if values came from `shared/team-agents.yaml`:

```bash
make generate
make validate
make dashboards-restart
```

### Kanban has unknown assignees

List enabled agents:

```bash
make registry-list
```

Inspect roster:

```text
shared/project/generated/team-roster.md
```

Reassign or close stale tasks deliberately. Do not hand-edit `shared/kanban/kanban.db` unless you have a backup and understand the schema.

### A worker keeps timing out

Check dispatcher logs:

```bash
make kanban-dispatcher-logs
```

Then inspect the task, split it into smaller subtasks, or unblock it manually. Do not simply lower safety by relaunching the same looping task indefinitely.

### Hermes doctor reports missing optional tools

Run:

```bash
make doctor AGENT=atlas
```

Some warnings are optional integrations. Add the relevant API key or dependency only if that tool is part of your intended workflow.

### Discord bot is silent

Check:

- `DISCORD_BOT_TOKEN` is set in `.env`.
- Discord Message Content Intent is enabled in the bot settings.
- `DISCORD_ALLOWED_USERS` and `DISCORD_HOME_CHANNEL` match your intended access model.
- The gateway container was restarted after `.env` changes.

Restart:

```bash
make restart
```

---

## 23. File map

Important repo paths:

```text
.env.example                                      Environment template
.env                                              Local secrets; do not commit
Makefile                                          Main operator commands
docker-compose.yml                               Base Compose services
docker-compose.agents.generated.yml              Generated gateway services
docker-compose.dashboards.generated.yml          Generated dashboard services
nginx/dashboards.conf                            Generated dashboard reverse proxy config
shared/team-agents.yaml                          Source of truth for roster, ports, dashboard colors
shared/project                                   Shared read-only mission context
shared/project/artifacts                         Writable cross-agent handoff artifacts
shared/project/generated/team-roster.md          Generated active roster
shared/kanban                                    Shared Kanban database and dispatcher logs
shared/skills                                    Shared team skills
shared/mcp                                       Shared MCP registry/templates/docs
shared/plugins                                   Shared Hermes/dashboard plugins
shared/dashboard-themes/team-nexus.yaml          Active dashboard theme
templates/agent-config.yaml.tmpl                 Agent config template
scripts/team_registry.py                         Registry generation and validation
scripts/kanban-compose-dispatcher.py             Compose-aware Kanban dispatcher
agents/<agent>/home/config.yaml                  Agent Hermes config
agents/<agent>/home/SOUL.md                      Agent persona/voice
agents/<agent>/home/AGENTS.md                    Agent operating/project instructions
agents/<agent>/home/profile.jpg                  Agent dashboard portrait
agents/<agent>/workspace                         Agent private working directory
```

---

## 24. Safety rules

- Do not commit real `.env` values.
- Do not publish dashboard ports to `0.0.0.0` unless you intentionally want network exposure.
- Keep dashboard and gateway ports bound to `127.0.0.1` by default.
- Do not make `shared/project`, `shared/skills`, or `shared/mcp` writable inside containers unless you are intentionally changing the trust boundary.
- Use lifecycle targets for roster changes instead of manually copying agent directories.
- Treat `agents/<agent>/home` as sensitive durable state: it can contain auth, logs, memory, sessions, and config.
- Prefer Atlas for multi-agent coordination and final synthesis.
- Prefer Kanban and handoff artifacts for durable cross-agent work.

---

## 25. Minimal successful setup checklist

Run this from the repo root:

```bash
cp .env.example .env
# edit .env with at least one model provider key
make generate
make validate
make workspace-init
make build
make compose-config
make kanban-init
make up
make dashboards-up
make ps
```

Then open:

```text
http://127.0.0.1:9130/atlas/
```

Verify Kanban:

```bash
make kanban-stats
make kanban-list
```

Verify Atlas dashboard identity:

```bash
curl -sS http://127.0.0.1:9119/api/plugins/agent-identity-dashboard/identity
```

At this point Team Nexus is ready for operator-driven missions.
