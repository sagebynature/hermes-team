# ADR-0007: Keep automatic dispatch explicit rather than hidden inside startup

Status: Accepted

Date: 2026-05-04

## Context

Automatic worker dispatch has side effects: it can claim tasks, launch containers, spend model tokens, and write task state. During early Team Nexus operation, it is safer for operators to start and observe dispatch intentionally.

## Decision

Do not autostart the Compose-aware Kanban dispatcher as part of `docker compose up` yet.

Start gateways with:

```bash
make up
```

Start automatic dispatch separately with:

```bash
make kanban-dispatcher-daemon
```

## Consequences

Positive:

- Safer first live runs.
- Operators can run dry-run before real dispatch.
- Dispatcher failures are visible in the terminal.
- No hidden background worker mutates the board unexpectedly.

Tradeoffs:

- Full automation requires a second terminal/process.
- If the dispatcher is not running, ready tasks will remain queued.

## Implementation notes

Safe dry-run:

```bash
make kanban-dispatcher-once DRY_RUN=1
```

Future option: add a dedicated Compose service or launchd/systemd user service for the dispatcher once behavior is trusted.

