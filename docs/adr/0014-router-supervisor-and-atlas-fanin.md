# ADR-0014: Router Supervisor and Atlas Fan-In

Status: Accepted

Date: 2026-05-06

## Context

Team Nexus has two durable ledgers:

- The Team Nexus router records who Atlas attempted to reach, why, under which conversation, and with which bounded envelope.
- Hermes Kanban records execution state for each worker task.

Before this decision, Atlas could still create worker Kanban tasks directly for multi-agent prompts such as "ask everyone to introduce themselves." That produced execution tasks, but it bypassed router conversation evidence. Atlas could say it had activated specialists without being able to cite router message IDs. Operators then had to inspect Kanban manually and there was no automatic fan-in trigger for Atlas to synthesize the completed worker results.

## Decision

Use router-first fanout for Team Nexus multi-agent requests and add a router supervisor to bridge Kanban execution outcomes back into router conversation state.

The source-of-truth split is:

- Router: coordination/audit source of truth. It owns conversations, message IDs, route policy, fanout, message status, conversation terminal events, and Atlas report task creation.
- Kanban: execution source of truth. It owns ready/running/done/blocked/failed task state, worker runs, logs, and artifacts.

The supervisor pass performs three actions:

1. Dispatch pending router messages into Kanban tasks.
2. Sync completed/blocked/failed Kanban outcomes back onto router messages and aggregate conversations.
3. Optionally create exactly one Atlas synthesis task for each completed or needs-attention router conversation.

For a multi-agent request, Atlas must create router messages first. The operator-facing acknowledgement must include the router conversation ID and message IDs; after dispatch, the Kanban task IDs are inspectable on each message. Atlas must not claim a worker replied unless router/Kanban evidence exists.

## Consequences

Positive:

- Multi-agent fanout is auditable from a single router conversation.
- Atlas cannot honestly claim team activation without inspectable router message IDs or Kanban task IDs.
- Worker terminal outcomes become router events that can drive final synthesis.
- Operators can run one supervisor daemon instead of manually alternating `router-dispatch`, Kanban dispatcher checks, and `router-sync`.
- Router doctor can flag likely direct Kanban fanout without a router envelope.

Negative:

- There is another long-running service to operate (`router-supervisor`).
- Atlas report task creation can recurse into Atlas work if enabled carelessly; dispatcher Atlas execution remains opt-in through `KANBAN_DISPATCH_INCLUDE_ATLAS`.
- Fanout plus report creation increases provider/API pressure; dispatch concurrency must still be tuned conservatively.

## Implementation notes

- `scripts/team-message-router.py` stores `conversations`, aggregates terminal message counts, emits `conversation_completed` or `conversation_needs_attention` events, and can create idempotent Atlas report tasks with key `router-conversation:<conversation-id>:report`.
- `make router-supervisor-once` runs one supervisor pass.
- `make router-supervisor-daemon` starts the Compose service.
- `ROUTER_SUPERVISOR_CREATE_REPORT_TASKS=1` enables Atlas synthesis task creation.
- `KANBAN_DISPATCH_INCLUDE_ATLAS=1` allows the Compose-aware Kanban dispatcher to execute Atlas-assigned report tasks.
- `make router-doctor` warns on likely multi-agent Kanban tasks that bypassed the router envelope.
