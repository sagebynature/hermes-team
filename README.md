# Hermes Startup Team Docker Workspace

This repository defines a Dockerized virtual startup team made of independent Hermes Agent gateways. Each agent has its own durable Hermes home, private workspace, persona, secrets, sessions, skills, memories, and logs.

The layout follows the Hermes Docker convention:

```text
host directory -> container path
agents/<agent>/home      -> /opt/data
agents/<agent>/workspace -> /workspace
```

Hermes stores config, API keys, sessions, skills, memories, and logs under `/opt/data`. Agent-generated work lives under `/workspace`.

---

## Team roster

| Agent | Role | Primary responsibility |
|---|---|---|
| **Atlas** | Orchestrator / Chief of Staff | Routes work, decomposes objectives, tracks decisions, synthesizes output |
| **Vega** | Product Strategist | Product strategy, ICP, MVP scope, PRDs, roadmap, prioritization |
| **Scout** | Market + Customer Research | Market research, competitors, customer discovery, pricing intelligence |
| **Forge** | Engineering Lead | Architecture, implementation, prototypes, APIs, technical tradeoffs |
| **Lumen** | UX / Design Lead | UX flows, interface structure, onboarding, design critique, UI copy |
| **Blitz** | Growth + GTM | Launch plans, acquisition experiments, messaging, funnels, distribution |
| **Ledger** | Finance + Ops | Budgets, runway, pricing models, unit economics, operating cadence |
| **Sentinel** | Legal / Risk / Compliance | Legal/risk/compliance/security issue spotting and mitigations |

Default coordination model: **Sage → Atlas → specialists → Atlas → Sage**.

---

## Directory structure

```text
hermes-startup-team/
  docker-compose.yml
  README.md
  .gitignore

  docker/
    Dockerfile
    .dockerignore
    mise/
      config.toml

  scripts/
    setup-agent.sh
    doctor-all.sh

  shared/
    project/       # shared project context, mounted readonly
    skills/        # shared skills, mounted readonly
    mcp/           # shared MCP scripts/configs, mounted readonly

  agents/
    atlas/
      README.md
      home/        # mounted as /opt/data
        config.yaml
        .env
        .env.example
        persona.md
        skills/
        sessions/
        logs/
        memory/
        mcp/
      workspace/   # mounted as /workspace
        .mise.toml
        inbox/
        outbox/
        artifacts/
        notes/

    vega/
    scout/
    forge/
    lumen/
    blitz/
    ledger/
    sentinel/
```

---

## Mount model

Every service mounts the same shape:

```yaml
volumes:
  - ./agents/<agent>/home:/opt/data
  - ./agents/<agent>/workspace:/workspace
  - ./shared/project:/shared/project:ro
  - ./shared/skills:/shared/skills:ro
  - ./shared/mcp:/shared/mcp:ro
```

Inside the container:

| Container path | Purpose |
|---|---|
| `/opt/data` | Hermes durable home: `config.yaml`, `.env`, `auth.json`, `skills/`, `sessions/`, `logs/`, `memory/` |
| `/workspace` | Agent-owned working directory |
| `/shared/project` | Shared project context, readonly |
| `/shared/skills` | Shared skill source, readonly |
| `/shared/mcp` | Shared MCP config/scripts, readonly |

Each `config.yaml` sets:

```yaml
terminal:
  backend: local
  cwd: /workspace
```

So tools run inside the agent's private mounted workspace by default.

---

## Custom Docker image

The Compose stack builds a local image:

```text
hermes-startup-agent:latest
```

from:

```text
docker/Dockerfile
```

It extends:

```text
nousresearch/hermes-agent:latest
```

