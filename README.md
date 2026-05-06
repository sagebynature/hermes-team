# Team Nexus

**A Hermes-native profile-driven software delivery team, containerized and ready to deploy.**

Team Nexus uses Hermes Agent profiles, Kanban, checkpoints, skills, and a functional Docker runtime. Atlas is the only Discord-facing gateway in v1. Forge, Sentinel, Scribe, and Curator are specialist Hermes profiles dispatched through Kanban.

## Operator quick start

```bash
cp .env.example .env
# edit .env; Atlas Discord token is required for gateway use
make profile-runtime-stage
make validate
make build
make up
```

Useful commands:

```bash
make compose-config
make profile-render-dry-run
make profile-render-docker-dry-run
make shell PROFILE=forge
make doctor PROFILE=atlas
make logs SERVICE=atlas-gateway
make kanban-dispatcher-once DRY_RUN=1
```

Flow:

```text
User -> Atlas Discord gateway -> Kanban -> specialist profiles -> Atlas -> User
```

## Key documents

- Architecture plan: `docs/architecture/profile-driven-team-nexus.md`
- ADR: `docs/adr/0014-profile-driven-team-nexus.md`
- Migration inventory: `docs/migration/profile-driven-runtime-inventory.md`
- Profile specs: `profiles/team-nexus.profiles.yaml`
- Profile schema notes: `shared/config/profile-spec-schema.md`
- Profile Compose runtime: `docker-compose.profiles.yml`

## V1 profile roster

| Profile | Mission |
| --- | --- |
| Atlas | Mission intake, routing, Kanban task graph, Discord-facing synthesis |
| Forge | Software implementation in task worktrees, tests, commits, draft PRs |
| Sentinel | Code review, QA, security, and ship/no-ship verdicts |
| Scribe | Docs, ADRs, changelog, and PR narrative |
| Curator | Learning governance, repo-visible skills/docs/profile updates |

Planned later profiles: Scout, Ops, and Relay. Worker Discord gateway settings are represented in the profile spec but disabled by default.

## Runtime model

The default Docker runtime uses one image and function services from `docker-compose.profiles.yml`:

| Service | Purpose |
| --- | --- |
| `atlas-gateway` | Atlas Discord gateway and native Kanban dispatcher host |
| `dashboard` | Light Team Nexus inspection/control plane |
| `admin-shell` | Operator shell using a selected profile home |
| `kanban-dispatcher` | Optional one-shot native dispatcher nudge |

Mounts:

```text
runtime/hermes             -> /opt/data
repo root                  -> /workspace
shared/skills              -> /shared/skills:ro
shared/mcp                 -> /shared/mcp:ro
shared/plugins             -> /opt/data/plugins:ro
shared/dashboard-themes    -> /opt/data/dashboard-themes:ro
```

`runtime/` is ignored because it may contain profile-local `.env`, auth, sessions, memory, logs, checkpoints, Kanban state, and other user/customer data.

## Profile generation

Canonical input:

```text
profiles/team-nexus.profiles.yaml
profiles/templates/
shared/skills/manifests/
```

Preview generated files:

```bash
make profile-render-dry-run
make profile-render-docker-dry-run
```

Stage Docker-mode profile files into ignored runtime state:

```bash
make profile-runtime-stage
```

Validate:

```bash
make validate
make compose-config
```

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
- Atlas Discord token is required for v1 gateway use.
- Worker Discord tokens are optional future fields and disabled by default.
- Do not copy secrets broadly between profiles without explicit operator action.

## Make targets

Core:

```bash
make build
make up
make down
make restart
make ps
make logs SERVICE=atlas-gateway
make shell PROFILE=forge
make doctor PROFILE=atlas
```

Kanban:

```bash
make kanban-init
make kanban-list
make kanban-stats
make kanban-create TITLE='...' ASSIGNEE=forge CONVERSATION_ID=mission_slug BODY='...'
make kanban-dispatcher-once DRY_RUN=1
```

MCP:

```bash
make mcp-list PROFILE=atlas
make mcp-register-template PROFILE=forge SERVER=filesystem-workspace
make mcp-register-template-all SERVER=filesystem-workspace TARGET_AGENTS='atlas forge'
```

## Migration note

The repo is intentionally moving away from the old per-agent Docker Compose runtime. Profiles are the identity boundary; Docker services are functional runtime processes. Old generated per-agent Compose files, registry generation, and nginx dashboard fan-out have been removed from the default architecture.
