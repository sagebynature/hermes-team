# Profile-Driven Team Nexus Design and Refactor Plan

Date: 2026-05-06
Status: Draft for review

## North star

Team Nexus should become a Hermes-native, profile-driven multi-agent system: software-delivery-first, expandable into a broader personal AI company. It should model the Hermes multi-agent reference architecture as closely as possible and avoid bespoke glue when native Hermes profiles, Kanban, checkpoints, dashboard, gateway, and skills can provide the primitive.

The first reliable workflow is software delivery through Discord:

```text
Discord user -> Atlas -> Hermes Kanban mission -> profile workers -> Atlas -> Discord final
```

Discord is the primary user interface. Dashboard is the inspection/control plane. CLI is an operator/admin fallback, normally through `docker run` or Compose/admin shell workflows.

## Primary design decisions

| Area | Decision |
|---|---|
| Runtime model | Dual-mode: host profiles plus single-container Docker profile mode. |
| Docker shape | One image; Compose services by function, not by agent: gateway, dashboard, dispatcher, admin/shell. |
| Migration style | Big-bang replacement of the old Docker-per-agent model, staged internally, with no dead code left behind. |
| Agent identity | Hermes profiles are the native agent identity unit. |
| Default isolation | Shared profile runtime is acceptable; sandbox-required tasks can use Docker as an escape hatch. |
| Workspace model | Kanban workspace-type driven; coding tasks use git worktrees by default. |
| Human interface | Discord is the CLI; Atlas is the user-facing bot in v1. |
| Agent bus | Kanban is the worker coordination/source-of-truth layer. Discord is not the worker bus. |
| Boards | Coding uses board-per-project/repo; general work uses default/general board. |
| Tenants | Coding boards use tenant = mission/conversation; general board uses domain or mission. |
| Learning | Repo-visible learning is high importance; Curator governs durable team knowledge. |
| Skills | Repo-visible canonical base + role skills synced into profiles. |
| Checkpoints | Enabled for editing profiles: Forge, Sentinel, Scribe, Curator; Atlas optional when editing. |
| Dashboard | Light Team Nexus dashboard branding/config in v1; defer custom mission dashboard. |

## Active v1 profiles

| Profile | One job |
|---|---|
| Atlas | Mission Orchestrator: clarifies intent, creates Kanban-backed mission/task graph, routes to profiles, tracks evidence, synthesizes final answer. |
| Forge | Implementation Engineer: changes code in task worktrees, runs verification, commits, reports changed files/tests/branch/PR evidence. |
| Sentinel | Quality Gate Reviewer: reviews implementation against acceptance criteria, tests, security, maintainability, and records approve/reject/block verdicts. |
| Scribe | Documentation Specialist: creates or updates repo-visible plans, ADRs, README/runbook/changelog/PR narrative. |
| Curator | Learning and Profile Steward: maintains profile specs, shared/team skills, role conventions, and promotes reusable learning into repo-visible artifacts or appropriate Hermes memory/skills. |

Planned but inactive by default: Scout, Ops, Relay/Echo.

## Discord gateway model

V1 uses Atlas-only Discord gateway.

Profile specs should include optional worker gateway settings, but worker gateways are disabled by default. A future C-lite mode may allow worker bot identities as notification-only evidence reporters in mission threads, never as a worker-to-worker bus.

Rules:
- Atlas is the normal human-facing voice.
- Worker profiles communicate through Kanban only.
- Direct mentions like “ask Forge” are routing preferences handled by Atlas.
- Clear low-risk requests may be routed immediately.
- Ambiguous/high-risk requests trigger clarification or planning/triage.
- Atlas claims about worker activity must cite board/task/run/branch/PR/test evidence.

## Discord mission UX

| Case | Behavior |
|---|---|
| Simple Q&A | Atlas answers directly; no Kanban mission. |
| Actionable tracked request in normal channel | Atlas creates a mission thread and Kanban mission/task(s). |
| Request already in suitable thread | Atlas reuses that thread as mission container. |
| Status in mission thread | Returns status for that mission. |
| Status in general channel | Returns concise active mission summary. |
| Worker bot enabled later | May only post evidence-backed notification messages in mission threads. |

Core command style:
- Natural language by default.
- Slash commands for precise controls: `/mission create`, `/mission status`, `/mission cancel`, `/mission retry`, `/board`, `/help`.
- Phrase aliases: “track this”, “just answer”, “status”, “make this a mission”.

Default Discord notifications:
- Mission accepted/created with board/task IDs.
- Human clarification needed.
- Worker blocked.
- Sentinel rejected or requested changes.
- PR opened.
- Dispatcher/runtime failure.
- Task stuck/timeout.
- Atlas final ready.