and adds [mise-en-place](https://mise.jdx.dev/) plus common runtime support for agent workspaces and MCP servers:

- `mise`
- `node@lts`
- `npm`
- `npx`
- `uv`
- `uvx`
- `jq`
- `ripgrep`
- `git`
- `openssh-client`
- `zip` / `unzip`

Global mise config lives at:

```text
docker/mise/config.toml
```

Current global tools:

```toml
[tools]
node = "lts"
uv = "latest"
```

Each agent also has an editable workspace-level mise file:

```text
agents/<agent>/workspace/.mise.toml
```

Use that file to add agent-specific tools like Python, Go, Rust, Bun, pnpm, etc.

Example for Forge:

```toml
[tools]
python = "3.12"
go = "latest"
rust = "latest"
node = "lts"
uv = "latest"
```

Then install inside that agent container:

```bash
docker compose run --rm forge mise install
```

---

## Bootstrap

From this directory:

```bash
cd /Users/sage/hermes-startup-team
```

Build the custom image:

```bash
docker compose build
```

Set up Atlas first:

```bash
docker compose run --rm atlas setup
docker compose run --rm atlas gateway setup
docker compose run --rm atlas doctor
```

Or use the helper script:

```bash
./scripts/setup-agent.sh atlas
```

Repeat for specialists you want live:

```bash
./scripts/setup-agent.sh vega
./scripts/setup-agent.sh scout
./scripts/setup-agent.sh forge
./scripts/setup-agent.sh lumen
./scripts/setup-agent.sh blitz
./scripts/setup-agent.sh ledger
./scripts/setup-agent.sh sentinel
```

Start all gateways:

```bash
docker compose up -d
```

Follow logs:

```bash
docker compose logs -f atlas
```

Check all agents:

```bash
./scripts/doctor-all.sh
```

---

## Gateway API ports

All ports are bound to localhost for safety:

| Agent | URL |
|---|---|
| Atlas | http://127.0.0.1:8642 |
| Vega | http://127.0.0.1:8643 |
| Scout | http://127.0.0.1:8644 |
| Forge | http://127.0.0.1:8645 |
| Lumen | http://127.0.0.1:8646 |
| Blitz | http://127.0.0.1:8647 |
| Ledger | http://127.0.0.1:8648 |
| Sentinel | http://127.0.0.1:8649 |

If you only use Discord, Telegram, Slack, or another messaging gateway, exposing API ports is optional. Keep them localhost-bound unless you intentionally need external access.

---

## Secrets and auth

Each agent has its own secrets file:

```text
agents/<agent>/home/.env
```

Each one starts from:

```text
agents/<agent>/home/.env.example
```

Common entries:

```bash
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
DISCORD_BOT_TOKEN=
GITHUB_TOKEN=
GATEWAY_API_KEY=
```

Rules:

- Do **not** commit real `.env` files.
- Prefer one gateway/bot token per agent.
- Prefer one provider key or credential pool per agent if you want independent accounting/revocation.
- OAuth/credential-pool state should remain in the mounted `home/`, not baked into the image.

For OAuth/provider login flows:

```bash
docker compose run --rm atlas login --provider <provider>
```

For credential pools:

```bash
docker compose run --rm atlas auth add
docker compose run --rm atlas auth list
```

---

## Persona files

Each agent has an editable persona:

```text
agents/<agent>/home/persona.md
```

Each `config.yaml` includes metadata pointing at:

```yaml
startup_agent:
  persona_file: /opt/data/persona.md
```

If your Hermes runtime does not automatically consume that persona file, wire it in using one of these patterns:

1. Copy it into Hermes' native personality/persona path during setup.
2. Convert the persona into an agent-specific skill and preload it.
3. Add a small gateway/router wrapper that injects the persona at session start.
4. Keep it as explicit operating documentation for the agent and human operators.

---

## Agent workspace convention

Each agent owns:

```text
agents/<agent>/workspace/
```

Inside the container this is:

```text
/workspace
```

Workspace subdirectories:

| Directory | Use |
|---|---|
| `inbox/` | Task briefs, requests, input docs |
| `outbox/` | Finished deliverables ready for Atlas/Sage |
| `artifacts/` | Generated files, prototypes, exports |
| `notes/` | Working notes and scratch docs |

Recommended rule: specialists write durable deliverables to `outbox/`, not only chat responses.

---

## Shared context

Use this for company-wide/project-wide files all agents can read:

```text
shared/project/
```

Mounted as:

```text
/shared/project:ro
```

Good candidates:

- company brief
- product strategy
- customer notes
- architecture docs
- brand voice
- decision logs exported by Atlas

Because it is readonly inside containers, agents cannot accidentally corrupt shared source-of-truth files.

---

## Skills

Per-agent editable skills live here:

```text
agents/<agent>/home/skills/
```

Shared readonly skills live here:

```text
shared/skills/
```

Mounted as:

```text
/shared/skills:ro
```

Install or inspect skills inside a specific agent container:

```bash
docker compose run --rm atlas skills list
docker compose run --rm atlas skills browse
docker compose run --rm atlas skills install <skill-id>
```

Tool/skill changes may require a new Hermes session or gateway restart.

---

## MCP

Add MCP servers per agent from inside the relevant container.

Example: filesystem MCP for Forge:

```bash
docker compose run --rm forge mcp add filesystem --command "npx -y @modelcontextprotocol/server-filesystem /workspace"
docker compose run --rm forge mcp list
docker compose run --rm forge mcp test filesystem
```

Because the custom image includes `node`, `npx`, `uv`, and `uvx`, common stdio MCP servers should work without rebuilding.

If an MCP server needs additional tools, add them to the relevant agent's:

```text
agents/<agent>/workspace/.mise.toml
```

Then run:

```bash
docker compose run --rm <agent> mise install
```

For shared production-grade MCP servers, consider HTTP MCP servers reachable by all containers rather than duplicating stdio server processes per agent.

---

## Common commands

Build:

```bash
docker compose build
```

Start all:

```bash
docker compose up -d
```

Stop all:

```bash
docker compose down
```

Logs:

```bash
docker compose logs -f atlas
docker compose logs -f forge
```

Run a one-off Hermes command:

```bash
docker compose run --rm atlas status --all
docker compose run --rm forge doctor
```

Open a shell in an agent container:

```bash
docker compose run --rm --entrypoint bash forge
```

Verify mise and runtimes:

```bash
docker compose run --rm --entrypoint mise atlas --version
docker compose run --rm --entrypoint node atlas --version
docker compose run --rm --entrypoint uv atlas --version
```

Validate Compose:

```bash
docker compose config
```

---

## Security notes

- Keep gateway API ports bound to `127.0.0.1` unless external access is intentional.
- Do not bake secrets into the Docker image.
- Do not mount your whole home directory into agent containers.
- Do not mount `/var/run/docker.sock` unless you intentionally want that agent to control host Docker.
- Use separate bot tokens and API keys where practical.
- Keep `security.redact_secrets: true` in each `config.yaml`.
- Prefer Atlas as the only agent allowed to fan out work to other agents.
- Give agents narrow tool and credential access based on role.

---

## Troubleshooting

### Build fails while installing mise tools

Try rebuilding without cache:

```bash
docker compose build --no-cache
```

If a specific mise tool fails, remove it from `docker/mise/config.toml` and install it per-agent from `agents/<agent>/workspace/.mise.toml` instead.

### MCP command not found

Check inside the container:

```bash
docker compose run --rm --entrypoint bash forge
which node
which npx
which uv
which uvx
mise ls
```

Then update either global `docker/mise/config.toml` or that agent's `.mise.toml`.

### Gateway does not respond in Discord

Check:

- the agent's `DISCORD_BOT_TOKEN` in `agents/<agent>/home/.env`
- Discord **Message Content Intent** is enabled
- the bot has channel permissions
- gateway logs:

```bash
docker compose logs -f <agent>
```

### Config/persona changes not taking effect

Restart the relevant gateway:

```bash
docker compose restart <agent>
```

or start a fresh Hermes session if the change affects tools/skills/persona context.
