# Registry-Driven Team Nexus Operations Implementation Plan

> Historical/superseded by ADR-0014: current operations use `profiles/team-nexus.profiles.yaml`, `profiles/<profile>/`, `shared/profile/AGENTS.base.md`, and `docker-compose.profiles.yml`. Commands and files in this plan that reference registry-generated per-agent Compose, nginx fan-out, or lifecycle Make targets are retained only as implementation history.

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make Team Nexus easier to run, safer to modify, and resistant to roster/config drift by making `shared/team-agents.yaml` the source of truth for agent services, dashboards, documentation, validation, and agent lifecycle commands.

**Architecture:** Introduce a small registry tool that reads `shared/team-agents.yaml`, validates the team roster, and generates repetitive fleet artifacts. Keep the dedicated-runtime architecture from ADR-0011, but stop hand-maintaining duplicate agent lists in Compose, nginx, Makefile, docs, and per-agent config. Add operator runbooks for starting Team Nexus, installing common/shared plugins, and adding/disabling/archiving agents.

**Tech Stack:** Python 3 stdlib, Docker Compose, Make, nginx, Hermes Agent, existing Team Nexus directory layout.

---

## Desired end state

A future operator should be able to:

```bash
make validate
make generate
make check-generated
make up
make dashboards-up
make kanban-dispatcher-daemon
```

Add an agent with one command:

```bash
make agent-add SLUG=raven NAME="Raven" ROLE="Legal / Compliance"
```

Disable an agent without deleting durable state:

```bash
make agent-disable SLUG=raven
```

Archive an agent deliberately:

```bash
make agent-archive SLUG=raven
```

Add common dashboard plugins by placing them under:

```text
shared/plugins/<plugin-name>/
```

and verify every agent/dashboard sees them with:

```bash
make validate-plugins
```

---

## Non-goals

- Do not collapse Team Nexus into one Hermes runtime with profiles.
- Do not remove the Compose-aware Kanban dispatcher.
- Do not delete existing agent state as part of simplification.
- Do not introduce a large framework or dependency-heavy generator.
- Do not require external package installation just to validate/generate the fleet.

---

## Source-of-truth model

Expand `shared/team-agents.yaml` to include all metadata needed by generated artifacts.

Target shape:

```yaml
agents:
  atlas:
    enabled: true
    service: atlas
    display_name: Atlas
    role: Orchestrator / Chief of Staff
    gateway_port: 8642
    dashboard_port: 9119
    dashboard_visible: true
    discord_visible: true
    dispatch_enabled: false
    default_route: true

  vega:
    enabled: true
    service: vega
    display_name: Vega
    role: Product Strategist
    gateway_port: 8643
    dashboard_port: 9120
    dashboard_visible: true
    discord_visible: true
    dispatch_enabled: true
```

Rules:

- `atlas` must exist and be enabled.
- Slugs must match `^[a-z][a-z0-9-]*$`.
- Services must be unique.
- `gateway_port` values must be unique for enabled agents.
- `dashboard_port` values must be unique for enabled/dashboard-visible agents.
- Disabled agents keep their directories but are excluded from generated runtime artifacts.
- Archived agents move under `agents/.archived/<slug>-YYYYMMDD/` and are excluded from runtime validation.

---

## Task 1: Add the team registry utility skeleton

**Objective:** Create one Python entrypoint responsible for reading the roster, listing agents, and supporting future validation/generation commands.

**Files:**
- Create: `scripts/team_registry.py`
- Modify: `Makefile`

**Step 1: Create `scripts/team_registry.py` with subcommands**

Implement these subcommands first:

```text
list-slugs
list-enabled-slugs
list-dashboard-slugs
validate-registry
next-ports
```

Implementation constraints:

- Use Python stdlib only if possible.
- If YAML parsing without PyYAML becomes too brittle, support only the current simple `shared/team-agents.yaml` structure and fail loudly on unexpected indentation.
- Keep parsing code in one place so the dispatcher can import it later.
- Return non-zero on validation failure.

**Step 2: Add Makefile wrappers**

Add:

