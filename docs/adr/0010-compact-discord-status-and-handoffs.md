# ADR-0010: Mirror only compact status and handoffs to Discord

Status: Accepted

Date: 2026-05-04

## Context

Users need visibility into multi-agent work, but dumping raw transcripts, full tool output, or every Kanban event into Discord would make the mission room noisy and risky.

## Decision

Mirror only compact status, blocker, handoff, review, and final synthesis messages to Discord.

Durable details belong in:

- Kanban comments;
- workspace files;
- artifacts;
- logs when needed for debugging.

## Consequences

Positive:

- Discord stays readable.
- Humans see the important milestones.
- The system avoids leaking tool noise or sensitive logs.
- Atlas can quote concise specialist handoffs.

Tradeoffs:

- Operators may need to inspect Kanban/workspaces for full detail.
- Specialists must produce good summaries, not just raw output.

## Implementation notes

Webhook helper:

```text
scripts/discord-post-status.py
```

Dry-run target:

```bash
make discord-status-dry-run MESSAGE='hello from Team Nexus'
```

Optional env vars:

```bash
DISCORD_STATUS_WEBHOOK_URL=
DISCORD_HANDOFFS_WEBHOOK_URL=
```

Recommended Kanban comment prefixes:

```text
[handoff]
[question]
[review]
[decision]
[status]
```

