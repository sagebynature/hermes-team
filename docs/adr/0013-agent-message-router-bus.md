# ADR-0013: Structured Agent Message Router / Bus

Status: Accepted

Date: 2026-05-05

## Context

Team Nexus runs one Hermes runtime per agent. Each specialist has its own gateway, home, workspace, memory, sessions, logs, credentials boundary, and lifecycle. This is useful for operational separation, but it means agent-to-agent coordination needs an explicit control plane.

Discord is valuable as a human-visible mission room: operators can see status, handoffs, and final summaries. It is a poor substrate for bot-to-bot control because free-form bot mentions are hard to audit, can trigger loops, duplicate work, bypass Kanban state, and burn tokens without clear stop conditions.

Kanban is already the durable execution source of truth. Atlas is already the default coordinator and user-facing synthesis point.

## Decision

Use a structured router/bus as the agent-to-agent control plane for Team Nexus.

The router accepts bounded message envelopes, validates sender/recipient policy, enforces TTL and fanout limits, and materializes worker requests as Kanban tasks. Kanban remains the execution source of truth. Discord remains human-facing and may summarize routed work, but Discord bot mentions are not guaranteed dispatch and are not the A2A work path.

Atlas is the default aggregator for user-facing results. Workers return concise deliverables through Kanban task completion comments and artifact paths, then Atlas synthesizes the final answer unless the operator explicitly requests a direct specialist response.

## Consequences

Positive:

- Agent-to-agent work is bounded by structured envelopes, route policy, TTL, fanout limits, and expected outputs.
- Kanban keeps durable state for ready/running/done/blocked work instead of relying on Discord transcripts.
- Atlas remains the default synthesis point, reducing scattered specialist output.
- Router events can be audited and linked to Kanban tasks.
- Loop prevention and dedupe can be designed into the dispatch path from the start.
- Discord remains readable for humans instead of becoming noisy bot chatter.

Negative:

- The system is less theatrical than real-time bot-to-bot Discord conversations.
- Operators and agents must follow an explicit message envelope and route policy.
- The router adds another protocol surface that needs validation, documentation, and tests.
- Some quick ad-hoc exchanges must become Kanban tasks or structured routed requests.

Follow-up:

- Build a small SQLite-backed router under `shared/router/`.
- Add a route policy file and CLI for send/list/inspect/sweep operations.
- Integrate routed worker requests with the existing Compose-aware Kanban dispatcher.
- Add validation and tests for envelope shape, recipients, TTL, fanout, dedupe, and loop prevention.