Do not notify by default for worker heartbeats, task starts, routine completions, internal comments, or non-blocking progress.

## Mission and Kanban model

Mission creation is adaptive.

| Request type | Shape |
|---|---|
| Simple answer | No mission. |
| Small single-agent action | One Kanban task may be enough. |
| Multi-agent work | Parent Atlas mission task plus child specialist tasks and dependency links. |
| Large/ambiguous/high-risk | Planning/triage task first; implementation waits for clarification. |
| Coding work | Project board, tenant = mission/conversation, worktree tasks, branch/PR/test/review evidence. |

Create a Kanban mission/task when the request:
- requires file/repo changes,
- invokes another profile,
- is multi-step or long-running,
- needs progress tracking,
- could block,
- creates external side effects,
- should be auditable later,
- is explicitly requested as a mission.

Do not create a mission for simple Q&A, quick explanations, small planning conversation before commitment, or status checks that only read existing board state.

### Board and tenant policy

| Board type | Board | Tenant |
|---|---|---|
| Coding | Project/repo board, e.g. `team-nexus` | Mission/conversation identifier |
| General | `default` or `general` | Domain such as `team-nexus`, `personal`, `ops`, `research`, or mission for larger efforts |

Every mission/task should carry metadata:
- mission_id
- conversation_id / Discord thread ID
- project/repo
- runtime target: host | docker | either
- risk level
- notification level
- phase
- assignee_role
- branch / PR URL / tests / verdict when relevant

Native Hermes Kanban statuses remain authoritative: triage, todo, ready, running, blocked, done, archived. Do not create a parallel custom state machine in v1.

Structured comment types:
- proposed_followup
- review_verdict
- blocker
- pr_opened
- learning_candidate
- final_synthesis

## Coding workflow

Default: every coding task uses a git worktree and task branch.

Forge task done requires:
- implementation complete,
- relevant tests/checks run or inability justified,
- changes committed on task branch/worktree unless explicitly no-commit,
- completion summary with changed files, tests/checks, branch/commit, unresolved risks, PR URL if opened.

Sentinel review policy:
- All source code changes require Sentinel review before final.
- PR-bound work requires Sentinel review.
- Dependency/security/runtime/config changes require Sentinel review.
- Docs-only changes may skip Sentinel unless architecture/process/public-critical docs are affected.
- Atlas final states whether Sentinel reviewed or why review was skipped.

PR policy:
- For PR-bound missions, Forge opens a draft PR after implementation.
- PR body includes mission/task IDs, summary, tests, changed files, review status.
- Sentinel reviews PR/branch.
- After approval, Forge or Atlas marks PR ready depending on implementation convenience.
- Non-PR missions ask before push/PR unless delivery was requested.

## Knowledge and learning policy

Knowledge hierarchy:
1. ADRs/docs: durable architectural decisions and human-facing rationale.
2. Profile specs + AGENTS.md: active role/workflow instructions and constraints.
3. Repo-visible skills: reusable procedures/checklists.
4. Hermes memory: compact stable facts/preferences/environment notes only.
5. SOUL.md: identity/personality, not operational process.
6. Kanban: mission/task evidence, not long-term knowledge.

Repo-visible learning is high importance. Any durable Team Nexus behavior, convention, workflow, or reusable procedure should become repo-visible unless clearly personal/private/local.

Skill update policy:
- Workers do not directly modify canonical skills during normal work.
- Workers emit structured `learning_candidate` comments.
- Curator owns canonical repo-visible skill/doc updates.
- Significant changes to workflow, safety, permissions, profile architecture, role definitions, or Discord/Kanban evidence model require Sentinel or Atlas review and possibly human approval.

## SOUL.md, AGENTS.md, profile specs, and skills

SOUL.md should contain:
- agent identity,
- one-job mission,
- tone/voice,
- role boundaries,
- source-of-truth references.

SOUL.md should not contain long workflows, detailed Kanban schema, full safety policy, or exhaustive Git/PR instructions.

Operational behavior belongs in:
- profile specs,
- AGENTS.md,
- repo-visible skills,
- docs/ADRs.

Profile configs should be generated from repo specs/templates with safe ownership boundaries:
- managed files/sections are labeled,
- local `.env`, secrets, auth, sessions, profile memory, logs, and live Kanban DB are not overwritten,
- host and Docker render from the same specs with path substitution,
- generator supports dry-run/diff/backup before overwrite.

## Docker target

V1 target:
- one Team Nexus image,
- Compose services by function:
  - Atlas gateway / Discord bot,
  - dashboard,
  - gateway-embedded native Kanban dispatcher by default,
  - optional one-shot dispatcher nudge service,
  - optional admin/shell,
- shared mounted HERMES_HOME,
- shared mounted workspace/project root,
- generated profile set,
- workers spawned as Hermes profiles by dispatcher.

