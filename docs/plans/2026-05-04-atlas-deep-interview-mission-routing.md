# Atlas Deep Interview + Mission Routing Implementation Plan

> Historical/superseded by ADR-0014 where it references deleted dispatcher/setup scripts or per-agent Compose runtime paths. Current mission routing should use the profile-driven Team Nexus runtime.

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Improve Atlas so ambiguous Discord missions start with a short clarification interview, then become a dependency-aware mission route that uses the full Team Nexus roster intentionally.

**Architecture:** Atlas remains the single human-facing orchestrator. Atlas first classifies incoming work by ambiguity and risk, asks only the questions needed to remove blocking ambiguity, then creates a mission route: objectives, assumptions, task graph, assignees, dependencies, artifact handoffs, review gates, and final synthesis. Kanban remains the source of truth; Discord gets compact mission reads, questions, assignments, and status updates.

**Tech Stack:** Hermes Agent Discord gateway, Atlas `SOUL.md` / `AGENTS.md`, shared Team Nexus protocol docs, Hermes Kanban CLI (`kanban create --parent`, `kanban link`), Docker Compose agent services, `/shared/project/artifacts` handoff directory.

---

## Design principles

1. Atlas should not over-ask. It asks questions only when ambiguity changes strategy, cost, scope, risk, or authority.
2. Atlas should not under-plan. Multi-agent work must become a visible task graph before execution.
3. The plan/route should use all relevant agents, not all agents blindly.
4. Dependencies belong in Kanban via `--parent` or `kanban link`, not only in prose.
5. Discord stays readable: interview questions, mission read, assignment table, compact status, final synthesis.
6. Long rationale, route manifests, and handoff details belong in `/shared/project/artifacts` and Kanban comments.

---

## Target behavior

### Intake classification

When Atlas receives a new mission, it classifies it as one of:

- `direct-answer`: can answer directly; no Kanban fan-out.
- `clarify-first`: goal is promising but missing essential facts.
- `route-ready`: enough information exists to create a mission route.
- `user-decision-required`: asks user to choose between meaningful tradeoffs.

### Deep interview behavior

Atlas conducts a bounded interview when the mission is ambiguous. It should:

- restate the goal in one sentence;
- list the top ambiguity/risk dimensions;
- ask 3-7 numbered questions maximum in one pass;
- mark each question as `required` or `optional`;
- propose defaults for low-stakes choices;
- stop interviewing once it has enough information to route work;
- save durable assumptions in the route, not memory.

### Mission route behavior

After clarification, Atlas produces a mission route with:

- `conversation_id`;
- mission objective;
- accepted assumptions;
- excluded scope;
- task graph;
- assignees;
- dependencies;
- expected outputs;
- artifact paths;
- review gates;
- final synthesis owner.

### Default role routing matrix

Use specialists intentionally:

- Vega: product scope, user value, prioritization, PRD, acceptance criteria.
- Scout: market/customer research, evidence gathering, competitor analysis.
- Forge: engineering approach, implementation plan, feasibility, technical risks.
- Lumen: UX, interaction design, information architecture, prototypes.
- Blitz: positioning, launch/GTM, messaging, funnel experiments.
- Ledger: pricing, cost, financial model, ops constraints.
- Sentinel: QA, code review, security, privacy, release readiness.
- Atlas: interview, route design, dependency graph, synthesis, decisions.

---

## Phase 1: Prompt-level Atlas improvement

### Task 1.1: Add Atlas intake classifier to AGENTS.md

**Objective:** Make Atlas classify missions before answering or delegating.

**Files:**
- Modify: `agents/atlas/home/AGENTS.md`

**Implementation:**
Add an `Atlas intake classifier` section that requires Atlas to choose `direct-answer`, `clarify-first`, `route-ready`, or `user-decision-required` for every meaningful new mission.

**Verification:**
Run:

```bash
git diff -- agents/atlas/home/AGENTS.md
```

Expected: Atlas instructions include the four-route classifier and state that direct simple answers do not need Kanban fan-out.

### Task 1.2: Add bounded deep interview instructions

**Objective:** Give Atlas an interview protocol similar in spirit to OMC deep-interview, adapted to Discord and Team Nexus.

**Files:**
- Modify: `agents/atlas/home/AGENTS.md`

**Implementation:**
Add a `Deep interview mode` section requiring Atlas to ask 3-7 numbered questions, separate required vs optional, propose defaults, and stop once route-ready.

**Verification:**
Run:

```bash
git diff -- agents/atlas/home/AGENTS.md
```

Expected: Atlas has a concrete question format and no instruction to conduct unlimited interviews.

### Task 1.3: Add mission route template

**Objective:** Make Atlas produce dependency-aware routes before creating Kanban tasks.

**Files:**
- Modify: `agents/atlas/home/AGENTS.md`

**Implementation:**
Add a `Mission route template` with fields for `conversation_id`, objective, assumptions, exclusions, task graph, assignees, dependencies, expected outputs, artifacts, review gates, final synthesis.

**Verification:**
Run:

```bash
git diff -- agents/atlas/home/AGENTS.md
```

Expected: Atlas default output shape includes interview/route behavior for multi-agent missions.

---

## Phase 2: Shared protocol documentation

### Task 2.1: Document deep interview in collaboration protocol

**Objective:** Ensure all specialists understand that Atlas may interview before routing.

