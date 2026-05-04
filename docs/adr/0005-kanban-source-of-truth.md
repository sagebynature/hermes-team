# ADR-0005: Use Hermes Kanban as the durable collaboration source of truth

Status: Accepted

Date: 2026-05-04

## Context

Multi-agent work needs persistent task state, assignees, dependencies, blockers, comments, handoffs, and completion status. Chat alone is not sufficient.

## Decision

Use Hermes Kanban as the durable collaboration source of truth.

Every agent sets:

```yaml
HERMES_KANBAN_HOME: /shared/kanban
```

and mounts:

```text
./shared/kanban:/shared/kanban
```

## Consequences

Positive:

- All agents see the same task board.
- Decisions, blockers, and handoffs survive process restarts.
- Atlas can reconstruct mission state without reading Discord history.
- The dispatcher has a concrete queue to poll.

Tradeoffs:

- The shared board is runtime state and should not be committed.
- Operators must understand that Kanban is a SQLite board, not a daemon.

## Implementation notes

Initialize with:

```bash
make kanban-init
```

Inspect with:

```bash
make kanban-list
make kanban-stats
make kanban-watch
```

Runtime files live under:

```text
shared/kanban/
```

and are ignored by git.

