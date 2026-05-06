# Profile-driven runtime migration inventory

Status: Draft
Date: 2026-05-06
Related: `docs/architecture/profile-driven-team-nexus.md`, `docs/adr/0014-profile-driven-team-nexus.md`

This inventory starts Phase 0 of the big-bang profile-driven refactor. It identifies current runtime surfaces that must either be migrated into the Hermes profile model or removed before the refactor is considered complete.

## Current runtime surfaces

| Surface | Current path(s) | Migration disposition |
|---|---|---|
| Agent roster registry | `shared/team-agents.yaml`, `scripts/team_registry.py`, `generated/team-agents.mk` | Removed from active runtime. Superseded by `profiles/team-nexus.profiles.yaml`, renderer validation, and profile manifests. |
| Per-agent Compose services | `docker-compose.agents.generated.yml` | Removed from active runtime. Superseded by `docker-compose.profiles.yml` function services where profiles are identity and services are gateway/dashboard/admin/dispatcher functions. |
| Per-agent dashboard services | `docker-compose.dashboards.generated.yml`, `nginx/dashboards.conf` | Removed from active runtime. Dashboard is now a function service using shared plugin/theme mounts. |
| Per-agent homes | `agents/*/home/` | Legacy tracked seed/runtime state. Do not delete blindly; it may include useful assets or user/auth/session history outside Git. Current generated Docker profile homes live under ignored `runtime/hermes/profiles/<profile>/`. |
| Shared skills | `shared/skills/` | Preserve. Introduce manifests that select shared base and role-specific skills for each profile. |
| Shared MCP registry | `shared/mcp/` | Preserve if still useful. Reattach through profile specs/config fragments rather than per-agent generated config. |
| Kanban dispatcher/notifier | `scripts/kanban-compose-dispatcher.py`, `scripts/kanban-mission-notifier.py`, Compose `kanban-*` services | Custom Compose dispatcher removed. Keep `scripts/kanban-mission-notifier.py` as the profile-compatible fan-in/outbox bridge; use native `hermes kanban dispatch` through `kanban-dispatcher` for one-shot dispatch nudges. |
| Docker image/bootstrap | `docker/Dockerfile`, `docker/team-nexus-entrypoint.sh` | Preserve and adapt to single-image/function-service profile runtime. |
| Make targets | `Makefile` | Replace agent-service targets with profile/function-service targets. Add profile validation and bootstrap dry-run targets first. |

## Must not break during migration

- Docker remains runnable.
- Atlas Discord gateway path remains or has a working replacement before old paths are removed.
- Dashboard remains available for inspection.
- Existing shared skills/docs/assets are preserved or intentionally migrated.
- Multi-agent claims remain backed by Kanban/GitHub/evidence artifacts.
- Secrets, auth, profile memory, sessions, logs, checkpoint data, and live Kanban DBs are not committed or overwritten by bootstrap.

## Big-bang cleanup rule

The refactor may use temporary compatibility while building the replacement, but the final state should not retain dead old per-agent service code. Any old file/path left behind must have an active purpose, an explicit archive note, or be removed.