```make
TEAM_REGISTRY := python3 scripts/team_registry.py

registry-list: ## List enabled Team Nexus agent slugs
	$(TEAM_REGISTRY) list-enabled-slugs

registry-validate: ## Validate shared/team-agents.yaml only
	$(TEAM_REGISTRY) validate-registry

registry-next-ports: ## Show next available gateway/dashboard ports
	$(TEAM_REGISTRY) next-ports
```

**Step 3: Verify**

Run:

```bash
python3 scripts/team_registry.py list-slugs
python3 scripts/team_registry.py validate-registry
make registry-list
make registry-next-ports
```

Expected:

- Existing agents are listed in registry order.
- Duplicate ports or duplicate services fail validation if intentionally introduced and then reverted.

---

## Task 2: Expand and validate `shared/team-agents.yaml`

**Objective:** Add fields required for generation and lifecycle management without changing runtime behavior yet.

**Files:**
- Modify: `shared/team-agents.yaml`
- Modify: `scripts/team_registry.py`

**Step 1: Add metadata fields for every existing agent**

For each current agent, add:

```yaml
enabled: true
dashboard_port: <existing dashboard port>
dashboard_visible: true
dispatch_enabled: true_or_false
```

Use current values:

```text
atlas     gateway 8642 dashboard 9119 dispatch_enabled false
vega      gateway 8643 dashboard 9120 dispatch_enabled true
scout     gateway 8644 dashboard 9121 dispatch_enabled true
forge     gateway 8645 dashboard 9122 dispatch_enabled true
lumen     gateway 8646 dashboard 9123 dispatch_enabled true
blitz     gateway 8647 dashboard 9124 dispatch_enabled true
ledger    gateway 8648 dashboard 9125 dispatch_enabled true
sentinel  gateway 8649 dashboard 9126 dispatch_enabled true
```

**Step 2: Update validation**

Validation should check:

- required fields exist
- port fields are integers
- booleans are booleans or parseable `true`/`false`
- `atlas.default_route` is true, or exactly one enabled agent has `default_route: true`
- no disabled agent is returned by `list-enabled-slugs`

**Step 3: Verify**

Run:

```bash
make registry-validate
python3 scripts/team_registry.py list-dashboard-slugs
```

Expected dashboard slugs:

```text
atlas vega scout forge lumen blitz ledger sentinel
```

---

## Task 3: Generate Make roster include

**Objective:** Stop hardcoding the agent roster in `Makefile`.

**Files:**
- Modify: `scripts/team_registry.py`
- Create generated: `generated/team-agents.mk`
- Modify: `Makefile`
- Modify: `.gitignore` if generated files policy requires ignoring or explicitly tracking generated output

**Step 1: Add generator command**

Add subcommand:

```bash
python3 scripts/team_registry.py generate-make > generated/team-agents.mk
```

Output:

```make
# GENERATED FILE. DO NOT EDIT.
# Source: shared/team-agents.yaml
# Regenerate: make generate
TEAM_AGENTS := atlas vega scout forge lumen blitz ledger sentinel
DASHBOARD_AGENTS := atlas vega scout forge lumen blitz ledger sentinel
```

**Step 2: Update Makefile**

Replace hardcoded:

```make
TEAM_AGENTS := atlas vega scout forge lumen blitz ledger sentinel
```

with:

```make
-include generated/team-agents.mk
TEAM_AGENTS ?= atlas vega scout forge lumen blitz ledger sentinel
TARGET_AGENTS ?= $(TEAM_AGENTS)
```

The fallback keeps Make usable before generation.

**Step 3: Add generate target placeholder**

Add:

```make
generate: ## Generate registry-derived Team Nexus files
	@mkdir -p generated
	$(TEAM_REGISTRY) generate-make > generated/team-agents.mk
```

**Step 4: Verify**

Run:

```bash
make generate
make help
make registry-list
```

Expected:

- `generated/team-agents.mk` exists.
- `make help` still prints all current agents.

---

## Task 4: Generate dashboard nginx config

**Objective:** Replace the hand-maintained repeated nginx dashboard proxy blocks with a generated file.

**Files:**
- Create: `templates/dashboards.conf.tmpl`
- Modify: `scripts/team_registry.py`
- Replace generated: `nginx/dashboards.conf`
- Modify: `Makefile`

