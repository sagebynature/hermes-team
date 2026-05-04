# Team Nexus

**An autonomous startup strike team, containerized and ready to deploy.**

Team Nexus turns Hermes Agent into a serious multi-agent command center. Each specialist runs as its own Hermes gateway with its own home, workspace, memory, credentials, sessions, skills, and logs. Atlas coordinates the mission. Specialists execute. Shared context keeps everyone reading from the same brief without letting any one agent corrupt the source of truth.

This is not a toy swarm. It is an A-Team in a repo.

```text
User -> Atlas -> specialists -> Atlas -> User
```

---

## The Squad

<table>
  <tr>
    <td align="center" width="25%"><img src=".docs/image/atlas.jpeg" alt="Atlas portrait" width="140"><br><strong>Atlas</strong><br><em>Orchestrator</em></td>
    <td align="center" width="25%"><img src=".docs/image/vega.jpeg" alt="Vega portrait" width="140"><br><strong>Vega</strong><br><em>Product lead</em></td>
    <td align="center" width="25%"><img src=".docs/image/scout.jpeg" alt="Scout portrait" width="140"><br><strong>Scout</strong><br><em>Market recon</em></td>
    <td align="center" width="25%"><img src=".docs/image/forge.jpeg" alt="Forge portrait" width="140"><br><strong>Forge</strong><br><em>Engineering lead</em></td>
  </tr>
  <tr>
    <td align="center" width="25%"><img src=".docs/image/lumen.jpeg" alt="Lumen portrait" width="140"><br><strong>Lumen</strong><br><em>UX and design</em></td>
    <td align="center" width="25%"><img src=".docs/image/blitz.jpeg" alt="Blitz portrait" width="140"><br><strong>Blitz</strong><br><em>Growth and GTM</em></td>
    <td align="center" width="25%"><img src=".docs/image/ledger.jpeg" alt="Ledger portrait" width="140"><br><strong>Ledger</strong><br><em>Finance and ops</em></td>
    <td align="center" width="25%"><img src=".docs/image/sentinel.jpeg" alt="Sentinel portrait" width="140"><br><strong>Sentinel</strong><br><em>Code review, QA, and security</em></td>
  </tr>
</table>

| Agent        | Callsign                      | Mission                                                                                        | Persona                                                                                                                        |
| ------------ | ----------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Atlas**    | Mission commander             | Decomposes objectives, routes work, tracks decisions, synthesizes the final answer             | Calm under pressure. Decisive without ego. The one who makes the call when the room gets loud.                                 |
| **Vega**     | Product strategist            | Sharpens ICP, MVP scope, PRDs, roadmap, positioning, and prioritization                        | Elegant, intense, allergic to vague product thinking. Cuts scope like a blade, but only to protect the product.                |
| **Scout**    | Market recon                  | Maps competitors, customers, categories, pricing, and weak signals                             | Curious, skeptical, and quietly relentless. Trusts evidence over vibes and is comfortable saying "unknown."                    |
| **Forge**    | Engineering lead              | Designs systems, builds prototypes, makes technical tradeoffs, ships working code              | Serious, blunt, and straight to the point. Does not crack jokes. Warm heart deep inside, mostly expressed as reliable systems. |
| **Lumen**    | UX and design                 | Shapes flows, screens, onboarding, interface structure, critique, and copy                     | Warm, perceptive, and exacting. Gentle with people, ruthless with confusing interfaces.                                        |
| **Blitz**    | Growth and GTM                | Builds launch plans, acquisition loops, messaging, funnels, and distribution plays             | Fast, bold, and tactical. Brings momentum without tolerating spam, vanity metrics, or growth theater.                          |
| **Ledger**   | Finance and ops               | Models runway, pricing, unit economics, operating cadence, and resource allocation             | Precise, conservative, and unflappable. Makes ambition measurable and survivable.                                              |
| **Sentinel** | Code review, QA, and security | Reviews code, designs QA coverage, assesses security exposure, and makes the ship/no-ship call | Watchful, exact, and hard to impress. Thinks like a senior reviewer, a QA lead, and an attacker at the same time.              |

---

## Operating doctrine

Team Nexus gives each agent a clean lane and a hard boundary.

- Every specialist has a private Hermes home under `agents/<agent>/home`.
- Every specialist has a private workspace under `agents/<agent>/workspace`.
- Shared project files, skills, and MCP material are mounted read-only.
- Secrets stay out of the image and out of git.
- Atlas is the default point of coordination, so specialist output gets synthesized instead of scattered.

The result is simple: autonomous agents with their own identity, their own tools, and a common operating picture.

---

## Runtime map

Each agent is a separate Docker Compose service running Hermes Agent. The container layout follows the Hermes Docker convention:

