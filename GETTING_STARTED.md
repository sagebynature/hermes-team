# Getting Started with Team Nexus

Team Nexus now uses the Hermes-native profile-driven runtime. This guide is intentionally short; the detailed design lives in `docs/architecture/profile-driven-team-nexus.md`.

## 1. Prepare secrets

```bash
cp .env.example .env
# edit .env
```

Rules:

- Do not commit `.env`.
- Atlas Discord token is required for the v1 gateway.
- Worker Discord tokens are optional future settings and disabled by default.

## 2. Render profile homes

```bash
make profile-runtime-stage
```

This renders Docker-mode profile files into:

```text
runtime/hermes/profiles/<profile>/
```

`runtime/` is ignored because it can contain profile state, auth, memory, logs, checkpoints, and Kanban data.

## 3. Validate

```bash
make validate
make compose-config
```

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

Default services:

| Service | Purpose |
| --- | --- |
| `atlas-gateway` | Atlas Discord gateway and native Kanban dispatcher host |
| `dashboard` | Light inspection/control plane |
| `admin-shell` | Operator shell with selected profile home |
| `kanban-dispatcher` | Optional one-shot dispatcher nudge |

## 5. Operate

```bash
make ps
make logs SERVICE=atlas-gateway
make shell PROFILE=forge
make doctor PROFILE=atlas
```

Kanban:

```bash
make kanban-init
make kanban-list
make kanban-create TITLE='Example task' ASSIGNEE=forge CONVERSATION_ID=example BODY='Implement the bounded task and report evidence.'
make kanban-dispatcher-once DRY_RUN=1
```

MCP:

```bash
make mcp-list PROFILE=atlas
make mcp-register-template PROFILE=forge SERVER=filesystem-workspace
```

## Architecture references

- `docs/architecture/profile-driven-team-nexus.md`
- `docs/adr/0014-profile-driven-team-nexus.md`
- `profiles/team-nexus.profiles.yaml`
- `shared/config/profile-spec-schema.md`
- `docker-compose.profiles.yml`
