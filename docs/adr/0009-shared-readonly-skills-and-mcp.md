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

Keep agent-specific skills under:

```text
agents/<agent>/home/skills
```

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
shared/skills/                 team-wide, read-only in containers
agents/<agent>/home/skills/    agent-specific, writable/committable
```

There are no skills-sync Makefile targets or sync scripts by design.

