# ADR-0004: Use Discord as the human mission room, not the source of truth

Status: Accepted

Date: 2026-05-04

## Context

The user wants visible inter-agent collaboration in Discord. Discord is excellent for human visibility and interaction, but poor as a durable routing database or task ledger. Unbounded peer-to-peer agent chatter would become noisy, hard to audit, and prone to loops.

## Decision

Use Discord as the human-facing mission room.

Recommended channels:

```text
#nexus-command   user talks to Atlas
#nexus-status    compact progress/status posts
#nexus-handoffs  optional handoff/escalation summaries
#nexus-lab       optional bounded roundtables
```

Discord may mirror important events, but Kanban remains the source of truth.

## Consequences

Positive:

- Humans can observe missions and intervene.
- Atlas can provide concise status and final synthesis.
- The system avoids chaotic agent-to-agent chat loops.

Tradeoffs:

- Not every low-level task event appears in Discord.
- Debugging sometimes requires inspecting Kanban, logs, or workspaces.

## Implementation notes

Discord bot configuration comes from `.env`:

```bash
DISCORD_BOT_TOKEN=
DISCORD_ALLOWED_USERS=
DISCORD_HOME_CHANNEL=
```

Optional status/handoff webhooks:

```bash
DISCORD_STATUS_WEBHOOK_URL=
DISCORD_HANDOFFS_WEBHOOK_URL=
```

Do not post secrets, raw logs, or full tool output to Discord.

