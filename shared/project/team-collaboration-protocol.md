# Team Nexus Collaboration Protocol

## Source of truth

Kanban is the durable task and coordination layer. Discord is the human visibility layer. If a task, decision, blocker, handoff, or artifact matters, it must be represented on the shared Kanban board or in a workspace file; Discord may summarize it, but Discord is not the source of truth.

## Roles

- Atlas routes, coordinates, resolves disagreement, and synthesizes user-facing answers.
- Specialists execute, review, and request routed support through Atlas.
- user can ask for a direct specialist answer, but multi-agent work should still be captured in Kanban.

## Required inter-agent request shape

Every inter-agent request must include:

- id
- conversation_id
- from
- to
- objective
- constraints
- expected_output
- ttl
- next_action

Keep deliverables bounded. If a request is too broad, block with a precise question instead of guessing.

## Collaboration modes

### Mission graph

Atlas breaks a mission into specialist tasks, links dependencies, and posts a compact assignment summary.

### Fan-out / fan-in

Atlas asks multiple specialists to work independently in parallel, then creates or performs a synthesis step after the parent tasks complete. This is the default pattern for research, roundtables, cross-functional planning, and tradeoff analysis.

### Specialist handoff

A specialist completes a bounded task, adds a Kanban handoff comment, and writes durable artifacts to `/workspace/outbox` or `/workspace/artifacts` for private work. Use `/shared/project/artifacts` for deliberate cross-agent handoff artifacts that downstream specialists must read.

### Review gate

A reviewer checks a completed task for scope, quality, risk, or release readiness. If changes are required, Atlas creates a new follow-up task rather than rerunning the same task informally.

### Product / engineering handshake

Vega defines or trims product scope. Forge estimates feasibility and implementation shape. Atlas reconciles tradeoffs for user.

### Design / product / growth loop

Lumen explores user experience, Vega checks product fit, and Blitz checks messaging or go-to-market fit. Atlas synthesizes the loop into a decision or next experiment.

### Blocked task escalation

A specialist blocks the task with the exact missing information, risk, or decision needed. Atlas either asks user or routes a focused follow-up to another specialist.

### Roundtable

Atlas creates one short task per relevant role. Each response is limited to five bullets. Atlas summarizes agreement, disagreement, and a recommended decision. Agents do not debate indefinitely.

## Discord operating model

- `#nexus-command`: user talks to Atlas. This is the primary mission intake channel.
- `#nexus-status`: Atlas posts task graphs, status milestones, blockers, completions, and final summaries.
- `#nexus-handoffs`: Optional channel for compact specialist handoff summaries if status updates become noisy.
- `#nexus-social` or `#nexus-lab`: Optional channel for explicitly requested brainstorming or low-stakes roundtables.

Discord etiquette:

- Keep public updates short and attributed by agent name.
- Do not dump raw transcripts or full tool output.
- Post artifact paths and short summaries instead of large blobs.
- Ask Atlas to route follow-up work rather than starting side conversations.
- Do not expose secrets, tokens, auth files, private user data, or unredacted logs.

## Mission thread convention

For multi-agent missions, Atlas should create or reuse a Discord thread when the platform supports it.

- Thread title: `mission: <short-name>`
- Kanban conversation id: `mission_<slug>_<yyyymmdd>`
- Task bodies should include the conversation id, assignee, objective, expected output, constraints, and dependency notes.
- Atlas posts the task graph and final synthesis in the mission thread.
- `#nexus-status` receives compact milestones only.

## Kanban comment conventions

Use predictable comment prefixes so the board reads like a collaboration transcript:

- `[handoff]` completed contribution, recommendation, artifact paths, and requested next reviewer if any.
- `[question]` specific question blocking progress.
- `[review]` approval, requested changes, or risk note.
- `[decision]` decision made by Atlas or user.
- `[status]` short progress update.

## Discord-ready specialist handoff shape

When a specialist completes a Kanban task, include a compact handoff that Atlas can quote in Discord:

- contribution
- recommendation
- risks
- artifact paths
- requested next reviewer, if any

Keep this summary to five bullets or fewer.
