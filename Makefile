SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

COMPOSE_FILES ?= -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml
COMPOSE ?= docker compose $(COMPOSE_FILES)
TEAM_NEXUS_UID ?= $(shell id -u)
TEAM_NEXUS_GID ?= $(shell id -g)
export TEAM_NEXUS_UID TEAM_NEXUS_GID SLUG NAME ROLE GATEWAY_PORT DASHBOARD_PORT FORCE
-include generated/team-agents.mk
TEAM_AGENTS ?= atlas vega scout forge lumen blitz ledger sentinel
DASHBOARD_AGENTS ?= $(TEAM_AGENTS)
TARGET_AGENTS ?= $(TEAM_AGENTS)
TEAM_REGISTRY := python3 scripts/team_registry.py

# When SERVER is set, optionally load a shared MCP registry definition.
# Example: make mcp-register-template AGENT=atlas SERVER=time
ifneq ($(strip $(SERVER)),)
-include shared/mcp/registry/$(SERVER).mk
endif

.PHONY: help build up down restart ps logs shell doctor doctor-all compose-config workspace-init \
	generate check-generated validate preflight profile-validate registry-list registry-validate registry-next-ports validate-plugins dashboards-up dashboards-restart \
	agent-add agent-disable agent-archive \
	kanban-init kanban-list kanban-stats kanban-watch kanban-create kanban-link kanban-dispatch \
	kanban-dispatcher-once kanban-dispatcher-daemon kanban-dispatcher-stop kanban-dispatcher-logs \
	kanban-notifier-once kanban-notifier-daemon kanban-notifier-stop kanban-notifier-logs kanban-notifier-deliver kanban-notifier-dry-run discord-status-dry-run \
	mcp-list mcp-list-all mcp-test mcp-remove mcp-add-command mcp-add-url \
	mcp-register-template mcp-register-template-all mcp-templates mcp-show-template \
	guard-agent guard-server guard-command guard-url

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "; printf "Usage:\n  make <target> [AGENT=atlas] [SERVER=name] ...\n\nTargets:\n"} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-30s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf "\nAgents:\n  $(TEAM_AGENTS)\n"
	@printf "\nMCP examples:\n"
	@printf "  make mcp-list AGENT=atlas\n"
	@printf "  make mcp-add-command AGENT=forge SERVER=filesystem COMMAND='npx -y @modelcontextprotocol/server-filesystem /workspace'\n"
	@printf "  make mcp-register-template AGENT=atlas SERVER=time\n"
	@printf "  make mcp-register-template-all SERVER=filesystem-workspace TARGET_AGENTS='atlas forge'\n"

build: ## Build the custom Hermes team image once; all agents share team-nexus-agent:latest
	$(COMPOSE) build atlas

up: ## Start all Hermes gateways and dashboard reverse proxy
	$(COMPOSE) --profile dashboard up -d
	$(COMPOSE) --profile kanban up -d

down: ## Stop all Hermes gateways
	$(COMPOSE) --profile dashboard down
	$(COMPOSE) --profile kanban down

restart: ## Restart all Hermes gateways
	$(COMPOSE) --profile dashboard restart
	$(COMPOSE) --profile kanban restart

ps: ## Show Compose service status
	$(COMPOSE) ps

logs: guard-agent ## Follow logs for one agent, e.g. make logs AGENT=atlas
	$(COMPOSE) logs -f $(AGENT)

shell: guard-agent ## Open bash in one agent container, e.g. make shell AGENT=forge
	$(COMPOSE) run --rm --entrypoint bash $(AGENT)

doctor: guard-agent ## Run hermes doctor inside one agent container
	$(COMPOSE) run --rm $(AGENT) doctor

doctor-all: ## Run hermes doctor for every team agent
	@for agent in $(TEAM_AGENTS); do \
		printf '\n==> %s doctor\n' "$$agent"; \
		$(COMPOSE) run --rm "$$agent" doctor; \
	done

compose-config: ## Validate docker-compose.yml
	$(COMPOSE) config >/tmp/team-nexus-compose.yaml
	@echo "compose config OK -> /tmp/team-nexus-compose.yaml"

