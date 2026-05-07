# ADR-0009: Use shared read-only skills and MCP registries with agent-local extensions

Status: Accepted

Date: 2026-05-04

## Context

The virtual team needs common team-wide skills, MCP templates, and integration conventions. At the same time, each specialist may need agent-specific skills or auth state.

## Decision

Mount shared skills and MCP material read-only into every container:

```text
shared/skills -> /shared/skills:ro
shared/mcp    -> /shared/mcp:ro
```

Keep profile-local skills and runtime extensions under:

```text
runtime/hermes/profiles/<profile>/skills
```

Profile-local runtime skills are allowed, but Team Nexus canonical skills live in `shared/skills/`. Any skill required by the dispatcher or more than one profile must be promoted to `shared/skills/` and selected through the shared skill manifests.

## Consequences

Positive:

- Team-wide procedures are consistent.
- Shared MCP templates are inspectable and versioned.
- Agents can still carry role-specific skills.
- Runtime agents cannot casually mutate shared team-wide instructions.

Tradeoffs:

- Updating shared skills/MCP material is a repo operation.
- Operators must decide whether a new procedure is team-wide or agent-specific.

## Implementation notes

The repo intentionally uses a simple skills layout:

```text
shared/skills/                                 team-wide, read-only in containers
runtime/hermes/profiles/<profile>/skills/      profile-local runtime extensions, ignored state
shared/skills/manifests/                       shared base and role-specific skill selection
```

There are no ad-hoc skills-sync Makefile targets by design. Promote reusable or dispatcher-required procedures into `shared/skills/`, then render/validate profiles with the normal profile commands.

