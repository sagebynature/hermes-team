# GitHub organization board intake pattern

Session-derived example: user asked for a dedicated Kanban board for all repos related to `https://github.com/NJ-Onnuri-Church`, named `NJ Onnuri`.

Commands used:

```bash
hermes kanban boards create nj-onnuri \
  --name "NJ Onnuri" \
  --description "Dedicated board for all repositories related to https://github.com/NJ-Onnuri-Church" \
  --icon "⛪" \
  --color "#2563eb" \
  --switch

hermes kanban boards list
hermes kanban boards show
```

Then seeded an intake task:

```bash
hermes kanban --board nj-onnuri create \
  "Inventory NJ Onnuri GitHub repositories and seed workstreams" \
  --assignee forge \
  --workspace scratch \
  --priority 80 \
  --idempotency-key nj-onnuri-org-inventory-v1 \
  --body "Mission: Inventory every public repository under https://github.com/NJ-Onnuri-Church and propose repo-specific Kanban workstreams on the `nj-onnuri` board. Acceptance criteria: enumerate visible repos with URL/language/description/updated date/purpose; classify active/stale/archived/duplicate/deployment-critical/docs-only/follow-up-needed; create child Kanban tasks for concrete follow-up; summarize repo map, task graph, assumptions, blockers. Guardrails: no code changes; do not require private repo access; prefer durable Kanban tasks."
```

Reusable lesson: for a repo family or GitHub org, create the board first, then a single `forge`/engineering intake task that inventories repos and fans out child cards. This keeps org discovery durable without prematurely creating repo-specific tasks before the repo list is known.
