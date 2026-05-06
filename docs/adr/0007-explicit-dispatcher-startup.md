# ADR-0007: Keep automatic dispatch explicit and run it as a Compose service

Status: Superseded by ADR-0014

Date: 2026-05-04

Updated: 2026-05-06

Supersession note: Team Nexus no longer runs a separate Compose-aware dispatcher service for real work. The current profile-driven runtime hosts native dispatch in `atlas-gateway`; `kanban-dispatcher` is only an optional dry-run/preview function service.

## Context

Automatic worker dispatch has side effects: it can claim tasks, launch containers, spend model tokens, and write task state. During early Team Nexus operation, it is safer for operators to start and observe dispatch intentionally.

The first implementation ran the dispatcher as a host-side foreground Python process. That worked for validation, but it left the daemon outside the Compose runtime even though all other Team Nexus long-running processes are Compose services.

## Decision

Run the Compose-aware Kanban dispatcher as a Docker Compose service named `kanban-dispatcher`, but keep it behind the explicit Compose `dispatcher` profile.

Plain gateway startup remains:

```bash
make up
```

Automatic dispatch starts separately with:

```bash
make kanban-dispatcher-daemon
```

which runs:

```bash
docker compose --profile dispatcher up -d kanban-dispatcher
```

Stop and inspect it with:

```bash
make kanban-dispatcher-stop
make kanban-dispatcher-logs
```

## Consequences

Positive:

- Dispatcher lifecycle is now visible through Docker Compose.
- The dispatcher can use `restart: unless-stopped` like the gateways.
- Operators can still run dry-run before real dispatch.
- Plain `make up` does not silently start automatic task execution.
- No hidden profile-based Hermes dispatcher competes with the Compose-aware dispatcher.

Tradeoffs:

- The dispatcher container needs access to the host Docker socket.
- The repo is mounted into the dispatcher at the caller's current repo path via `${PWD}` so nested `docker compose run` commands resolve bind mounts correctly without hardcoding a user-specific home path.
- If the dispatcher profile is not running, ready tasks remain queued.

## Implementation notes

The dispatcher service uses Docker-outside-of-Docker:

```yaml
volumes:
  - ./team-nexus:/team-nexus
  - /var/run/docker.sock:/var/run/docker.sock
```

The image includes Docker CLI and Docker Compose v2 so the dispatcher can run named worker containers with:

```bash
docker compose run --rm --name team-nexus-<agent>-task-<task-id> <agent> chat -q "work kanban task <task-id>"
```

Worker dispatch has a hard timeout. On timeout, the dispatcher removes the named one-off container, records `dispatch_timed_out`, closes the run as `timed_out`, and blocks the task for operator review instead of requeueing it into a loop.

Safe dry-run:

```bash
make kanban-dispatcher-once DRY_RUN=1
```

Tuning:

```bash
KANBAN_DISPATCH_INTERVAL=60
KANBAN_DISPATCH_MAX_TASKS=1
KANBAN_DISPATCH_WORKER_TIMEOUT=900
```
