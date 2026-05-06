SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

COMPOSE_FILES ?= -f docker-compose.profiles.yml
COMPOSE ?= docker compose $(COMPOSE_FILES)
LEGACY_COMPOSE_FILES ?= -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml
LEGACY_COMPOSE ?= docker compose $(LEGACY_COMPOSE_FILES)
TEAM_NEXUS_UID ?= $(shell id -u)
TEAM_NEXUS_GID ?= $(shell id -g)
PROFILE ?= atlas
AGENT ?= $(PROFILE)
SERVICE ?= atlas-gateway
export TEAM_NEXUS_UID TEAM_NEXUS_GID SLUG NAME ROLE GATEWAY_PORT DASHBOARD_PORT FORCE PROFILE AGENT SERVICE
# Profile-driven defaults. Legacy generated roster remains available through
# shared/team-agents.yaml and scripts/team_registry.py until old runtime paths are removed.
TEAM_AGENTS ?= atlas forge sentinel scribe curator
DASHBOARD_AGENTS ?= $(TEAM_AGENTS)
TARGET_AGENTS ?= $(TEAM_AGENTS)
TEAM_REGISTRY := python3 scripts/team_registry.py

# When SERVER is set, optionally load a shared MCP registry definition.
# Example: make mcp-register-template AGENT=atlas SERVER=time
ifneq ($(strip $(SERVER)),)
-include shared/mcp/registry/$(SERVER).mk
endif

.PHONY: help build up down restart ps logs shell doctor doctor-all compose-config workspace-init \
	generate check-generated validate preflight profile-validate profile-render-dry-run profile-render-docker-dry-run profile-runtime-stage profile-compose-config registry-list registry-validate registry-next-ports validate-plugins dashboards-up dashboards-restart \
	agent-add agent-disable agent-archive \
	kanban-init kanban-list kanban-stats kanban-watch kanban-create kanban-link kanban-dispatch \
	kanban-dispatcher-once kanban-dispatcher-daemon kanban-dispatcher-stop kanban-dispatcher-logs \
	kanban-notifier-once kanban-notifier-daemon kanban-notifier-stop kanban-notifier-logs kanban-notifier-deliver kanban-notifier-dry-run discord-status-dry-run \
	mcp-list mcp-list-all mcp-test mcp-remove mcp-add-command mcp-add-url \
	mcp-register-template mcp-register-template-all mcp-templates mcp-show-template \
	guard-agent guard-server guard-command guard-url

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "; printf "Usage:\n  make <target> [PROFILE=atlas] [SERVICE=atlas-gateway] [SERVER=name] ...\n\nTargets:\n"} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-30s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf "\nProfiles:\n  $(TEAM_AGENTS)\n"
	@printf "\nMCP examples:\n"
	@printf "  make mcp-list PROFILE=atlas\n"
	@printf "  make mcp-add-command PROFILE=forge SERVER=filesystem COMMAND='npx -y @modelcontextprotocol/server-filesystem /workspace'\n"
	@printf "  make mcp-register-template PROFILE=atlas SERVER=time\n"
	@printf "  make mcp-register-template-all SERVER=filesystem-workspace TARGET_AGENTS='atlas forge'\n"

build: ## Build the custom Hermes team image once; all profiles share team-nexus-agent:latest
	$(COMPOSE) build atlas-gateway

up: profile-runtime-stage ## Start Atlas gateway and dashboard on the profile-driven runtime
	$(COMPOSE) --profile dashboard up -d atlas-gateway dashboard

down: ## Stop profile-driven runtime services
	$(COMPOSE) --profile dashboard --profile admin --profile dispatcher-once down

restart: profile-runtime-stage ## Restart Atlas gateway and dashboard on the profile-driven runtime
	$(COMPOSE) --profile dashboard up -d --force-recreate atlas-gateway dashboard

ps: ## Show profile-driven Compose service status
	$(COMPOSE) --profile dashboard --profile admin --profile dispatcher-once ps

logs: ## Follow logs for one profile runtime service, e.g. make logs SERVICE=atlas-gateway
	$(COMPOSE) --profile dashboard logs -f $(SERVICE)

shell: profile-runtime-stage ## Open bash in the profile runtime, e.g. make shell PROFILE=forge
	$(COMPOSE) --profile admin run --rm --entrypoint bash -e HERMES_HOME=/opt/data/profiles/$(PROFILE) admin-shell

doctor: profile-runtime-stage ## Run hermes doctor for one rendered profile, e.g. make doctor PROFILE=forge
	$(COMPOSE) run --rm -e HERMES_HOME=/opt/data/profiles/$(PROFILE) atlas-gateway doctor

doctor-all: profile-runtime-stage ## Run hermes doctor for every active Team Nexus profile
	@for profile in $(TEAM_AGENTS); do \
		printf '\n==> %s doctor\n' "$$profile"; \
		$(COMPOSE) run --rm -e HERMES_HOME=/opt/data/profiles/"$$profile" atlas-gateway doctor; \
	done

