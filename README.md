# Team Nexus

Dockerized virtual startup team powered by [Hermes Agent](https://hermes-agent.nousresearch.com/).

Team Nexus is a repo-local operating system for a multi-agent startup team. It runs one independent Hermes Agent gateway per specialist, with isolated homes, workspaces, memories, credentials, skills, sessions, and logs — plus shared read-only context for team-wide knowledge.

> Default coordination model: **Sage → Atlas → specialists → Atlas → Sage**.

---

## The team

Portraits are stored in `.docs/image/` and can be used in docs, launch pages, or team dashboards.

<table>
  <tr>
    <td align="center" width="25%"><img src=".docs/image/atlas.jpeg" alt="Atlas portrait" width="140"><br><strong>Atlas</strong><br><em>Orchestrator / Chief of Staff</em></td>
    <td align="center" width="25%"><img src=".docs/image/vega.jpeg" alt="Vega portrait" width="140"><br><strong>Vega</strong><br><em>Product Strategist</em></td>
    <td align="center" width="25%"><img src=".docs/image/scout.jpeg" alt="Scout portrait" width="140"><br><strong>Scout</strong><br><em>Market + Customer Research</em></td>
    <td align="center" width="25%"><img src=".docs/image/forge.jpeg" alt="Forge portrait" width="140"><br><strong>Forge</strong><br><em>Engineering Lead</em></td>
  </tr>
  <tr>
    <td align="center" width="25%"><img src=".docs/image/lumen.jpeg" alt="Lumen portrait" width="140"><br><strong>Lumen</strong><br><em>UX / Design Lead</em></td>
    <td align="center" width="25%"><img src=".docs/image/blitz.jpeg" alt="Blitz portrait" width="140"><br><strong>Blitz</strong><br><em>Growth + GTM</em></td>
    <td align="center" width="25%"><img src=".docs/image/ledger.jpeg" alt="Ledger portrait" width="140"><br><strong>Ledger</strong><br><em>Finance + Ops</em></td>
    <td align="center" width="25%"><img src=".docs/image/sentinel.jpeg" alt="Sentinel portrait" width="140"><br><strong>Sentinel</strong><br><em>Legal / Risk / Compliance</em></td>
  </tr>
</table>

| Agent | Role | Primary responsibility |
|---|---|---|
| **Atlas** | Orchestrator / Chief of Staff | Routes work, decomposes objectives, tracks decisions, synthesizes output |
| **Vega** | Product Strategist | Product strategy, ICP, MVP scope, PRDs, roadmap, prioritization |
| **Scout** | Market + Customer Research | Market research, competitors, customer discovery, pricing intelligence |
| **Forge** | Engineering Lead | Architecture, implementation, prototypes, APIs, technical tradeoffs |
| **Lumen** | UX / Design Lead | UX flows, interface structure, onboarding, design critique, UI copy |
| **Blitz** | Growth + GTM | Launch plans, acquisition experiments, messaging, funnels, distribution |
| **Ledger** | Finance + Ops | Budgets, runway, pricing models, unit economics, operating cadence |
| **Sentinel** | Legal / Risk / Compliance | Legal, risk, compliance, security issue spotting and mitigations |

---

## How it works

Each agent is a separate Docker Compose service running Hermes Agent. The container layout follows the Hermes Docker convention:

```text
host directory                 container path
agents/<agent>/home      ->    /opt/data
agents/<agent>/workspace ->    /workspace
shared/project           ->    /shared/project:ro
shared/skills            ->    /shared/skills:ro
shared/mcp               ->    /shared/mcp:ro
```

- `/opt/data` is the agent's durable Hermes home: `config.yaml`, `.env`, auth state, sessions, skills, memory, and logs.
- `/workspace` is the agent's private working directory for notes, deliverables, prototypes, and generated artifacts.
- `/shared/project`, `/shared/skills`, and `/shared/mcp` are read-only team context mounted into every agent.

Every agent config sets terminal work to `/workspace` by default:

```yaml
terminal:
  backend: local
  cwd: /workspace
```

---

## Repository layout

```text
team-nexus/
  docker-compose.yml
  Makefile
  README.md
  .gitignore

  .docs/
    image/                         # team portraits
      atlas.jpeg
      vega.jpeg
      scout.jpeg
      forge.jpeg
      lumen.jpeg
      blitz.jpeg
      ledger.jpeg
      sentinel.jpeg

  docker/
    Dockerfile
    .dockerignore
    mise/
      config.toml                  # global tools baked into the image

  scripts/
    setup-agent.sh                 # setup one agent
    doctor-all.sh                  # doctor every agent

  shared/
    project/                       # shared project context, mounted read-only
    skills/                        # shared team-wide skills, mounted read-only
    mcp/                           # shared MCP registry/templates/docs

  agents/
    atlas/
      README.md
      home/                        # mounted as /opt/data
        config.yaml
        .env.example
        persona.md
        skills/
        sessions/
        logs/
        memory/
        mcp/
      workspace/                   # mounted as /workspace
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

## Custom Docker image

The Compose stack builds a local image:

```text
team-nexus-agent:latest
```

from `docker/Dockerfile`. It extends `nousresearch/hermes-agent:latest` and adds common runtime support for agent workspaces and MCP servers:

- `mise`
- `node@lts`, `npm`, `npx`
- `uv`, `uvx`
- `jq`, `ripgrep`, `git`
- `openssh-client`
- `zip` / `unzip`

Global mise config lives at `docker/mise/config.toml`:

```toml
[tools]
node = "lts"
uv = "latest"
```

Each agent also has an editable workspace-level mise file:

```text
agents/<agent>/workspace/.mise.toml
```

Use that file to add agent-specific tools like Python, Go, Rust, Bun, or pnpm.

---

## Quick start

From this directory:

```bash
cd /Users/sage/team-nexus
```

Build the image:

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
| Atlas | <http://127.0.0.1:8642> |
| Vega | <http://127.0.0.1:8643> |
| Scout | <http://127.0.0.1:8644> |
| Forge | <http://127.0.0.1:8645> |
| Lumen | <http://127.0.0.1:8646> |
| Blitz | <http://127.0.0.1:8647> |
| Ledger | <http://127.0.0.1:8648> |
| Sentinel | <http://127.0.0.1:8649> |

If you only use Discord, Telegram, Slack, or another messaging gateway, exposing API ports is optional. Keep them localhost-bound unless you intentionally need external access.

---

## Agent-to-agent messaging model

Team Nexus is set up so every agent can run as a gateway with its own identity. There are three practical coordination patterns:

1. **Human-mediated chat** — Sage talks to Atlas in Discord or another gateway. Atlas summarizes, delegates, and asks specialists through their configured gateway channels.
2. **Gateway API calls** — Atlas or a helper MCP/server can send tasks to specialist gateway API endpoints on localhost, then collect the responses.
3. **Workspace handoff** — Agents write briefs to `workspace/inbox/` and finished deliverables to `workspace/outbox/`, with Atlas responsible for synthesis.

Recommended operating rule: specialists write durable deliverables to `outbox/`, not only chat responses.

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
- OAuth and credential-pool state should remain in the mounted `home/`, not baked into the image.

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

## Personas

Each agent has an editable persona file:

```text
agents/<agent>/home/persona.md
```

Each `config.yaml` includes metadata pointing at:

```yaml
startup_agent:
  persona_file: /opt/data/persona.md
```

If the Hermes runtime does not automatically consume that file, wire it in by copying it into the runtime persona path, converting it into a preload skill, or using a small gateway/router wrapper that injects it at session start.

---

## Shared context

Use `shared/project/` for company-wide or project-wide files all agents can read:

- company brief
- product strategy
- customer notes
- architecture docs
- brand voice
- decision logs exported by Atlas

Because it is read-only inside containers, agents cannot accidentally corrupt shared source-of-truth files.

---

## Skills

Per-agent editable Hermes skills live in:

```text
agents/<agent>/home/skills/
```

Shared read-only skill source lives in:

```text
shared/skills/
```

The model is intentionally simple:

```text
shared skill  -> shared/skills/<category>/<skill>
agent skill   -> agents/<agent>/home/skills/<skill>
```

No sync target is required: if a skill is shared, place it under `shared/skills`; if it belongs only to one agent, place it in that agent's skill folder.

Inspect skills inside an agent container:

```bash
docker compose run --rm atlas skills list
docker compose run --rm atlas skills browse
```

Tool or skill changes may require a new Hermes session or gateway restart.

---

## MCP

Hermes native MCP servers are configured per agent under that agent's mounted home/config. Shared server definitions and reusable docs live under:

```text
shared/mcp/
  registry/    # Makefile-compatible server definitions
  templates/   # YAML examples/snippets for config.yaml
  scripts/     # optional sync/helper scripts
  docs/        # server-specific setup notes
```

Use Makefile targets from the repo root to avoid typing long `docker compose run` commands.

List templates:

```bash
make mcp-templates
```

Register a shared template for one agent:

```bash
make mcp-register-template AGENT=atlas SERVER=time
make mcp-register-template AGENT=forge SERVER=filesystem-workspace
```

Register for multiple agents:

```bash
make mcp-register-template-all SERVER=filesystem-workspace TARGET_AGENTS="atlas forge"
```

Register ad-hoc MCP servers:

```bash
make mcp-add-command \
  AGENT=forge \
  SERVER=filesystem \
  COMMAND='npx -y @modelcontextprotocol/server-filesystem /workspace'

make mcp-add-url \
  AGENT=atlas \
  SERVER=company-api \
  URL='https://mcp.example.com/mcp'
```

List, test, or remove servers:

```bash
make mcp-list AGENT=atlas
make mcp-list-all
make mcp-test AGENT=atlas SERVER=time
make mcp-remove AGENT=atlas SERVER=time
```

Do **not** commit secrets into `shared/mcp/registry/*.mk`. Keep tokens in `agents/<agent>/home/.env`, OAuth state, or another local secret store.

---

## Common commands

```bash
make help                         # show Makefile targets
make build                        # docker compose build
make up                           # start all gateways
make down                         # stop all gateways
make ps                           # show service status
make logs AGENT=atlas             # follow one agent's logs
make shell AGENT=forge            # open bash in one agent container
make doctor AGENT=atlas           # run hermes doctor for one agent
make doctor-all                   # run hermes doctor for every agent
make compose-config               # validate docker-compose.yml
```

One-off Hermes commands:

```bash
docker compose run --rm atlas status --all
docker compose run --rm forge doctor
```

Verify runtime tools:

```bash
docker compose run --rm --entrypoint mise atlas --version
docker compose run --rm --entrypoint node atlas --version
docker compose run --rm --entrypoint uv atlas --version
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

### Config/persona changes do not take effect

Restart the relevant gateway:

```bash
docker compose restart <agent>
```

or start a fresh Hermes session if the change affects tools, skills, or persona context.