```text
host directory                 container path
agents/<agent>/home      ->    /opt/data
agents/<agent>/workspace ->    /workspace
shared/project           ->    /shared/project:ro
shared/skills            ->    /shared/skills:ro
shared/mcp               ->    /shared/mcp:ro
```

Inside the container:

| Path              | Purpose                                                                                |
| ----------------- | -------------------------------------------------------------------------------------- |
| `/opt/data`       | Durable Hermes home: `config.yaml`, `.env`, auth state, sessions, skills, memory, logs |
| `/workspace`      | Agent-owned working area for notes, prototypes, deliverables, and artifacts            |
| `/shared/project` | Read-only mission brief and project context                                            |
| `/shared/skills`  | Read-only team skill library                                                           |
| `/shared/mcp`     | Read-only MCP registry, templates, scripts, and docs                                   |

Every agent runs terminal tools from `/workspace` by default:

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

  .env.example                    # template for the shared repo-root .env

  agents/
    atlas/
      README.md
      home/                        # mounted as /opt/data
        config.yaml
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

## The field kit

The Compose stack builds one local image for the team:

```text
team-nexus-agent:latest
```

It is built from `docker/Dockerfile`, extends `nousresearch/hermes-agent:latest`, and adds the tools agents need to work like operators instead of chat windows:

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

Each agent can carry extra gear in its own workspace-level mise file:

```text
agents/<agent>/workspace/.mise.toml
```

Use it for specialist tools: Python for research and finance, Go or Rust for systems work, Bun or pnpm for frontend work, or anything else the mission calls for.

---

## Deployment sequence

Start from the repo root:

```bash
cd /Users/sage/team-nexus
```

Build the shared team image once:

```bash
make build
```

All services use `team-nexus-agent:latest`; only Atlas carries the Compose `build:` stanza so the image is not built eight times in parallel.

Bring Atlas online first with the helper script:

```bash
./scripts/setup-agent.sh atlas
```

The helper runs a non-interactive doctor check against the committed baseline config. It does not invoke Hermes' interactive setup wizard from scripts; put real secrets in the shared repo-root `.env` first, and run gateway setup manually from a TTY only when you need to change platform credentials:

```bash
docker compose run --rm atlas gateway setup
```

Then activate whichever specialists you want in the field:

```bash
./scripts/setup-agent.sh vega
./scripts/setup-agent.sh scout
./scripts/setup-agent.sh forge
./scripts/setup-agent.sh lumen
./scripts/setup-agent.sh blitz
./scripts/setup-agent.sh ledger
./scripts/setup-agent.sh sentinel
```

Launch all gateways:

```bash
docker compose up -d
```

Watch Atlas:

```bash
docker compose logs -f atlas
```

Run a full team health check:

```bash
./scripts/doctor-all.sh
```

On a fresh clone, the image entrypoint bootstraps each mounted agent home before doctor runs: it creates the Hermes command symlink and a minimal Skills Hub lock file. Doctor may still report missing optional API keys for full tool access (`EXA_API_KEY`, `TAVILY_API_KEY`, `TINKER_API_KEY`, `WANDB_API_KEY`, etc.); those are intentionally left blank in the shared `.env.example` because they are secrets.

---

## Gateway ports

Ports are bound to localhost. Keep them that way unless you deliberately want external access.

| Agent    | URL                     |
| -------- | ----------------------- |
| Atlas    | <http://127.0.0.1:8642> |
| Vega     | <http://127.0.0.1:8643> |
| Scout    | <http://127.0.0.1:8644> |
| Forge    | <http://127.0.0.1:8645> |
| Lumen    | <http://127.0.0.1:8646> |
| Blitz    | <http://127.0.0.1:8647> |
| Ledger   | <http://127.0.0.1:8648> |
| Sentinel | <http://127.0.0.1:8649> |

If the team operates through Discord, Telegram, Slack, or another gateway, direct API access is optional.

---

## Agent-to-agent comms

Team Nexus supports four coordination paths.

1. **Command channel**
   Sage talks to Atlas in Discord or another gateway. Atlas turns the objective into assignments, routes work to specialists, and returns the synthesis.

2. **Shared Kanban board**
   All agents mount the same writable Kanban root at `/shared/kanban` via `HERMES_KANBAN_HOME`. Use it for durable cross-agent tasks, comments, dependencies, and handoffs:

   ```bash
   make kanban-init
   make kanban-list
   make kanban-stats
   make kanban-create TITLE="research pricing options" ASSIGNEE=atlas
   ```

   Atlas is the only gateway with `kanban.dispatch_in_gateway: true`; the other agents keep dispatch disabled so multiple gateway dispatchers do not race on the same SQLite board. Every agent still has the `kanban` toolset enabled for normal sessions, so agents can inspect, create, comment on, and route shared board tasks.

3. **Gateway API**
   Atlas or a helper service can call specialist gateway endpoints on localhost and collect responses programmatically.

