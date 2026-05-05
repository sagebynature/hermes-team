# ADR-0006: Use a Compose-aware Kanban dispatcher instead of embedded Hermes profile dispatch

Status: Accepted

Date: 2026-05-04

## Context

Hermes has built-in gateway dispatch support for Kanban, but that path assumes assignees are local Hermes profiles visible under the dispatcher's home. Team Nexus uses one Docker Compose service per agent, each with a separate `HERMES_HOME`.

Using embedded dispatch in this architecture would risk spawning the wrong runtime, failing to find profiles, or duplicating dispatcher ownership.

## Decision

Disable every embedded Hermes gateway Kanban dispatcher and use a Compose-aware dispatcher script, normally run by the Docker Compose service `kanban-dispatcher`.

All agent configs use:

```yaml
kanban:
  dispatch_in_gateway: false
```

The dispatcher service is:

```text
kanban-dispatcher
```

Dispatcher implementation:

```text
scripts/kanban-compose-dispatcher.py
```

Manual one-task wrapper:

```text
scripts/kanban-dispatch-compose.sh
```

Agent registry:

```text
shared/team-agents.yaml
```

## Consequences

Positive:

- Dispatch maps directly to Compose services.
- One dispatcher owns worker spawning.
- Dry-run behavior can be tested without mutation.
- Automatic dispatch shows the normal Kanban lifecycle: `ready -> running -> done`.
- The architecture remains explicit and inspectable.

Tradeoffs:

- The dispatcher is project-specific glue code.
- Operators must not re-enable embedded gateway dispatch while this dispatcher is active.
- The dispatcher mirrors the Hermes claim transition locally so Compose-service dispatch can preserve running-state observability.

## Implementation notes

Dry-run:

```bash
make kanban-dispatcher-once DRY_RUN=1
```

Continuous dispatch:

```bash
make kanban-dispatcher-daemon
```

Manual dispatch:

```bash
make kanban-dispatch AGENT=forge TASK=<task-id>
```

The dispatcher claims a ready task before spawning the worker container, so operators and dashboards can observe the normal lifecycle:

```text
ready -> running -> done
```

The dispatcher runs commands like:

```bash
docker compose run --rm forge chat -q "work kanban task <task-id>"
```

If the worker command exits non-zero before completing the task, the dispatcher records `dispatch_failed`, closes that run as `spawn_failed`, and requeues the task to `ready`.