generate: ## Generate registry-derived Team Nexus files
	@mkdir -p generated nginx shared/project/generated
	$(TEAM_REGISTRY) generate-make > generated/team-agents.mk
	$(TEAM_REGISTRY) generate-compose-agents > docker-compose.agents.generated.yml
	$(TEAM_REGISTRY) generate-compose-dashboards > docker-compose.dashboards.generated.yml
	$(TEAM_REGISTRY) generate-nginx > nginx/dashboards.conf
	$(TEAM_REGISTRY) generate-roster > shared/project/generated/team-roster.md

check-generated: ## Regenerate files in a temp dir and fail if generated outputs are stale
	@tmp="$$(mktemp -d)"; trap 'rm -rf "$$tmp"' EXIT; \
		$(TEAM_REGISTRY) generate-make > "$$tmp/team-agents.mk"; \
		$(TEAM_REGISTRY) generate-compose-agents > "$$tmp/docker-compose.agents.generated.yml"; \
		$(TEAM_REGISTRY) generate-compose-dashboards > "$$tmp/docker-compose.dashboards.generated.yml"; \
		$(TEAM_REGISTRY) generate-nginx > "$$tmp/dashboards.conf"; \
		$(TEAM_REGISTRY) generate-roster > "$$tmp/team-roster.md"; \
		cmp -s generated/team-agents.mk "$$tmp/team-agents.mk" || { diff -u generated/team-agents.mk "$$tmp/team-agents.mk"; exit 1; }; \
		cmp -s docker-compose.agents.generated.yml "$$tmp/docker-compose.agents.generated.yml" || { diff -u docker-compose.agents.generated.yml "$$tmp/docker-compose.agents.generated.yml"; exit 1; }; \
		cmp -s docker-compose.dashboards.generated.yml "$$tmp/docker-compose.dashboards.generated.yml" || { diff -u docker-compose.dashboards.generated.yml "$$tmp/docker-compose.dashboards.generated.yml"; exit 1; }; \
		cmp -s nginx/dashboards.conf "$$tmp/dashboards.conf" || { diff -u nginx/dashboards.conf "$$tmp/dashboards.conf"; exit 1; }; \
		cmp -s shared/project/generated/team-roster.md "$$tmp/team-roster.md" || { diff -u shared/project/generated/team-roster.md "$$tmp/team-roster.md"; exit 1; }; \
		echo "generated files OK"

validate: ## Validate registry, generated files, configs, compose, nginx, plugins, kanban assignees, and profile specs
	$(TEAM_REGISTRY) validate-all
	python3 scripts/validate-profile-spec.py

profile-validate: ## Validate profile-driven Team Nexus spec and manifests
	python3 scripts/validate-profile-spec.py

preflight: ## Run generation, validation, compose config, and drift check
	./scripts/preflight.sh

agent-add: ## Add an agent: make agent-add SLUG=raven NAME=Raven ROLE='Legal / Compliance'
	$(TEAM_REGISTRY) agent-add-env
	$(MAKE) generate
	$(MAKE) validate

agent-disable: ## Disable an agent without deleting state: make agent-disable SLUG=raven
	$(TEAM_REGISTRY) agent-disable-env
	$(MAKE) generate
	$(MAKE) validate

agent-archive: ## Archive a disabled agent: make agent-archive SLUG=raven [FORCE=1]
	$(TEAM_REGISTRY) agent-archive-env
	$(MAKE) generate
	$(MAKE) validate

registry-list: ## List enabled Team Nexus agent slugs
	$(TEAM_REGISTRY) list-enabled-slugs

registry-validate: ## Validate shared/team-agents.yaml only
	$(TEAM_REGISTRY) validate-registry

registry-next-ports: ## Show next available gateway/dashboard ports
	$(TEAM_REGISTRY) next-ports

validate-plugins: ## Validate shared plugin layout
	$(TEAM_REGISTRY) validate-plugins

dashboards-up: ## Start dashboard profile
	$(COMPOSE) --profile dashboard up -d

dashboards-restart: ## Restart dashboard profile services
	$(COMPOSE) --profile dashboard restart

