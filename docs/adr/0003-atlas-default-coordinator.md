# ADR-0003: Use Atlas as the default coordinator and synthesizer

Status: Accepted

Date: 2026-05-04

## Context

Team Nexus should feel collaborative without becoming an unbounded agent group chat. Users need one reliable place to issue missions, receive updates, and get final synthesized answers.

## Decision

Atlas is the default human-facing coordinator and synthesizer.

Atlas owns:

- mission intake;
- task decomposition;
- assignment routing;
- dependency/blocker management;
- conflict resolution;
- final user-facing synthesis.

Specialists execute bounded work and return structured handoffs.

## Consequences

Positive:

- Users have one default interface for multi-agent missions.
- Specialist output is synthesized instead of scattered.
- Disagreements and blockers have a clear owner.
- Discord stays readable.

Tradeoffs:

- Atlas can become a bottleneck on highly parallel missions.
- Direct specialist interaction should be reserved for explicit user requests or narrow tasks.

## Implementation notes

Atlas-specific collaboration rules live in:

```text
agents/atlas/home/AGENTS.md
```

Team-wide collaboration rules live in:

```text
shared/project/team-collaboration-protocol.md
```