**Files:**
- Modify: `shared/project/team-collaboration-protocol.md`

**Implementation:**
Add a collaboration mode named `Deep interview / clarification` before mission graph. State that Atlas asks user questions when objective, constraints, success criteria, authority, budget, timeline, or risk tolerance are unclear.

**Verification:**
Run:

```bash
git diff -- shared/project/team-collaboration-protocol.md
```

Expected: Shared protocol documents the clarification phase and does not ask specialists to interview the user directly unless routed by Atlas.

### Task 2.2: Document mission route fields

**Objective:** Give a durable schema for route manifests and task graph comments.

**Files:**
- Modify: `shared/project/team-collaboration-protocol.md`

**Implementation:**
Add `Mission route fields` with the fields listed above and a compact Discord assignment table shape.

**Verification:**
Run:

```bash
git diff -- shared/project/team-collaboration-protocol.md
```

Expected: Protocol names the fields Atlas should include before task creation.

---

## Phase 3: Operator docs and examples

### Task 3.1: Add Atlas interview/routing runbook section

**Objective:** Explain how operators should expect Atlas to behave in Discord.

**Files:**
- Modify: `docs/discord-kanban-operations.md`

**Implementation:**
Add a section `Atlas deep interview and mission routes` covering:

- when Atlas should ask questions;
- when Atlas should proceed with assumptions;
- how Atlas posts a route;
- how tasks are linked with `kanban create --parent` / `kanban link`;
- how final synthesis works.

**Verification:**
Run:

```bash
git diff -- docs/discord-kanban-operations.md
```

Expected: Runbook gives operators a clear mental model without exposing secrets.

### Task 3.2: Add example route manifest

**Objective:** Provide a concrete pattern Atlas can mimic.

**Files:**
- Create: `shared/project/atlas-mission-route-template.md`

**Implementation:**
Create a markdown template with frontmatter-like fields and an example task graph table:

```markdown
# Atlas Mission Route: <mission>

conversation_id: mission_<slug>_<yyyymmdd>
status: proposed|active|complete
owner: atlas

## Mission read
## Clarifications / accepted assumptions
## Excluded scope
## Task graph
| id | assignee | objective | depends_on | expected_output | artifact |
## Review gates
## Final synthesis plan
```

**Verification:**
Run:

```bash
git diff -- shared/project/atlas-mission-route-template.md
```

Expected: Template exists under shared project context and can be read by all agents.

---

## Phase 4: Kanban helper ergonomics

### Task 4.1: Add Makefile helper for linked Kanban tasks

**Objective:** Make dependency linking easier from the host.

**Files:**
- Modify: `Makefile`

**Implementation:**
Add:

```make
kanban-link: ## Link parent->child dependency: make kanban-link PARENT=K... CHILD=K...
	@if [ -z "$(PARENT)" ]; then echo "PARENT is required" >&2; exit 2; fi
	@if [ -z "$(CHILD)" ]; then echo "CHILD is required" >&2; exit 2; fi
	$(COMPOSE) run --rm atlas kanban link "$(PARENT)" "$(CHILD)"
```

Also add `kanban-link` to `.PHONY`.

**Verification:**
Run:

```bash
make help | grep kanban-link
make compose-config
```

Expected: helper appears in help and Compose config still validates.

### Task 4.2: Add route smoke-test instructions

**Objective:** Make it easy to test Atlas task dependencies manually.

**Files:**
- Modify: `docs/discord-kanban-operations.md`

**Implementation:**
Add a non-mutating/dry-run-friendly route smoke-test recipe, then an optional live test recipe using two tiny tasks and `kanban link`.

**Verification:**
Run:

```bash
git diff -- docs/discord-kanban-operations.md
```

Expected: Docs include clear live-test commands and remind operators that automatic dispatch requires the `dispatcher` profile.

---

## Phase 5: Verification

### Task 5.1: Static verification

**Objective:** Verify documentation and Compose still parse cleanly.

**Files:**
- No new files.

**Commands:**

```bash
docker compose --profile dispatcher --profile dashboard config >/tmp/team-nexus-compose-config.out
git diff --check
python3 tests/test_kanban_compose_dispatcher.py
python3 -m py_compile scripts/kanban-compose-dispatcher.py scripts/discord-post-status.py
bash -n scripts/kanban-dispatch-compose.sh scripts/setup-agent.sh docker/team-nexus-entrypoint.sh
```

Expected: all commands pass.

### Task 5.2: Atlas prompt smoke test

**Objective:** Confirm Atlas now behaves differently on ambiguous vs route-ready missions.

**Commands:**

```bash
docker compose run --rm atlas chat -q "I want to build a thing that helps founders. What should the team do?"
docker compose run --rm atlas chat -q "Plan a launch for a $19/mo developer tool for solo founders; use the team and show dependencies, but do not create tasks yet."
```

Expected:

- First prompt triggers a bounded interview.
- Second prompt returns a mission route with relevant agents and dependencies.
- Atlas should not create Kanban tasks unless explicitly told to execute the route.

---

## Acceptance criteria

- Atlas conducts a bounded clarification interview for ambiguous missions.
- Atlas produces a mission route before multi-agent execution.
- The route uses relevant specialists and explicitly states why each is involved.
- Dependencies are represented in Kanban when tasks are created.
- Discord remains compact and user-facing.
- Shared protocol and operator docs match Atlas behavior.
