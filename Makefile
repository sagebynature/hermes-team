SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
TEAM_AGENTS := atlas vega scout forge lumen blitz ledger sentinel
TARGET_AGENTS ?= $(TEAM_AGENTS)

# When SERVER is set, optionally load a shared MCP registry definition.
# Example: make mcp-register-template AGENT=atlas SERVER=time
ifneq ($(strip $(SERVER)),)
-include shared/mcp/registry/$(SERVER).mk
endif

.PHONY: help build up down restart ps logs shell doctor doctor-all compose-config workspace-init \
	kanban-init kanban-list kanban-stats kanban-watch kanban-create kanban-link kanban-dispatch \
	kanban-dispatcher-once kanban-dispatcher-daemon kanban-dispatcher-stop kanban-dispatcher-logs discord-status-dry-run \
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

up: ## Start all Hermes gateways
	$(COMPOSE) up -d

down: ## Stop all Hermes gateways
	$(COMPOSE) down

restart: ## Restart all Hermes gateways
	$(COMPOSE) restart

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

kanban-create: ## Create a shared Kanban task: make kanban-create TITLE='...' ASSIGNEE=atlas
	@if [ -z "$(TITLE)" ]; then echo "TITLE is required" >&2; exit 2; fi
	@if [ -z "$(ASSIGNEE)" ]; then echo "ASSIGNEE is required, e.g. atlas" >&2; exit 2; fi
	$(COMPOSE) run --rm atlas kanban create "$(TITLE)" --assignee "$(ASSIGNEE)"

kanban-link: ## Link parent->child dependency: make kanban-link PARENT=K... CHILD=K...
	@if [ -z "$(PARENT)" ]; then echo "PARENT is required" >&2; exit 2; fi
	@if [ -z "$(CHILD)" ]; then echo "CHILD is required" >&2; exit 2; fi
	$(COMPOSE) run --rm atlas kanban link "$(PARENT)" "$(CHILD)"

kanban-dispatch: guard-agent ## Run one Kanban task in the assigned agent container: make kanban-dispatch AGENT=forge TASK=K...
	@if [ -z "$(TASK)" ]; then echo "TASK is required" >&2; exit 2; fi
	./scripts/kanban-dispatch-compose.sh $(AGENT) $(TASK)

kanban-dispatcher-once: ## Run one Dockerized Compose-aware dispatcher pass; add DRY_RUN=1 to avoid spawning
	@if [ "$(DRY_RUN)" = "1" ]; then \
		$(COMPOSE) --profile dispatcher run --rm kanban-dispatcher bash -lc 'python3 scripts/kanban-compose-dispatcher.py --dry-run --max-tasks $${MAX_TASKS:-1} --worker-timeout $${KANBAN_DISPATCH_WORKER_TIMEOUT:-900}'; \
	else \
		$(COMPOSE) --profile dispatcher run --rm kanban-dispatcher bash -lc 'python3 scripts/kanban-compose-dispatcher.py --max-tasks $${MAX_TASKS:-1} --worker-timeout $${KANBAN_DISPATCH_WORKER_TIMEOUT:-900}'; \
	fi

kanban-dispatcher-daemon: ## Start the Dockerized Compose-aware Kanban dispatcher daemon; KANBAN_DISPATCH_INTERVAL=60 KANBAN_DISPATCH_MAX_TASKS=1 KANBAN_DISPATCH_WORKER_TIMEOUT=900
	$(COMPOSE) --profile dispatcher up -d kanban-dispatcher

kanban-dispatcher-stop: ## Stop the Dockerized Kanban dispatcher daemon
	$(COMPOSE) --profile dispatcher stop kanban-dispatcher

kanban-dispatcher-logs: ## Follow Dockerized Kanban dispatcher logs
	$(COMPOSE) --profile dispatcher logs -f kanban-dispatcher

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
