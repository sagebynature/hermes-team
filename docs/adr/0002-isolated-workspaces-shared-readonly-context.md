# ADR-0002: Keep shared project context read-only and agent workspaces isolated

Status: Accepted

Date: 2026-05-04

## Context

Agents need common project context, shared team conventions, and durable artifacts. At the same time, agents should not accidentally corrupt shared source material or overwrite each other's intermediate work.

## Decision

Use private writable workspaces per agent and mount shared project context read-only, with one explicit writable submount for cross-agent handoff artifacts.

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

Shared writable coordination and handoff paths:

```text
shared/kanban            -> /shared/kanban:rw
shared/project/artifacts -> /shared/project/artifacts:rw
```

The Compose manifest uses shorthand bind mounts with explicit `:ro` or `:rw` suffixes for the shared mounts so the intended permissions are visible in review without expanding every mount into long-form YAML.

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
/workspace/outbox     finished private handoffs
/workspace/artifacts  agent-local generated durable files
```

Cross-agent artifact convention:
```text
/shared/project/artifacts  shared handoff artifacts consumed by downstream agents
```

Specialists should put private outputs in `/workspace/outbox` or `/workspace/artifacts`. If another agent must consume the output, copy or write the bounded handoff artifact under `/shared/project/artifacts` and reference it with a `[handoff]` Kanban comment.