4. **Workspace handoff**
   Agents can pass briefs and artifacts through the workspace convention: `inbox/` for incoming tasks, `outbox/` for finished deliverables.

Operational rule: if a specialist produces something worth keeping, it goes in `outbox/`. Chat is the radio. The workspace is the record.

---

## Secrets and auth

All agents load the same repo-root secrets file through Compose:

```text
.env
```

Start from the shared example:

```bash
cp .env.example .env
```

Common entries:

```bash
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
DISCORD_BOT_TOKEN=
DISCORD_ALLOWED_USERS=
DISCORD_HOME_CHANNEL=
GITHUB_TOKEN=
GATEWAY_API_KEY=
```

Rules of engagement:

- Do not commit the real repo-root `.env` file.
- Every service reads the same `./.env`; use it for shared provider keys and common gateway defaults.
- If an agent needs distinct OAuth, credential-pool, or platform auth state, keep that state in the agent's mounted home, not in the image.
- Prefer separate provider keys or credential pools only when you want clean accounting and revocation; otherwise the shared `.env` keeps bootstrap simple.

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

Each agent has a SOUL.md file:

```text
agents/<agent>/home/SOUL.md
```

Each `config.yaml` includes metadata pointing at it:

```yaml
startup_agent:
  persona_file: /opt/data/SOUL.md
```

If the Hermes runtime does not automatically consume that file, wire it in by copying it into the runtime persona path, converting it into a preload skill, or adding a gateway/router wrapper that injects it at session start.

---

## Shared intelligence

Use `shared/project/` for the material every agent should know before acting:

- company brief
- product strategy
- customer notes
- architecture docs
- brand voice
- Atlas decision logs

The mount is read-only inside containers. Agents can read the brief. They cannot accidentally rewrite the canon.

---

## Skills

Per-agent Hermes skills live here:

```text
agents/<agent>/home/skills/
```

Shared team skills live here:

```text
shared/skills/
```

The rule is deliberately boring:

```text
shared skill  -> shared/skills/<category>/<skill>
agent skill   -> agents/<agent>/home/skills/<skill>
```

If everyone needs it, put it in `shared/skills`. If only Forge, Lumen, Scout, or another specialist needs it, keep it with that agent.

Inspect skills inside an agent container:

```bash
docker compose run --rm atlas skills list
docker compose run --rm atlas skills browse
```

Tool or skill changes may require a new Hermes session or gateway restart.

---

## MCP arsenal

Hermes native MCP servers are configured per agent under that agent's mounted home/config. Shared server definitions and reusable docs live under:

```text
shared/mcp/
  registry/    # Makefile-compatible server definitions
  templates/   # YAML examples/snippets for config.yaml
  scripts/     # optional sync/helper scripts
  docs/        # server-specific setup notes
```

Use Makefile targets from the repo root instead of hand-typing long `docker compose run` commands.

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

Do not commit secrets into `shared/mcp/registry/*.mk`. Keep shared tokens in the repo-root `.env`, and keep agent-specific OAuth state or credential pools in that agent's mounted home.

---

## Command deck

```bash
make help                         # show Makefile targets
make build                        # build shared team-nexus-agent image once
make up                           # start all gateways
make down                         # stop all gateways
make restart                      # restart all gateways
make ps                           # show service status
make logs AGENT=atlas             # follow one agent's logs
make shell AGENT=forge            # open bash in one agent container
make doctor AGENT=atlas           # run hermes doctor for one agent
make doctor-all                   # run hermes doctor for every agent
make compose-config               # validate docker-compose.yml
make kanban-init                  # initialize shared Kanban DB
make kanban-list                  # list shared Kanban tasks
make kanban-stats                 # show shared Kanban counts
make kanban-create TITLE='...' ASSIGNEE=atlas
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

## Security posture

- Keep gateway API ports bound to `127.0.0.1` unless external access is intentional.
- Do not bake secrets into the Docker image.
- Do not mount your whole home directory into agent containers.
- Do not mount `/var/run/docker.sock` unless you intentionally want that agent to control host Docker.
- Use the shared repo-root `.env` for baseline credentials; move high-risk or role-specific auth into agent-local OAuth/credential-pool state where practical.
- Keep `security.redact_secrets: true` in each `config.yaml`.
- Prefer Atlas as the only agent allowed to fan out work to other agents.
- Give agents narrow tool and credential access based on role.

---

## Troubleshooting

### Build fails while installing mise tools

Rebuild without cache:

```bash
docker compose build --no-cache
```

If a specific mise tool fails, remove it from `docker/mise/config.toml` and install it per-agent from `agents/<agent>/workspace/.mise.toml` instead.

### MCP command not found

Check the container:

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

- `DISCORD_BOT_TOKEN` in the shared repo-root `.env`
- Discord Message Content Intent is enabled
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

Start a fresh Hermes session if the change affects tools, skills, or persona context.