compose-config: ## Validate profile-driven docker-compose.yml
	$(COMPOSE) --profile dashboard --profile admin --profile dispatcher-once config >/tmp/team-nexus-compose.yaml
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

profile-render-dry-run: ## Preview host profile files rendered from profile specs
	python3 scripts/render-profile-spec.py --mode host

profile-render-docker-dry-run: ## Preview Docker profile files rendered from profile specs
	python3 scripts/render-profile-spec.py --mode docker

profile-runtime-stage: ## Render Docker profile files into ignored runtime/hermes/profiles
	python3 scripts/render-profile-spec.py --mode docker --write --output-dir runtime/hermes/profiles

profile-compose-config: ## Validate profile-driven Docker Compose function services
	docker compose -f docker-compose.profiles.yml --profile dashboard --profile admin --profile dispatcher-once config >/dev/null

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

dashboards-up: profile-runtime-stage ## Start the profile-driven dashboard service
	$(COMPOSE) --profile dashboard up -d dashboard

dashboards-restart: profile-runtime-stage ## Restart the profile-driven dashboard service
	$(COMPOSE) --profile dashboard up -d --force-recreate dashboard

workspace-init: ## Initialize shared workspace directories and artifact handoff placeholder
	@mkdir -p shared/project/artifacts shared/kanban
	@if [ ! -f shared/project/artifacts/.gitignore ]; then \
		printf '*\n!.gitignore\n' > shared/project/artifacts/.gitignore; \
	fi
	@chmod 2775 shared/project/artifacts shared/kanban 2>/dev/null || true
	@echo "workspace initialized: shared/project/artifacts and shared/kanban"

kanban-init: profile-runtime-stage workspace-init ## Initialize the shared Team Nexus Kanban board
	$(COMPOSE) run --rm atlas-gateway kanban init

kanban-list: profile-runtime-stage ## List shared Kanban tasks
	$(COMPOSE) run --rm atlas-gateway kanban list

kanban-stats: profile-runtime-stage ## Show shared Kanban task counts
	$(COMPOSE) run --rm atlas-gateway kanban stats

kanban-watch: profile-runtime-stage ## Watch shared Kanban board events
	$(COMPOSE) run --rm atlas-gateway kanban watch

kanban-create: profile-runtime-stage ## Create a mission-scoped Kanban task: make kanban-create TITLE='...' ASSIGNEE=forge CONVERSATION_ID=mission_slug [DISCORD_THREAD_ID=123 REPLY_MODE=direct_discord] BODY='...'
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
		$(COMPOSE) run --rm atlas-gateway kanban create "[mission:$(CONVERSATION_ID)] $(TITLE)" --assignee "$(ASSIGNEE)" --body "$$body" --json

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
	$(COMPOSE) run --rm atlas-gateway kanban link "$(PARENT)" "$(CHILD)"

kanban-dispatch: profile-runtime-stage ## Run native one-shot dispatcher for profile-driven tasks
	$(COMPOSE) --profile dispatcher-once run --rm kanban-dispatcher

kanban-dispatcher-once: profile-runtime-stage ## Run native one-shot dispatcher; MAX_TASKS controls cap; DRY_RUN=1 previews
	@if [ "$(DRY_RUN)" = "1" ]; then \
		$(COMPOSE) --profile dispatcher-once run --rm kanban-dispatcher kanban dispatch --dry-run --max $${MAX_TASKS:-1}; \
	else \
		$(COMPOSE) --profile dispatcher-once run --rm kanban-dispatcher kanban dispatch --max $${MAX_TASKS:-1}; \
	fi

kanban-dispatcher-daemon: ## Native dispatcher is embedded in atlas-gateway; start the gateway instead
	$(MAKE) up

kanban-dispatcher-stop: ## Stop the Atlas gateway that hosts native dispatch
	$(COMPOSE) stop atlas-gateway

kanban-dispatcher-logs: ## Follow Atlas gateway logs for native dispatcher activity
	$(COMPOSE) logs -f atlas-gateway

kanban-notifier-once: ## Process new Kanban mission events into notification outbox rows
	python3 scripts/kanban-mission-notifier.py --limit $${LIMIT:-100}

kanban-notifier-daemon: ## Start the legacy Dockerized Kanban mission notifier daemon; KANBAN_NOTIFIER_DELIVER=1 posts updates
	$(LEGACY_COMPOSE) --profile kanban up -d kanban-notifier

kanban-notifier-stop: ## Stop the legacy Dockerized Kanban mission notifier daemon
	$(LEGACY_COMPOSE) --profile kanban stop kanban-notifier

kanban-notifier-logs: ## Follow legacy Dockerized Kanban notifier container logs
	$(LEGACY_COMPOSE) --profile kanban logs -f kanban-notifier

kanban-notifier-deliver: ## Deliver pending mission notification outbox rows through Discord status webhook
	python3 scripts/kanban-mission-notifier.py --deliver --limit $${LIMIT:-100}