workspace-init: ## Initialize shared workspace directories and artifact handoff placeholder
	@mkdir -p shared/project/artifacts shared/kanban
	@if [ ! -f shared/project/artifacts/.gitignore ]; then \
		printf '*\n!.gitignore\n' > shared/project/artifacts/.gitignore; \
	fi
	@chmod 2775 shared/project/artifacts shared/kanban 2>/dev/null || true
	@echo "workspace initialized: shared/project/artifacts and shared/kanban"

kanban-init: workspace-init ## Initialize the shared Team Nexus Kanban board
	$(COMPOSE) run --rm atlas kanban init

kanban-list: ## List shared Kanban tasks
	$(COMPOSE) run --rm atlas kanban list

kanban-stats: ## Show shared Kanban task counts
	$(COMPOSE) run --rm atlas kanban stats

kanban-watch: ## Watch shared Kanban board events
	$(COMPOSE) run --rm atlas kanban watch

kanban-create: ## Create a mission-scoped Kanban task: make kanban-create TITLE='...' ASSIGNEE=vega CONVERSATION_ID=mission_slug [DISCORD_THREAD_ID=123 REPLY_MODE=direct_discord] BODY='...'
	@if [ -z "$(TITLE)" ]; then echo "TITLE is required" >&2; exit 2; fi
	@if [ -z "$(ASSIGNEE)" ]; then echo "ASSIGNEE is required, e.g. atlas" >&2; exit 2; fi
	@if [ -z "$(CONVERSATION_ID)" ]; then echo "CONVERSATION_ID is required, e.g. mission_readiness_20260506" >&2; exit 2; fi
	@if [ -z "$(BODY)" ]; then echo "BODY is required and must include bounded task instructions" >&2; exit 2; fi
	@thread_line=""; reply_line="reply_mode: kanban_only\nreply_expected: false\n"; \
		if [ -n "$(DISCORD_THREAD_ID)" ]; then thread_line="$$(printf 'discord_thread_id: %s\n' "$(DISCORD_THREAD_ID)")"; fi; \
		if [ "$(REPLY_MODE)" = "direct_discord" ]; then \
			if [ -z "$(DISCORD_THREAD_ID)" ]; then echo "DISCORD_THREAD_ID is required when REPLY_MODE=direct_discord" >&2; exit 2; fi; \
			reply_line="$$(printf 'reply_mode: direct_discord\nreply_target: discord:%s\nreply_expected: true\n' "$(DISCORD_THREAD_ID)")"; \
		fi; \
		body="$$(printf 'conversation_id: %s\n%s%sfrom: atlas\nto: %s\nassignee: %s\n%s\n' "$(CONVERSATION_ID)" "$$thread_line" "$$reply_line" "$(ASSIGNEE)" "$(ASSIGNEE)" "$(BODY)")"; \
		$(COMPOSE) run --rm atlas kanban create "[mission:$(CONVERSATION_ID)] $(TITLE)" --assignee "$(ASSIGNEE)" --body "$$body" --json

kanban-mission-contract-install: ## Install DB triggers rejecting Kanban tasks without mission markers
	python3 scripts/kanban-mission-contract.py install

kanban-mission-contract-uninstall: ## Remove DB mission-contract triggers
	python3 scripts/kanban-mission-contract.py uninstall

kanban-mission-contract-check: ## Audit existing Kanban tasks for missing mission markers
	python3 scripts/kanban-mission-contract.py check

kanban-mission-payload-sample: ## Print a valid deterministic Kanban mission task payload
	python3 scripts/kanban-mission-contract.py sample-payload

kanban-link: ## Link parent->child dependency: make kanban-link PARENT=K... CHILD=K...
	@if [ -z "$(PARENT)" ]; then echo "PARENT is required" >&2; exit 2; fi
	@if [ -z "$(CHILD)" ]; then echo "CHILD is required" >&2; exit 2; fi
	$(COMPOSE) run --rm atlas kanban link "$(PARENT)" "$(CHILD)"