**Step 1: Create template**

Create `templates/dashboards.conf.tmpl` with placeholders for repeated per-agent blocks. Keep the current behavior exactly:

- `/` redirects to default route agent, currently `/atlas/`
- `/<agent>` redirects to `/<agent>/sessions`
- `/<agent>/` redirects to `/<agent>/sessions`
- `/<agent>/` proxies to `http://<agent>-dashboard:9119/`
- Existing `sub_filter` rules are preserved for each agent prefix

**Step 2: Add generator command**

Add:

```bash
python3 scripts/team_registry.py generate-nginx > nginx/dashboards.conf
```

The generated file must start with:

```nginx
# GENERATED FILE. DO NOT EDIT.
# Source: shared/team-agents.yaml
# Template: templates/dashboards.conf.tmpl
# Regenerate: make generate
```

**Step 3: Update `make generate`**

Add:

```make
	$(TEAM_REGISTRY) generate-nginx > nginx/dashboards.conf
```

**Step 4: Verify generated nginx matches current routing**

Run:

```bash
make generate
docker compose --profile dashboard config >/tmp/team-nexus-compose.yaml
```

Then, if Docker is available:

```bash
docker compose --profile dashboard run --rm dashboard-nginx nginx -t
```

Expected:

- Compose config succeeds.
- Nginx config test succeeds.
- Generated config includes every dashboard-visible agent and no stale unknown agent.

---

## Task 5: Add full drift validation

**Objective:** Add one command that catches stale hardcoding, missing directories, bad config, and unsafe runtime drift.

**Files:**
- Modify: `scripts/team_registry.py`
- Modify: `Makefile`

**Step 1: Add validation subcommands**

Add:

```text
validate-filesystem
validate-configs
validate-compose
validate-nginx
validate-kanban-assignees
validate-plugins
validate-all
```

**Step 2: Filesystem validation**

For each enabled agent, assert these exist:

```text
agents/<slug>/home/config.yaml
agents/<slug>/home/SOUL.md
agents/<slug>/home/AGENTS.md
agents/<slug>/workspace/
agents/<slug>/workspace/inbox/
agents/<slug>/workspace/outbox/
agents/<slug>/workspace/artifacts/
agents/<slug>/workspace/notes/
```

Warn, but do not fail, for missing optional:

```text
agents/<slug>/workspace/.mise.toml
```

Fail if `agents/<slug>/` exists for a slug not in registry unless it is under:

```text
agents/.archived/
```

**Step 3: Config validation**

For every enabled agent config, check:

```yaml
terminal.cwd: /workspace
kanban.dispatch_in_gateway: false
security.redact_secrets: true
startup_agent.slug: <slug>
startup_agent.name: <display_name>
startup_agent.role: <role>
dashboard.agent_name: ${AGENT_NAME}
dashboard.agent_role: ${AGENT_ROLE}
```

Also assert `toolsets` includes:

```yaml
- hermes-cli
- kanban
```

**Step 4: Compose validation**

Run:

```bash
docker compose --profile dashboard --profile dispatcher config
```

Then parse or text-check the rendered config enough to assert:

- every enabled agent has a gateway service
- every dashboard-visible agent has a dashboard service
- no disabled/unknown agent service appears
- published ports bind to `127.0.0.1`
- the dispatcher service exists

**Step 5: Nginx validation**

Check `nginx/dashboards.conf` contains exactly one dashboard block per dashboard-visible agent and no unknown agent prefixes.

**Step 6: Kanban assignee validation**

If `shared/kanban/kanban.db` exists, query tasks and report any assignee not in enabled registry slugs.

Do not mutate Kanban in validation.

**Step 7: Plugin validation**

Validate shared plugin layout:

```text
shared/plugins/<plugin>/dashboard/manifest.json
```

For each manifest:

- valid JSON
- has expected top-level identity fields if Hermes requires them
- no plugin directory is empty

**Step 8: Add Make target**

```make
validate: ## Validate registry, generated files, configs, compose, nginx, plugins, and kanban assignees
	$(TEAM_REGISTRY) validate-all
```

**Step 9: Verify**

