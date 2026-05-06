# Profile-driven runtime migration inventory

Status: Draft
Date: 2026-05-06
Related: `docs/architecture/profile-driven-team-nexus.md`, `docs/adr/0014-profile-driven-team-nexus.md`

This inventory starts Phase 0 of the big-bang profile-driven refactor. It identifies current runtime surfaces that must either be migrated into the Hermes profile model or removed before the refactor is considered complete.

## Current runtime surfaces

| Surface | Current path(s) | Migration disposition |
|---|---|---|
| Agent roster registry | `shared/team-agents.yaml`, `scripts/team_registry.py`, `generated/team-agents.mk` | Superseded by `profiles/team-nexus.profiles.yaml` and future profile renderer. Keep only until the new renderer owns Docker/host outputs. |
| Per-agent Compose services | `docker-compose.agents.generated.yml` | Remove after functional services replace agent services. Profiles become identity; services become gateway/dashboard/dispatcher/admin. |
| Per-agent dashboard services | `docker-compose.dashboards.generated.yml`, `nginx/dashboards.conf` | Migrate to functional/light dashboard model. Preserve useful dashboard theme/plugin assets. |
| Per-agent homes | `agents/*/home/` | Runtime-owned state. Do not delete blindly. Bootstrap must not overwrite `.env`, auth, sessions, memory, logs, gateway state, or live DBs. |
| Shared skills | `shared/skills/` | Preserve. Introduce manifests that select shared base and role-specific skills for each profile. |
| Shared MCP registry | `shared/mcp/` | Preserve if still useful. Reattach through profile specs/config fragments rather than per-agent generated config. |
| Kanban dispatcher/notifier | `scripts/kanban-compose-dispatcher.py`, `scripts/kanban-mission-notifier.py`, Compose `kanban-*` services | Reassess. Prefer native profile/Kanban dispatcher semantics; keep only pieces needed for profile-compatible notification/fan-in. |
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
