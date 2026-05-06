# Team Nexus Collaboration Protocol

## Source of truth

Kanban is the durable task and coordination layer. Discord is the human visibility layer. If a task, decision, blocker, handoff, or artifact matters, it must be represented on the shared Kanban board or in a workspace file; Discord may summarize it, but Discord is not the source of truth.

## Roles

- Atlas routes, coordinates, resolves disagreement, and synthesizes user-facing answers.
- Specialists execute, review, and request routed support through Atlas.
- user can ask for a direct specialist answer, but multi-agent work should still be captured in Kanban.

Registered Kanban assignees are `atlas`, `vega`, `scout`, `forge`, `lumen`, `blitz`, `ledger`, and `sentinel`. Do not invent assignee names; map generic roles to these agents.

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

### Deep interview / clarification

Atlas interviews the user before routing when ambiguity would materially change scope, cost, risk, timeline, success criteria, or assignee choice. Atlas should ask a bounded set of 3-7 numbered questions, label required vs optional answers, propose defaults for low-stakes choices, and stop once the mission is route-ready. Specialists should not interview the user directly unless Atlas routes a focused clarification task to them. Atlas should not create Kanban tasks for a new mission until the user explicitly approves execution or asks Atlas to create tasks.

### Mission graph

Atlas breaks a mission into specialist tasks, links dependencies, and posts a compact assignment summary.

Mission routes should include:

- `conversation_id`
- objective and success criteria
- accepted assumptions and excluded scope
- task graph with registered Team Nexus assignee, objective, dependency, expected output, artifact path, and optional max runtime
- specialist rationale for each chosen assignee
- review gates
- final Atlas synthesis plan

Use relevant specialists, not all specialists blindly. Display generic role labels only as rationale; route and Kanban assignee fields must use registered agent names. When tasks are created, dependencies should be represented in Kanban using task parents or `kanban link`, not only described in Discord prose.

### Fan-out / fan-in

Atlas asks multiple specialists to work independently in parallel, then creates or performs a synthesis step after the parent tasks complete. This is the default pattern for research, roundtables, cross-functional planning, and tradeoff analysis.

### Direct specialist request

When user asks Atlas to ask a named registered specialist for that specialist's own answer, statement, role summary, or opinion, treat it as explicit approval for one bounded durable task to that specialist. Atlas must not answer in the specialist's voice and must not rely on `@Specialist` Discord prose as delegation. Atlas should create the Kanban/router work item, report the task/message ID, then wait for the specialist's completed result/comment/artifact before presenting it as the specialist's statement. If routing or task creation fails, Atlas should say it failed and provide no fake specialist response.

### Specialist handoff

A specialist completes a bounded task, adds a Kanban `[handoff]` comment, and writes durable artifacts to `/workspace/outbox` or `/workspace/artifacts` for private work. Use `/shared/project/artifacts/<conversation_id>/...` for every artifact that downstream specialists, Atlas synthesis, or reviewers must read.

A cross-agent handoff is complete only when the Kanban comment points at the durable shared artifact path. Do not rely on Discord text, raw transcripts, private workspace files, or prose-only task completion as the handoff record.

Artifact visibility contract:

- Producer tasks must create the expected files in `/shared/project/artifacts/<conversation_id>/` before marking the task done when any downstream task depends on those files.
- Producer tasks must add a compact `[handoff]` comment with producer, consumer, source task id, artifact path, summary, and next reviewer/consumer.
- Consumer tasks must inspect parent task bodies/results/comments and `/shared/project/artifacts/<conversation_id>/` before blocking on missing files.
- If an artifact is missing, the blocker must name the upstream producer task id, expected path, and exact artifact type needed; Atlas should route a focused repair task to the producer rather than asking the consumer to guess or recreate hidden work.

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


## Code-writing and GitHub workflow

Code-writing tasks must preserve agent isolation, GitHub traceability, and downstream handoff quality.

Required sequence for any task that modifies code or repository files:

1. Work in your own workspace. Do not edit another agent's private `/workspace` files or mutate a shared checkout. Use your agent-owned `/workspace` for clones, worktrees, notes, test outputs, and draft artifacts.
2. If the task uses GitHub, clone the repository into your own workspace and create a Git worktree for the task branch before changing files. The normal shape is:
   - clone/cache path: `/workspace/repos/<repo>`
   - worktree path: `/workspace/worktrees/<task-id-or-slug>`
   - branch: `<type>/<short-task-slug>` such as `feat/add-billing-import` or `fix/login-redirect`
3. When picking up, continuing, reviewing, or repairing upstream work, read the upstream worker log first. Use the task body, parent tasks, Kanban comments, and the referenced `worker-log.md` path to understand what was done, why, and which branch/worktree contains the work before making changes.
4. Commit with Conventional Commits. Use `type(scope): summary` when a scope helps, and include a body for non-obvious decisions. Common types are `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `chore`, `perf`, and `revert`.
5. Before completing the Kanban task, push the worktree branch to its remote. If push is impossible, block the task and explain the credential, remote, or policy issue; do not mark code work done with only local commits.
6. Before completing the Kanban task, update the worker log with what was done, how it was done, why key decisions were made, and where the work lives. The log entry must include branch name, worktree path, commit SHA(s), pushed remote, tests/checks run, changed files, artifact paths, and any follow-up risks.
7. Complete with a `[handoff]` comment that points to the worker log and any shared artifacts. Downstream agents should be able to resume from the log without reading private scratch files or guessing branch state.

Worker log location:

- Mission-scoped code work should use `/shared/project/artifacts/<conversation_id>/worker-log.md` so every downstream agent can read one chronological log.
- If no `conversation_id` exists, create one from the task slug before routing code work rather than scattering logs across private workspaces.

Recommended worker log entry shape:

```text
## <UTC timestamp> — <agent> — <task id/title>

- branch: <type/short-task-slug>
- worktree: /workspace/worktrees/<task-id-or-slug>
- remote: origin <git remote URL or owner/repo>
- pushed: yes, origin/<branch> at <commit sha>
- what: <files/features/fixes produced>
- how: <implementation and verification approach>
- why: <key decisions and tradeoffs>
- checks: <commands run and results>
- artifacts: <shared artifact paths, PR URL if created>
- follow-ups: <known risks or none>
```

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

- `[handoff]` completed contribution plus one or more durable artifact paths. Required for any cross-agent handoff. Include the producer, intended consumer, artifact path under `/shared/project/artifacts`, and requested next reviewer if any.
- `[question]` specific question blocking progress.
- `[review]` approval, requested changes, or risk note.
- `[decision]` decision made by Atlas or user. Include the decision owner, decision summary, rationale, and any decision artifact path under `/shared/project/artifacts` when the decision depends on a durable memo or synthesis.
- `[status]` short progress update.

Recommended shapes:

```text
[handoff] producer=<agent> consumer=<agent|atlas> artifact=/shared/project/artifacts/<file> summary=<one sentence> next=<optional task/reviewer>
[decision] owner=<atlas|user> decision=<one sentence> rationale=<why> artifact=/shared/project/artifacts/<optional memo>
```

`[handoff]` and `[decision]` comments should point to artifacts rather than embedding long content in the comment. Keep comments compact enough for Atlas to quote in Discord.

## Discord-ready specialist handoff shape

When a specialist completes a Kanban task, include a compact handoff that Atlas can quote in Discord:

- contribution
- recommendation
- risks
- artifact paths
- requested next reviewer, if any

Keep this summary to five bullets or fewer.