Future:
- optional sandbox worker containers for tasks with `sandbox_required: true`.

Secrets:
- Commit `.env.example` only.
- Bootstrap validates required variables but never commits secrets.
- Atlas Discord token is required in v1.
- Worker Discord token fields exist but are disabled by default.
- Do not broadly copy or clone secrets without explicit operator action.

## Dashboard v1

Must show or make easily inspectable:
- active boards and tasks,
- profile/assignee visibility,
- mission/task IDs,
- blocked/running/done state,
- structured comments/evidence,
- PR URL/verdict/test summary where relevant,
- basic gateway/dispatcher/dashboard health if easy.

Defer:
- fully custom mission analytics,
- bot transcript replay,
- complex dashboards per profile.

## Migration strategy

The refactor should be big-bang in direction, not a long-lived dual architecture.

Internal stages:
1. Add the new profile-driven docs/specs/runtime skeleton.
2. Switch defaults/docs/Make targets to the new profile-driven path.
3. Remove or archive old per-agent services/glue.
4. Verify Docker/dashboard/Discord/vertical slice.
5. Leave no dead code behind.

Non-breakage requirements:
- Docker image/Compose path remains runnable.
- Atlas Discord gateway path remains or has a planned replacement before removal.
- Dashboard inspection remains available.
- Existing shared skills/docs/assets are preserved or intentionally migrated.
- Multi-agent claims remain evidence-backed.
- No secrets/auth/profile memory are overwritten by bootstrap.

## First vertical slice

A small Team Nexus repo change should prove:
1. User asks Atlas in Discord.
2. Atlas creates project-board Kanban mission/task graph.
3. Forge implements in a worktree and commits.
4. Sentinel reviews and records verdict.
5. Scribe updates docs/PR narrative if needed.
6. Curator records or promotes at most one learning candidate if something reusable emerged.
7. Atlas sends final with task IDs, branch/PR, tests, verdict.

## Phased implementation plan

### Phase 0: Safety and inventory

- Capture current generated files and active Docker/Make targets.
- Identify obsolete per-agent-runtime pieces to remove after replacement.
- Verify no secrets are tracked.
- Add a migration note that ADR-0011 is superseded by the new profile-driven ADR.

### Phase 1: Repo-visible specs

- Add `profiles/team-nexus.profiles.yaml` as canonical v1 roster/runtime spec.
- Add compact SOUL/AGENTS templates or references for Atlas, Forge, Sentinel, Scribe, Curator.
- Add shared skill manifest structure for base and role skills.
- Add schema/validation notes under `shared/config/`.

### Phase 2: Bootstrap/generation design

- Implement dry-run profile renderer/validator.
- Render host profiles and Docker-mounted profiles from the same specs.
- Support backup/diff before overwrite.
- Never overwrite secrets, auth, memory, sessions, logs, or live Kanban DB.

### Phase 3: Docker runtime reshape

- Add profile-driven function-service Compose file: `docker-compose.profiles.yml`.
- Replace per-agent services with function services: gateway, dashboard, gateway-embedded dispatcher, one-shot dispatcher nudge, admin/shell.
- Keep one image.
- Mount one durable HERMES_HOME/profile set and workspace root.
- Make `docker run`/Compose admin path the operator CLI fallback.

### Phase 4: Discord/Kanban mission loop

- Configure Atlas gateway as the only v1 Discord bot.
- Add mission thread/status/notification conventions.
- Use project boards for coding and general board for non-coding.
- Ensure Atlas can create parent/child task graphs with metadata and structured comments.

### Phase 5: Worker profiles and quality gate

- Enable Forge/Sentinel/Scribe/Curator profiles.
- Enforce worktree coding tasks.
- Add Sentinel review dependencies.
- Add draft PR template/evidence policy.
- Add Curator learning_candidate workflow.

### Phase 6: Cleanup and verification

- Remove obsolete per-agent Compose services and custom glue replaced by native profile/Kanban flow.
- Validate generated configs/specs/skills.
- Build Docker image.
- Start gateway/dashboard/dispatcher.
- Run host bootstrap dry-run or smoke test.
- Run the first vertical slice.
- Confirm no dead code and no secrets committed.

## Done criteria

The refactor is not done until:
- profile spec/schema validation passes,
- skill manifest validation passes,
- generated config dry-run/diff works,
- Docker image builds,
- Docker services start for gateway/dashboard/dispatcher,
- host bootstrap works or dry-run is validated,
- Kanban board creation/routing smoke test passes,
- first vertical slice succeeds or has documented explicit gaps,
- no dead old per-agent paths remain,
- no secrets are committed,
- Atlas final evidence includes board/task/run/branch/PR/test/verdict as applicable.