kanban-notifier-dry-run: ## Preview pending mission notification delivery without posting
	python3 scripts/kanban-mission-notifier.py --dry-run --limit $${LIMIT:-100}

discord-status-dry-run: ## Dry-run a Discord status post: make discord-status-dry-run MESSAGE='...'
	@if [ -z "$(MESSAGE)" ]; then echo "MESSAGE is required" >&2; exit 2; fi
	printf '%s' "$(MESSAGE)" | python3 scripts/discord-post-status.py --dry-run

mcp-list: profile-runtime-stage guard-agent ## List MCP servers configured for one profile
	$(COMPOSE) run --rm -e HERMES_HOME=/opt/data/profiles/$(AGENT) atlas-gateway mcp list

mcp-list-all: profile-runtime-stage ## List MCP servers configured for every active profile
	@for agent in $(TEAM_AGENTS); do \
		printf '\n==> %s MCP servers\n' "$$agent"; \
		$(COMPOSE) run --rm -e HERMES_HOME=/opt/data/profiles/"$$agent" atlas-gateway mcp list || true; \
	done

mcp-test: profile-runtime-stage guard-agent guard-server ## Test one MCP server for one profile, e.g. make mcp-test PROFILE=atlas SERVER=time
	$(COMPOSE) run --rm -e HERMES_HOME=/opt/data/profiles/$(AGENT) atlas-gateway mcp test $(SERVER)

mcp-remove: profile-runtime-stage guard-agent guard-server ## Remove one MCP server from one profile config
	$(COMPOSE) run --rm -e HERMES_HOME=/opt/data/profiles/$(AGENT) atlas-gateway mcp remove $(SERVER)

mcp-add-command: profile-runtime-stage guard-agent guard-server guard-command ## Register a stdio MCP server with COMMAND='npx -y pkg args...'
	$(COMPOSE) run --rm -e HERMES_HOME=/opt/data/profiles/$(AGENT) atlas-gateway mcp add $(SERVER) --command "$(COMMAND)"

mcp-add-url: profile-runtime-stage guard-agent guard-server guard-url ## Register an HTTP MCP server with URL=https://example.com/mcp
	$(COMPOSE) run --rm -e HERMES_HOME=/opt/data/profiles/$(AGENT) atlas-gateway mcp add $(SERVER) --url "$(URL)"

mcp-register-template: profile-runtime-stage guard-agent guard-server ## Register SERVER from shared/mcp/registry/<SERVER>.mk for one profile
	@if [ ! -f "shared/mcp/registry/$(SERVER).mk" ]; then \
		echo "Missing template: shared/mcp/registry/$(SERVER).mk" >&2; exit 2; \
	fi
	@if [ "$(MCP_TRANSPORT)" = "command" ]; then \
		if [ -z "$(MCP_COMMAND)" ]; then echo "MCP_COMMAND is empty in shared/mcp/registry/$(SERVER).mk" >&2; exit 2; fi; \
		$(COMPOSE) run --rm -e HERMES_HOME=/opt/data/profiles/$(AGENT) atlas-gateway mcp add $(SERVER) --command "$(MCP_COMMAND)"; \
	elif [ "$(MCP_TRANSPORT)" = "url" ]; then \
		if [ -z "$(MCP_URL)" ]; then echo "MCP_URL is empty in shared/mcp/registry/$(SERVER).mk" >&2; exit 2; fi; \
		$(COMPOSE) run --rm -e HERMES_HOME=/opt/data/profiles/$(AGENT) atlas-gateway mcp add $(SERVER) --url "$(MCP_URL)"; \
	else \
		echo "Unsupported or missing MCP_TRANSPORT in shared/mcp/registry/$(SERVER).mk; expected 'command' or 'url'" >&2; exit 2; \
	fi

mcp-register-template-all: profile-runtime-stage guard-server ## Register SERVER template for TARGET_AGENTS='atlas forge' or all by default
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
	@if [ -z "$(AGENT)" ]; then echo "PROFILE is required, e.g. PROFILE=atlas" >&2; exit 2; fi
	@if ! printf '%s\n' $(TEAM_AGENTS) | grep -qx "$(AGENT)"; then \
		echo "Unknown PROFILE='$(AGENT)'. Expected one of: $(TEAM_AGENTS)" >&2; exit 2; \
	fi

guard-server:
	@if [ -z "$(SERVER)" ]; then echo "SERVER is required, e.g. SERVER=time" >&2; exit 2; fi

guard-command:
	@if [ -z "$(COMMAND)" ]; then echo "COMMAND is required, e.g. COMMAND='npx -y @modelcontextprotocol/server-filesystem /workspace'" >&2; exit 2; fi

guard-url:
	@if [ -z "$(URL)" ]; then echo "URL is required, e.g. URL=https://mcp.example.com/mcp" >&2; exit 2; fi