Run:

```bash
make validate
```

Expected:

- A clean repo passes.
- Introducing a duplicate port fails.
- Adding a fake `agents/ghost/` dir fails until archived or registered.
- Reverting test changes passes again.

---

## Task 6: Add generated-file drift check

**Objective:** Make it obvious when generated files are stale after editing `shared/team-agents.yaml`.

**Files:**
- Modify: `Makefile`
- Modify: `scripts/team_registry.py` if needed

**Step 1: Add `check-generated` target**

```make
check-generated: ## Regenerate files and fail if generated outputs are stale
	$(MAKE) generate
	git diff --exit-code -- generated/team-agents.mk nginx/dashboards.conf
```

If future Compose fragments are generated, add them to the diff list.

**Step 2: Verify**

Run:

```bash
make check-generated
```

Expected:

- Clean when generated files are up to date.
- Fails after manual edit to generated nginx.

---

## Task 7: Add agent lifecycle commands

**Objective:** Add safe add/disable/archive workflows so operators do not manually copy directories and hardcoded blocks.

**Files:**
- Modify: `scripts/team_registry.py`
- Modify: `Makefile`
- Create: `templates/agent-config.yaml.tmpl`
- Create: `templates/agent-SOUL.md.tmpl`
- Create: `templates/agent-AGENTS.md.tmpl`

**Step 1: Add templates**

Config template should include the known Team Nexus baseline:

- model provider/default/context length
- `toolsets: [hermes-cli, kanban]`
- `terminal.cwd: /workspace`
- `memory` enabled
- auxiliary defaults
- `approvals.mode: smart`
- `security.redact_secrets: true`
- `kanban.dispatch_in_gateway: false`
- dashboard identity from env vars
- startup_agent metadata from registry
- voice defaults if team standard remains Groq STT + Edge TTS

SOUL template should be minimal and clearly marked for role customization.

AGENTS template should include shared Startup Team Protocol and point to generated roster:

```text
Use only registered Team Nexus assignees from /shared/project/generated/team-roster.md.
```

**Step 2: Add `agent-add` command**

CLI behavior:

```bash
python3 scripts/team_registry.py agent-add --slug raven --name Raven --role "Legal / Compliance"
```

It should:

- validate slug not already active
- auto-assign next gateway/dashboard ports if not provided
- update `shared/team-agents.yaml`
- create `agents/raven/home/config.yaml`
- create `agents/raven/home/SOUL.md`
- create `agents/raven/home/AGENTS.md`
- create workspace dirs: `inbox`, `outbox`, `artifacts`, `notes`
- create optional `.mise.toml` placeholder
- run generation or tell operator to run `make generate`

**Step 3: Add Make wrapper**

```make
agent-add: ## Add an agent: make agent-add SLUG=raven NAME=Raven ROLE='Legal / Compliance'
	@if [ -z "$(SLUG)" ]; then echo "SLUG is required" >&2; exit 2; fi
	@if [ -z "$(NAME)" ]; then echo "NAME is required" >&2; exit 2; fi
	@if [ -z "$(ROLE)" ]; then echo "ROLE is required" >&2; exit 2; fi
	$(TEAM_REGISTRY) agent-add --slug "$(SLUG)" --name "$(NAME)" --role "$(ROLE)"
	$(MAKE) generate
	$(MAKE) validate
```

**Step 4: Add disable command**

```bash
python3 scripts/team_registry.py agent-disable --slug raven
```

It should:

- set `enabled: false`
- set `dashboard_visible: false`
- set `discord_visible: false`
- set `dispatch_enabled: false`
- keep files in place
- warn about open Kanban tasks assigned to the disabled agent

**Step 5: Add archive command**

```bash
python3 scripts/team_registry.py agent-archive --slug raven
```

It should:

- refuse unless agent is disabled first, unless `--force` is passed
- move `agents/raven` to `agents/.archived/raven-YYYYMMDD`
- remove or mark the registry entry as archived
- warn if auth/secrets might be inside the archived home

**Step 6: Verify lifecycle in a temporary test slug**

Run:

```bash
make agent-add SLUG=raven NAME=Raven ROLE='Legal / Compliance'
make validate
make agent-disable SLUG=raven
make validate
make agent-archive SLUG=raven
make validate
```

Expected:

- Add creates dirs and config.
- Disable removes runtime generation without deleting state.
- Archive moves files under `agents/.archived/`.
- No stale nginx/compose/make references remain.

After verification, either keep Raven as a real new agent if desired or remove the test registry/archive changes before commit.

---

## Task 8: Generate shared team roster documentation

**Objective:** Stop hardcoding allowed assignees and team roster lists in prose instructions.

**Files:**
- Modify: `scripts/team_registry.py`
- Create generated: `shared/project/generated/team-roster.md`
- Modify: `agents/atlas/home/AGENTS.md`
- Modify: specialist `agents/*/home/AGENTS.md` if needed

**Step 1: Add generator command**

```bash
python3 scripts/team_registry.py generate-roster > shared/project/generated/team-roster.md
```

Output should include:

```markdown
# Generated Team Nexus roster

Allowed Kanban assignees:

- atlas: Atlas — Orchestrator / Chief of Staff
- vega: Vega — Product Strategist
...
```

**Step 2: Update `make generate`**

Add roster generation.

**Step 3: Replace hardcoded allowed-assignee list in Atlas instructions**

Change Atlas AGENTS.md from hardcoded slugs to:

```text
Use only registered Team Nexus assignees listed in /shared/project/generated/team-roster.md. Do not invent roles as Kanban assignees.
```

**Step 4: Verify**

Run:

```bash
make generate
make validate
```

Expected:

- Roster file includes all enabled agents.
- Atlas instructions no longer need manual edits when adding/removing agents.

---

## Task 9: Generate Compose agent/dashboard fragments

**Objective:** Remove most per-agent service duplication from the hand-authored Compose file.

**Files:**
- Create: `docker-compose.base.yml` or retain current `docker-compose.yml` as base
- Create generated: `docker-compose.agents.generated.yml`
- Create generated: `docker-compose.dashboards.generated.yml`
- Modify: `scripts/team_registry.py`
- Modify: `Makefile`
- Modify docs that invoke Docker Compose if file names change

**Step 1: Choose Compose file strategy**

Preferred strategy:

- Keep `docker-compose.yml` for base shared services: image build, dispatcher, dashboard-nginx, shared anchors if useful.
- Generate `docker-compose.agents.generated.yml` for gateway services.
- Generate `docker-compose.dashboards.generated.yml` for dashboard services.

Compose invocation becomes:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.agents.generated.yml \
  -f docker-compose.dashboards.generated.yml \
  --profile dashboard up -d
```

To keep commands simple, define:

```make
COMPOSE_FILES := -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml
COMPOSE ?= docker compose $(COMPOSE_FILES)
```

**Step 2: Generate agent gateway services**

For every enabled agent, generate a service with:

- image `team-nexus-agent:latest`
- build stanza only for `atlas`, or keep build in base file
- container name `hermes-<slug>`
- restart `unless-stopped`
- `HERMES_HOME=/opt/data`
- `HERMES_KANBAN_HOME=/shared/kanban`
- `AGENT_NAME`
- `AGENT_ROLE`
- env_file `./.env`
- agent home/workspace mounts
- shared project/artifacts/kanban/skills/mcp/plugins/dashboard-themes mounts
- localhost gateway port
- command `gateway run`

**Step 3: Generate dashboard services**

For every enabled dashboard-visible agent, generate:

- service `<slug>-dashboard`
- container name `hermes-<slug>-dashboard`
- profile `dashboard`
- same home/workspace/shared mounts
- localhost dashboard port from registry
- command `dashboard --host 0.0.0.0 --port 9119 --insecure --no-open`

**Step 4: Update Makefile commands**

Ensure these still work:

```bash
make build
make up
make down
make restart
make ps
make logs AGENT=atlas
make doctor AGENT=atlas
make doctor-all
make compose-config
```

**Step 5: Verify**

Run:

```bash
make generate
make compose-config
make validate
```

Expected:

- Rendered Compose config contains all active gateway services.
- Rendered Compose config contains all dashboard-visible dashboard services.
- No stale services remain for disabled agents.

---

## Task 10: Add common plugin operations documentation and checks

**Objective:** Give operators a clear path to add shared plugins once and make them available to every agent.

**Files:**
- Create: `docs/team-nexus-operations.md` or update existing `docs/discord-kanban-operations.md`
- Modify: `README.md`
- Modify: `scripts/team_registry.py`
- Modify: `Makefile`

**Step 1: Document shared plugin layout**

Add a section:

```text
shared/plugins/<plugin-name>/
```

Explain:

- This path is mounted read-only into each agent at `/opt/data/plugins`.
- Plugins placed here are common/team-wide plugins.
- Agent-local plugins, if ever needed, belong in `agents/<agent>/home/plugins`, but the current Compose mount of shared plugins onto `/opt/data/plugins` may hide local plugin dirs. Prefer common plugins unless the Compose mount strategy is changed.
- Restart gateways/dashboards after plugin changes.

**Step 2: Document common plugin add flow**

Example:

```bash
mkdir -p shared/plugins/<plugin-name>
# copy plugin files into shared/plugins/<plugin-name>
make validate-plugins
make restart
make dashboards-up
```

If plugin includes dashboard assets:

```bash
make dashboards-restart
open http://127.0.0.1:${NGINX_PORT:-9130}/atlas/plugins
```

**Step 3: Add Make wrappers**

```make
validate-plugins: ## Validate shared plugin layout
	$(TEAM_REGISTRY) validate-plugins