kanban-dispatch: guard-agent ## Run one Kanban task in the assigned agent container: make kanban-dispatch AGENT=forge TASK=K...
	@if [ -z "$(TASK)" ]; then echo "TASK is required" >&2; exit 2; fi
	@if [ "$(DIRECT_REPLY)" = "1" ]; then \
		COMPOSE='$(COMPOSE)' ./scripts/kanban-dispatch-compose.sh $(AGENT) $(TASK) --direct-reply; \
	else \
		COMPOSE='$(COMPOSE)' ./scripts/kanban-dispatch-compose.sh $(AGENT) $(TASK); \
	fi

kanban-dispatcher-once: ## Run one Dockerized Compose-aware dispatcher pass; add DRY_RUN=1 to avoid spawning
	@if [ "$(DRY_RUN)" = "1" ]; then \
		$(COMPOSE) --profile kanban run --rm kanban-dispatcher bash -lc 'python3 scripts/kanban-compose-dispatcher.py --dry-run --max-tasks $${MAX_TASKS:-1} --worker-timeout $${KANBAN_DISPATCH_WORKER_TIMEOUT:-900}'; \
	else \
		$(COMPOSE) --profile kanban run --rm kanban-dispatcher bash -lc 'python3 scripts/kanban-compose-dispatcher.py --max-tasks $${MAX_TASKS:-1} --worker-timeout $${KANBAN_DISPATCH_WORKER_TIMEOUT:-900}'; \
	fi

kanban-dispatcher-daemon: ## Start the Dockerized Compose-aware Kanban dispatcher daemon; KANBAN_DISPATCH_INTERVAL=60 KANBAN_DISPATCH_MAX_TASKS=1 KANBAN_DISPATCH_WORKER_TIMEOUT=900
	$(COMPOSE) --profile kanban up -d kanban-dispatcher

kanban-dispatcher-stop: ## Stop the Dockerized Kanban dispatcher daemon
	$(COMPOSE) --profile kanban stop kanban-dispatcher

kanban-dispatcher-logs: ## Follow Dockerized Kanban dispatcher logs
	$(COMPOSE) --profile kanban logs -f kanban-dispatcher

kanban-notifier-once: ## Process new Kanban mission events into notification outbox rows
	python3 scripts/kanban-mission-notifier.py --limit $${LIMIT:-100}

kanban-notifier-daemon: ## Start the Dockerized Kanban mission notifier daemon; KANBAN_NOTIFIER_DELIVER=1 posts updates
	$(COMPOSE) --profile kanban up -d kanban-notifier

kanban-notifier-stop: ## Stop the Dockerized Kanban mission notifier daemon
	$(COMPOSE) --profile kanban stop kanban-notifier

kanban-notifier-logs: ## Follow Dockerized Kanban notifier container logs
	$(COMPOSE) --profile kanban logs -f kanban-notifier

kanban-notifier-deliver: ## Deliver pending mission notification outbox rows through Discord status webhook
	python3 scripts/kanban-mission-notifier.py --deliver --limit $${LIMIT:-100}

kanban-notifier-dry-run: ## Preview pending mission notification delivery without posting
	python3 scripts/kanban-mission-notifier.py --dry-run --limit $${LIMIT:-100}

discord-status-dry-run: ## Dry-run a Discord status post: make discord-status-dry-run MESSAGE='...'
	@if [ -z "$(MESSAGE)" ]; then echo "MESSAGE is required" >&2; exit 2; fi
	printf '%s' "$(MESSAGE)" | python3 scripts/discord-post-status.py --dry-run

mcp-list: guard-agent ## List MCP servers configured for one agent
	$(COMPOSE) run --rm $(AGENT) mcp list

mcp-list-all: ## List MCP servers configured for every team agent
	@for agent in $(TEAM_AGENTS); do \
		printf '\n==> %s MCP servers\n' "$$agent"; \
		$(COMPOSE) run --rm "$$agent" mcp list || true; \
	done

mcp-test: guard-agent guard-server ## Test one MCP server for one agent, e.g. make mcp-test AGENT=atlas SERVER=time
	$(COMPOSE) run --rm $(AGENT) mcp test $(SERVER)

