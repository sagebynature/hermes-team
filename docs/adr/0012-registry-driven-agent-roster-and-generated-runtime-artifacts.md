# ADR-0012: Use registry-driven agent roster and generated runtime artifacts

Status: Accepted

Date: 2026-05-05

## Context

Team Nexus runs a dedicated Hermes runtime per specialist. That model gives strong operational boundaries, but it also creates repeated agent lists across Make targets, Docker Compose services, dashboard routing, nginx proxy blocks, project instructions, and operations docs.

Manual copy/paste of roster data increases drift risk. Adding or removing an agent can leave stale ports, services, dashboard routes, or Kanban assignee instructions behind.

## Decision

Use `shared/team-agents.yaml` as the source of truth for active Team Nexus agent roster metadata.

Registry metadata includes agent slug, service name, display name, role, gateway port, dashboard port, visibility flags, dispatch flag, default route, and lifecycle state. Repetitive runtime artifacts should be generated from or validated against this registry.

Operators should use lifecycle commands instead of manual copy/paste for routine roster changes:

```bash
make agent-add SLUG=raven NAME=Raven ROLE='Legal / Compliance'
make agent-disable SLUG=raven
make agent-archive SLUG=raven
```

Generated and validated artifacts include, at minimum:

- `generated/team-agents.mk`
- `docker-compose.agents.generated.yml`
- `docker-compose.dashboards.generated.yml`
- `nginx/dashboards.conf`
- `shared/project/generated/team-roster.md`
- agent home/workspace scaffolding from templates
- registry, filesystem, config, Compose, nginx, plugin, and Kanban-assignee validation

## Consequences

Positive:

- Less hardcoding across Make, nginx, docs, and instructions.
- Safer add/disable/archive workflows for agents.
- Disabled agents can keep durable state without appearing in runtime generation.
- Archived agents can be moved under `agents/.archived/` without destructive deletion.
- Operators have one validation path for drift: `make validate`, `make check-generated`, and `make preflight`.

Tradeoffs:

- Generated files must be kept current after registry edits.
- Registry schema changes require updates to `scripts/team_registry.py`, templates, validation, and docs.
- Hand-editing generated files is temporary and will be overwritten by `make generate`.
- Lifecycle commands are conservative; exceptional recovery may still require manual review.

## Implementation notes

- Keep `shared/team-agents.yaml` human-readable and stdlib-parseable by `scripts/team_registry.py`.
- Keep lifecycle operations non-destructive. Disable preserves directories. Archive moves directories to `agents/.archived/<slug>-YYYYMMDD` and marks the registry entry archived.
- Validation should ignore directories under `agents/.archived/`.
- Registry-driven generation complements ADR-0011's dedicated-runtime model; it does not collapse Team Nexus into Hermes profiles.
- Existing Kanban tasks are not mutated by registry validation or lifecycle commands. Disable only warns when open tasks are still assigned to that agent.