dashboards-up: ## Start dashboard profile
	$(COMPOSE) --profile dashboard up -d

dashboards-restart: ## Restart dashboard profile services
	$(COMPOSE) --profile dashboard restart
```

**Step 4: Verify**

Run:

```bash
make validate-plugins
make dashboards-up
```

Expected:

- Existing shared plugins pass validation.
- Dashboard stack starts.

---

## Task 11: Write step-by-step Team Nexus runbook

**Objective:** Provide one operator-facing document that explains how to run Team Nexus, use dashboards, run Kanban, manage plugins, and manage agents.

**Files:**
- Create: `docs/team-nexus-operations.md`
- Modify: `README.md`
- Optionally keep `docs/discord-kanban-operations.md` as deep-dive and link to it

**Required sections:**

1. Prerequisites
   - Docker Desktop / Docker Compose v2
   - repo checkout
   - `.env` created from `.env.example`
   - provider keys required for model use

2. First-time setup

```bash
cd /Users/sage/team-nexus
cp .env.example .env
# edit .env
make generate
make validate
make workspace-init
make build
make compose-config
make kanban-init
```

3. Start the core gateway stack

```bash
make up
make ps
make logs AGENT=atlas
```

4. Start dashboards

```bash
make dashboards-up
open http://127.0.0.1:${NGINX_PORT:-9130}/atlas/
```

5. Start/stop automatic Kanban dispatch

```bash
make kanban-dispatcher-once DRY_RUN=1
make kanban-dispatcher-daemon
make kanban-dispatcher-logs
make kanban-dispatcher-stop
```

6. Create and inspect Kanban tasks

```bash
make kanban-create TITLE='Draft launch brief' ASSIGNEE=vega
make kanban-list
make kanban-stats
```

7. Add common plugins

```bash
mkdir -p shared/plugins/<plugin-name>
make validate-plugins
make restart
make dashboards-restart
```

8. Add an agent

```bash
make registry-next-ports
make agent-add SLUG=raven NAME=Raven ROLE='Legal / Compliance'
make generate
make validate
make compose-config
make up
```

9. Disable an agent safely

```bash
make agent-disable SLUG=raven
make generate
make validate
make restart
```

10. Archive an agent

```bash
make agent-archive SLUG=raven
make generate
make validate
```

11. Troubleshooting

Include:

- gateway logs
- dashboard logs
- dispatcher logs
- doctor all agents
- generated files stale
- port collision
- unknown Kanban assignee
- plugin not visible
- config changes require restart

**Step 2: Update README**

In `README.md`, add a short "Operator quick start" section linking to:

```text
docs/team-nexus-operations.md
docs/discord-kanban-operations.md
docs/adr/0011-dedicated-agent-runtimes-vs-profiles.md
```

**Step 3: Verify docs commands**

Run every non-destructive command in the runbook:

```bash
make generate
make validate
make compose-config
make registry-next-ports
make validate-plugins
make kanban-stats
```

Expected:

- Commands either pass or document the expected first-run prerequisite clearly.

---

## Task 12: Add CI/preflight script

**Objective:** Make the safe path one command for humans and future CI.

**Files:**
- Create: `scripts/preflight.sh`
- Modify: `Makefile`
- Optionally create: `.github/workflows/validate.yml` if CI is desired

**Step 1: Create preflight script**

`scripts/preflight.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

