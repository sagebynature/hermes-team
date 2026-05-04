# ADR-0002: Keep shared project context read-only and agent workspaces isolated

Status: Accepted

Date: 2026-05-04

## Context

Agents need common project context, shared team conventions, and durable artifacts. At the same time, agents should not accidentally corrupt shared source material or overwrite each other's intermediate work.

## Decision

Use private writable workspaces per agent and mount shared project context read-only.

Writable per-agent paths:

```text
agents/<agent>/home      -> /opt/data
agents/<agent>/workspace -> /workspace
```

Shared read-only paths:

```text
shared/project -> /shared/project:ro
shared/skills  -> /shared/skills:ro
shared/mcp     -> /shared/mcp:ro
```

Shared writable coordination path:

```text
shared/kanban -> /shared/kanban
```

## Consequences

Positive:

- Agents can read the same operating doctrine and mission context.
- Agents cannot casually mutate shared project instructions, team skills, or MCP registry files from inside normal runtime containers.
- Agent-local artifacts and notes remain attributable.

Tradeoffs:

- Updating shared context requires repo-level edits, not in-container mutation.
- Cross-agent handoff artifacts need conventions so Atlas knows where to look.

## Implementation notes

Workspace convention:

```text
/workspace/inbox      incoming task briefs
/workspace/outbox     finished handoffs
/workspace/artifacts  generated durable files
/workspace/notes      working notes
```

Specialists should put durable outputs in `outbox/` or `artifacts/` and reference them in Kanban comments.

