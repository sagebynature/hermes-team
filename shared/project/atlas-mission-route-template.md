# Atlas Mission Route Template

conversation_id: mission_<slug>_<yyyymmdd>
status: proposed|active|complete
owner: atlas
source: discord|cli|kanban

## Mission read

One-paragraph restatement of the user goal, desired outcome, and why it matters.

## Intake classification

- classification: direct-answer|clarify-first|route-ready|user-decision-required
- rationale: <why Atlas chose this path>

## Clarifications / accepted assumptions

### User-confirmed facts

- <fact>

### Assumptions Atlas is making

- <assumption and default>

### Open questions

- required: <question that blocks routing or execution>
- optional: <question that can improve quality but should not block>

## Excluded scope

- <what this route will not cover>

## Task graph

| id | assignee | objective | depends_on | expected_output | artifact | review_gate |
| --- | --- | --- | --- | --- | --- | --- |
| route-1 | vega | Define product scope and acceptance criteria | none | Scope memo | /shared/project/artifacts/<mission>/vega-scope.md | atlas |
| route-2 | scout | Gather supporting market/customer evidence | route-1 | Evidence brief | /shared/project/artifacts/<mission>/scout-evidence.md | atlas |
| route-3 | forge | Propose implementation approach and risks | route-1 | Technical plan | /shared/project/artifacts/<mission>/forge-plan.md | sentinel |
| route-4 | sentinel | Review quality/security/release risks | route-3 | Review memo | /shared/project/artifacts/<mission>/sentinel-review.md | atlas |
| route-final | atlas | Synthesize final recommendation | route-1, route-2, route-3, route-4 | Final answer | /shared/project/artifacts/<mission>/atlas-synthesis.md | user |

## Kanban creation notes

When executing this route, create parent tasks first, then child tasks with `--parent`, or link them afterwards:

```bash
kanban create "<title>" --assignee vega --body "<bounded task body>" --json
kanban create "<child title>" --assignee forge --parent <parent-task-id> --body "<bounded task body>" --json
kanban link <parent-task-id> <child-task-id>
```

Task bodies should include:

- conversation_id
- from: atlas
- to: <assignee>
- objective
- constraints
- expected_output
- artifact path under `/shared/project/artifacts/<mission>/`
- ttl or max runtime
- next_action

## Specialist rationale

- Vega: <why product strategy is needed>
- Scout: <why research/evidence is needed>
- Forge: <why engineering planning is needed>
- Lumen: <why UX/design is needed>
- Blitz: <why GTM/growth is needed>
- Ledger: <why finance/ops is needed>
- Sentinel: <why QA/security/review is needed>

Remove irrelevant agents from the active route rather than assigning busywork.

## Review gates

- <gate>: <reviewer> checks <risk/scope> before <dependent task/final synthesis>

## Discord update shape

```text
Mission route proposed: <mission>
conversation_id: <id>
Tasks:
- <assignee>: <objective> (depends: <none/task>)
- <assignee>: <objective> (depends: <task>)
Review gate: <reviewer/risk>
Next: <ask user to approve route OR say Atlas will create Kanban tasks>
```

## Final synthesis plan

Atlas will read completed Kanban tasks, `[handoff]` comments, and artifacts, then produce:

- final recommendation
- decisions needed from user
- risks and mitigations
- next concrete action
