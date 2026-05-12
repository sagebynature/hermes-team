# Team Nexus

**A Hermes-native profile-driven software delivery team, containerized and ready to deploy.**

Team Nexus uses Hermes Agent profiles, Kanban, checkpoints, skills, and a functional Docker runtime. Atlas is the only Discord-facing gateway in v1. Forge, Sentinel, Scribe, and Curator are specialist Hermes profiles dispatched through Kanban.

## Operator quick start

Guided installer from a fresh machine:

```bash
curl -fsSL https://raw.githubusercontent.com/sagebynature/team-nexus/main/scripts/install.sh | bash
```

Manual path inside an existing checkout:

```bash
cp .env.example .env
# edit .env; add a model provider key and Atlas Discord settings for gateway use
make preflight
make build
make up
```

Open the dashboard after startup:

```text
http://127.0.0.1:${TEAM_NEXUS_DASHBOARD_PORT}
```

Useful commands:

```bash
make validate
make compose-config
make profile-render-dry-run
make profile-render-docker-dry-run
make shell PROFILE=forge
make profile-permissions-check
make doctor PROFILE=atlas
make doctor-all
make logs SERVICE=atlas-gateway
make kanban-dispatcher-once DRY_RUN=1
```

Flow:

```text
User -> Atlas Discord gateway -> Kanban -> specialist profiles -> Atlas -> User
```

## Key documents

- First-time setup: `GETTING_STARTED.md`
- Operations runbook: `docs/team-nexus-operations.md`
- Troubleshooting guide: `TROUBLESHOOTING.md`
- Discord/Kanban runbook: `docs/discord-kanban-operations.md`
- Architecture plan: `docs/architecture/profile-driven-team-nexus.md`
- ADR: `docs/adr/0014-profile-driven-team-nexus.md`
- Migration inventory: `docs/migration/profile-driven-runtime-inventory.md`
- Profile specs: `profiles/team-nexus.profiles.yaml`
- Profile schema notes: `shared/config/profile-spec-schema.md`
- Profile Compose runtime: `docker-compose.profiles.yml`

## V1 profile roster

| Profile  | Mission                                                              |
| -------- | -------------------------------------------------------------------- |
| Atlas    | Mission intake, routing, Kanban task graph, Discord-facing synthesis |
| Forge    | Software implementation in task worktrees, tests, commits, draft PRs |
| Sentinel | Code review, QA, security, and ship/no-ship verdicts                 |
| Scribe   | Docs, ADRs, changelog, and PR narrative                              |
| Curator  | Learning governance, repo-visible skills/docs/profile updates        |

Planned later profiles: Scout, Ops, and Relay. Worker Discord gateway settings are represented in the profile spec but disabled by default.

## Runtime model

The default Docker runtime uses one image and function services from `docker-compose.profiles.yml`:

| Service             | Purpose                                                 |
| ------------------- | ------------------------------------------------------- |
| `atlas-gateway`     | Atlas Discord gateway and native Kanban dispatcher host |
| `dashboard`         | Light Team Nexus inspection/control plane               |
| `admin-shell`       | Operator shell using a selected profile home            |
| `kanban-dispatcher` | Optional one-shot native dispatcher nudge               |

Mounts:

```text
runtime/hermes             -> /opt/data
repo root                  -> /workspace (control repo; intentional edits only)
runtime/hermes/workspaces  -> /workspaces (ignored per-profile scratch cwd)
shared/skills              -> /shared/skills:ro
shared/mcp                 -> /shared/mcp:ro
shared/plugins              -> /opt/data/plugins:ro and /opt/data/profiles/<active>/plugins:ro
shared/dashboard-themes    -> /opt/data/dashboard-themes:ro and /opt/data/profiles/<active>/dashboard-themes:ro
```

Google Workspace CLI credentials use `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`.
A safe Docker-mode setup is:

```bash
mkdir -p runtime/hermes/secrets
cp /path/to/your/google-credentials.json runtime/hermes/secrets/google-workspace-credentials.json
printf '\nGOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/opt/data/secrets/google-workspace-credentials.json\n' >> .env
```

The custom Docker image installs `gws`, and the upstream `googleworkspace/cli`
agent skills are vendored under `shared/skills/` so all profiles can load them
through the shared `/shared/skills` external skill directory.

`runtime/` is ignored because it may contain profile-local `.env`, auth, sessions, memory, logs, checkpoints, Kanban state, credentials, per-profile scratch workspaces, and other user/customer data.

`/workspace` is the Team Nexus control repository. Profiles default their terminal cwd to `/workspaces/<profile>` so ad-hoc scratch files do not dirty the repo. Use `/workspace` explicitly for intentional Team Nexus source/docs/config edits, and use Kanban `workspace: scratch` or task-specific worktrees for delegated work.

## Profile generation

Canonical input:

```text
profiles/team-nexus.profiles.yaml
profiles/<profile>/{SOUL.md,AGENTS.md,config.yaml}
shared/profile/AGENTS.base.md
shared/skills/manifests/
```

Preview generated files:

```bash
make profile-render-dry-run
make profile-render-docker-dry-run
```

Stage Docker-mode profile files into ignored runtime state:

```bash
make profile-render
```

Validate:

```bash
make validate
make compose-config
make preflight
```

`make preflight` runs profile validation, Python compile checks, host/Docker render dry-runs, Compose config validation, and Docker runtime staging.

## Knowledge and learning policy

- Durable architecture/rationale belongs in docs and ADRs.
- Active role/workflow instructions belong in profile specs and generated `AGENTS.md`.
- Reusable procedures belong in repo-visible skills.
- Hermes memory is for compact stable facts only, not task progress or long workflows.
- Curator promotes reusable learnings into repo-visible artifacts.
- Significant workflow, safety, role, or permission changes require review.

## Safety policy

- Forge, Sentinel, Scribe, Curator, and future Ops profiles have checkpoints enabled.
- Git worktrees and commits remain the primary software-delivery safety model.
- Checkpoints are rollback safety nets, not a replacement for Git.
- No generated bootstrap should overwrite secrets, auth, sessions, memory, logs, checkpoint data, or live Kanban DBs.

## Secrets policy

- Commit `.env.example`, never real secrets.
- Docker mode loads repo-root `.env` through Compose.
- Add at least one model provider key for live agent runs, usually `OPENROUTER_API_KEY`.
- Atlas Discord settings are required for v1 gateway use: `DISCORD_BOT_TOKEN`, `DISCORD_ALLOWED_USERS`, and `DISCORD_HOME_CHANNEL`.
- Worker Discord tokens are optional future fields and disabled by default.
- Do not copy secrets broadly between profiles without explicit operator action.

## Make targets

Core:

```bash
make preflight
make build
make up
make down
make restart
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
make kanban-watch
make kanban-create TITLE='...' ASSIGNEE=forge CONVERSATION_ID=mission_slug BODY='...'
make kanban-dispatcher-once DRY_RUN=1
make kanban-notifier-once
make kanban-notifier-dry-run
```

MCP:

```bash
make mcp-list PROFILE=atlas
make mcp-register-template PROFILE=forge SERVER=filesystem-workspace
make mcp-register-template-all SERVER=filesystem-workspace TARGET_AGENTS='atlas forge'
```

## Migration note

The old generated per-agent Docker Compose runtime has been removed from the active repo path. Profiles are now the identity boundary; Docker services are functional runtime processes. `shared/team-agents.yaml`, `scripts/team_registry.py`, generated per-agent Compose files, nginx dashboard fan-out, and the Compose-aware Kanban dispatcher are superseded by `profiles/team-nexus.profiles.yaml`, `docker-compose.profiles.yml`, and native/profile-driven Kanban dispatch.