make generate
make validate
make compose-config
make check-generated
```

**Step 2: Add Make target**

```make
preflight: ## Run generation, validation, compose config, and drift check
	./scripts/preflight.sh
```

**Step 3: Optional GitHub Actions workflow**

If this repo uses GitHub CI, add:

```yaml
name: validate
on:
  pull_request:
  push:
    branches: [main]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - run: make preflight
```

**Step 4: Verify**

Run:

```bash
chmod +x scripts/preflight.sh
make preflight
```

Expected:

- The whole repo preflight passes from a clean checkout with `.env` present or documents `.env` as a required local-only file.

---

## Task 13: Record the generation/drift decision as an ADR

**Objective:** Preserve why Team Nexus moved to registry-driven generated artifacts.

**Files:**
- Create: `docs/adr/0012-registry-driven-agent-roster-and-generated-runtime-artifacts.md`
- Modify: `docs/adr/README.md`

**ADR contents:**

Decision:

- `shared/team-agents.yaml` is the source of truth for active agent roster metadata.
- Repetitive runtime artifacts should be generated or validated against the registry.
- Operators should use lifecycle commands for add/disable/archive instead of manual copy/paste.

Consequences:

- Less hardcoding.
- Safer add/remove agent workflow.
- Generated files must be kept current.
- Registry schema changes require generator updates.

**Step 2: Verify**

Run:

```bash
make validate
```

Expected:

- ADR index includes ADR-0012.

---

## Suggested implementation order

1. Registry utility skeleton.
2. Registry metadata expansion.
3. Make roster generation.
4. Nginx generation.
5. Validation suite.
6. Generated-file drift check.
7. Operator runbook.
8. Plugin docs/checks.
9. Agent lifecycle commands.
10. Generated roster docs.
11. Compose generated fragments.
12. Preflight/CI.
13. ADR-0012.

This order gives value early without forcing the largest Compose refactor first.

---

## Acceptance criteria

This project is complete when:

- `make validate` passes and catches registry/filesystem/config/Compose/nginx/plugin/Kanban-assignee drift.
- `make generate` creates all registry-derived artifacts.
- `make check-generated` fails if generated files are stale.
- `nginx/dashboards.conf` is generated from registry data.
- Makefile no longer has a manually maintained roster.
- Operators can add, disable, and archive agents through Make commands.
- Operators have a step-by-step runbook for:
  - first-time setup
  - starting/stopping Team Nexus
  - dashboards
  - Kanban dispatch
  - common plugin installation
  - adding agents
  - disabling/removing agents
  - troubleshooting
- ADR-0012 records the registry-driven generation decision.

---

## Verification command checklist

Run this before declaring the implementation done:

```bash
cd /Users/sage/team-nexus
make generate
make validate
make check-generated
make compose-config
make registry-next-ports
make validate-plugins
make kanban-dispatcher-once DRY_RUN=1
```

If dashboards are available locally:

```bash
make dashboards-up
curl -fsS http://127.0.0.1:${NGINX_PORT:-9130}/healthz
curl -fsS http://127.0.0.1:${NGINX_PORT:-9130}/atlas/ >/tmp/atlas-dashboard.html
```

If testing agent lifecycle with a temporary agent:

```bash
make agent-add SLUG=raven NAME=Raven ROLE='Legal / Compliance'
make validate
make agent-disable SLUG=raven
make validate
make agent-archive SLUG=raven
make validate
```

Review the final diff carefully before committing, especially generated files and any moved agent directories.
