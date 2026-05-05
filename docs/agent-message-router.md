# Agent message router

## Purpose

The agent message router is the Team Nexus agent-to-agent control plane. It is intended to turn bounded structured requests into trackable Kanban work while keeping Discord human-visible rather than using Discord bot chatter as the execution bus.

Discord bot mentions are not guaranteed dispatch. Router/Kanban is the A2A work path: routed requests become auditable messages, Kanban tasks, handoff comments, and artifact paths that Atlas can synthesize.

## Goals

- Dispatch bounded agent-to-agent work with explicit sender, recipient, objective, expected output, and stop condition.
- Keep Atlas as the default aggregator for user-facing synthesis.
- Reuse Kanban as the durable execution source of truth.
- Validate recipients against the registered Team Nexus roster and route policy.
- Prevent loops with message IDs, TTL, trace checks, and controlled fanout.
- Store enough metadata to inspect what was requested, routed, blocked, completed, or dropped.
- Keep worker prompts concise and require concise return artifacts/comments.

## Anti-goals

- Do not use free-form Discord bot mentions as the primary agent-to-agent bus.
- Do not enable an all-to-all bot swarm or global bot-to-bot Discord chatter.
- Do not let every specialist recursively delegate to every other specialist.
- Do not route raw transcripts, large logs, secrets, auth files, or private user data. The CLI rejects obvious key/token/password assignments and private-key blocks before storage.
- Do not invent dynamic recipients outside the registered roster or explicit group aliases.
- Do not bypass Kanban for work that must be tracked, reviewed, blocked, or handed off.

## Envelope fields

Every routed message should be JSON-serializable and include these fields:

- `id`: unique message ID for dedupe and audit.
- `conversation_id`: mission/thread/workstream ID shared across related requests.
- `parent_id`: optional parent message ID for fanout or follow-up chains.
- `from`: registered sender slug, usually `atlas` for new work.
- `to`: registered recipient slug or explicit group alias.
- `type`: message kind, such as `task.request`, `task.response`, `question`, `status`, or `blocker`.
- `priority`: optional priority such as `low`, `normal`, `high`, or `urgent`.
- `ttl`: remaining hop budget; must be positive before dispatch and decremented on each hop.
- `created_at`: UTC timestamp.
- `requires_response`: boolean indicating whether a response/handoff is expected.
- `reply_to`: expected response recipient, usually `atlas`.
- `summary`: compact human-readable summary.
- `body`: bounded structured payload with objective, constraints, deliverable, and stop condition.
- `artifacts`: list of durable artifact paths relevant to the request or response.
- `trace`: ordered list of agents that already handled the message.

Minimum required fields are `id`, `conversation_id`, `from`, `to`, `type`, `ttl`, `created_at`, `body`, and `trace`.

## Route policy

Initial policy should be conservative:

- Atlas may route to registered workers: `vega`, `scout`, `forge`, `lumen`, `blitz`, `ledger`, and `sentinel`.
- Workers may route responses, blockers, and focused questions back to Atlas.
- Worker-to-worker routes are denied by default unless an explicit route exists for a concrete use case.
- Group aliases must be explicitly registered, for example `product`, `delivery`, or `all-workers`.
- Wide fanout is disabled by default; if allowed by an operator, it must be justified and capped.
- Invalid, disabled, archived, or unknown recipients are rejected before Kanban task creation.
- Every worker request created by the router must include the source message ID in the Kanban task body or comments.

Default operating shape:

```text
user -> Atlas -> router -> Kanban task(s) -> specialist(s) -> Kanban handoff(s) -> Atlas -> user
```

## Loop-prevention checklist

Before routing a message, verify:

- The message `id` has not already been processed.
- `ttl` is greater than zero and does not exceed the max policy TTL.
- The sender and recipient are registered and enabled.
- The sender is allowed to send to the recipient or group alias.
- The recipient is not already in `trace` unless an explicit exception exists.
- Fanout count is within policy.
- Broadcast/group routes do not recursively broadcast.
- The body has a bounded objective, expected output, and stop condition.
- The message does not contain secrets, raw logs, unbounded transcripts, or oversized payloads.
- The routed Kanban task links back to the source message ID and conversation ID.

## When to use Kanban directly instead

Use Kanban directly when the work is already clear and does not require router policy decisions:

- A human/operator is manually assigning a specific bounded task.
- Atlas has already decomposed the mission and knows the exact assignee.
- The task is a routine follow-up, review, or artifact handoff.
- The work should be queued for the existing Compose-aware dispatcher without additional fanout.
- The request is purely task-state management: assign, block, comment, link, close, or inspect.

## When not to route

Do not route when:

- The message is just a human-visible status update for Discord.
- The user asked for a direct single-agent answer and no durable task is needed.
- The request is ambiguous enough that Atlas must clarify scope first.
- The request would expose secrets, credentials, auth files, private user data, or unredacted logs.
- The request would create broad speculative fanout without clear deliverables.
- The same recipient is already working on an equivalent open Kanban task.
- A simple workspace artifact or Kanban comment is the safer handoff.

## Operator workflow

```bash
make router-send FROM=atlas TO=scout SUMMARY='bounded request' GOAL='...' DELIVERABLE='...'
make router-list STATUS=pending
make router-dispatch MAX_MESSAGES=1
make router-list STATUS=dispatched
make kanban-dispatcher-once MAX_TASKS=1
make router-sync
make router-list STATUS=completed
make router-inspect MESSAGE=<message-id>
```

`router-sync` reads the shared Kanban database and records worker outcomes back onto dispatched router messages. Completed Kanban tasks become router `completed`; blocked tasks become router `blocked`; failed task runs become router `failed`. The original Kanban task/run remains the execution record, while the router event log becomes the Atlas-friendly coordination view.

## Troubleshooting

- Missing specialist response: inspect the router and Kanban task first, then dispatcher logs. Discord bot mentions are not guaranteed dispatch.
- Atlas mentioned specialists but nobody replied: check whether Atlas actually created router/Kanban work. A Discord `@Vega @Forge ...` post alone is not a control-plane event.
- Router message not moving: run `make router-list STATUS=pending`, inspect the message with `make router-inspect MESSAGE=<message-id>`, then run `make router-dispatch`.
- Worker finished but router still says dispatched: run `make router-sync`, then inspect the message again. This syncs completed, blocked, or failed Kanban task outcomes back into the router event log so Atlas can synthesize from router state instead of manually scraping Kanban runs.
- Unsafe Discord bot mode: run `python3 scripts/team_registry.py validate-discord-bot-mode`; remove `DISCORD_ALLOW_BOTS=all` if present.
- Unknown recipient: check `shared/team-agents.yaml` and generated roster docs for enabled agent slugs.
- Route denied: confirm the sender is allowed to reach the recipient or group alias under router policy.
- Duplicate work: search by `conversation_id` and source message ID before creating another request.
- Loop or repeated fanout: check TTL, `trace`, parent IDs, and group routes; block recursive broadcast.
- Too much output: tighten the envelope summary, body constraints, deliverable shape, and max response size.
- Sensitive content risk: stop routing, redact the payload, and use a safer artifact or operator-only handoff path.
- Human visibility gap: post a compact Discord status summary after the Kanban/router state is correct; do not treat Discord as the source of truth.