mcp-remove: guard-agent guard-server ## Remove one MCP server from one agent config
	$(COMPOSE) run --rm $(AGENT) mcp remove $(SERVER)

mcp-add-command: guard-agent guard-server guard-command ## Register a stdio MCP server with COMMAND='npx -y pkg args...'
	$(COMPOSE) run --rm $(AGENT) mcp add $(SERVER) --command "$(COMMAND)"

mcp-add-url: guard-agent guard-server guard-url ## Register an HTTP MCP server with URL=https://example.com/mcp
	$(COMPOSE) run --rm $(AGENT) mcp add $(SERVER) --url "$(URL)"

mcp-register-template: guard-agent guard-server ## Register SERVER from shared/mcp/registry/<SERVER>.mk for one agent
	@if [ ! -f "shared/mcp/registry/$(SERVER).mk" ]; then \
		echo "Missing template: shared/mcp/registry/$(SERVER).mk" >&2; exit 2; \
	fi
	@if [ "$(MCP_TRANSPORT)" = "command" ]; then \
		if [ -z "$(MCP_COMMAND)" ]; then echo "MCP_COMMAND is empty in shared/mcp/registry/$(SERVER).mk" >&2; exit 2; fi; \
		$(COMPOSE) run --rm $(AGENT) mcp add $(SERVER) --command "$(MCP_COMMAND)"; \
	elif [ "$(MCP_TRANSPORT)" = "url" ]; then \
		if [ -z "$(MCP_URL)" ]; then echo "MCP_URL is empty in shared/mcp/registry/$(SERVER).mk" >&2; exit 2; fi; \
		$(COMPOSE) run --rm $(AGENT) mcp add $(SERVER) --url "$(MCP_URL)"; \
	else \
		echo "Unsupported or missing MCP_TRANSPORT in shared/mcp/registry/$(SERVER).mk; expected 'command' or 'url'" >&2; exit 2; \
	fi

mcp-register-template-all: guard-server ## Register SERVER template for TARGET_AGENTS='atlas forge' or all by default
	@if [ ! -f "shared/mcp/registry/$(SERVER).mk" ]; then \
		echo "Missing template: shared/mcp/registry/$(SERVER).mk" >&2; exit 2; \
	fi
	@for agent in $(TARGET_AGENTS); do \
		printf '\n==> registering %s for %s\n' "$(SERVER)" "$$agent"; \
		$(MAKE) --no-print-directory mcp-register-template AGENT="$$agent" SERVER="$(SERVER)"; \
	done

mcp-templates: ## List shared MCP registry templates
	@printf "Shared MCP registry templates:\n"
	@for file in shared/mcp/registry/*.mk; do \
		[ -e "$$file" ] || continue; \
		basename "$$file" .mk; \
	done

mcp-show-template: guard-server ## Print shared/mcp/registry/<SERVER>.mk
	@if [ ! -f "shared/mcp/registry/$(SERVER).mk" ]; then \
		echo "Missing template: shared/mcp/registry/$(SERVER).mk" >&2; exit 2; \
	fi
	@sed -n '1,160p' "shared/mcp/registry/$(SERVER).mk"

guard-agent:
	@if [ -z "$(AGENT)" ]; then echo "AGENT is required, e.g. AGENT=atlas" >&2; exit 2; fi
	@if ! printf '%s\n' $(TEAM_AGENTS) | grep -qx "$(AGENT)"; then \
		echo "Unknown AGENT='$(AGENT)'. Expected one of: $(TEAM_AGENTS)" >&2; exit 2; \
	fi

guard-server:
	@if [ -z "$(SERVER)" ]; then echo "SERVER is required, e.g. SERVER=time" >&2; exit 2; fi

guard-command:
	@if [ -z "$(COMMAND)" ]; then echo "COMMAND is required, e.g. COMMAND='npx -y @modelcontextprotocol/server-filesystem /workspace'" >&2; exit 2; fi

guard-url:
	@if [ -z "$(URL)" ]; then echo "URL is required, e.g. URL=https://mcp.example.com/mcp" >&2; exit 2; fi
