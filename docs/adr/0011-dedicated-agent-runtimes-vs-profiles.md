# ADR-0011: Treat dedicated agent runtimes as Team Nexus mode, not the default lightweight pattern

Status: Accepted

Date: 2026-05-05

## Context

Team Nexus currently runs each specialist as a dedicated Hermes Agent runtime: one Docker Compose service, one mounted Hermes home, one workspace, one gateway process, one log/auth/session/memory boundary, and one optional dashboard per agent.

This differs from the lighter Hermes pattern of running multiple named profiles inside a single Hermes runtime/home. The profile model is simpler and maps more directly to Hermes' built-in profile-oriented features, including embedded Kanban dispatch assumptions. The dedicated-runtime model is heavier and has already required Team Nexus-specific operating machinery, most notably a Compose-aware Kanban dispatcher.

The architectural question is whether Team Nexus should keep the dedicated runtime model or collapse to one runtime with multiple profiles.

## Decision

Keep the dedicated runtime model for Team Nexus.

Team Nexus is intentionally a multi-agent operations environment, not just a set of alternate personas. Each agent should continue to have:

```text
agents/<agent>/home      -> /opt/data
agents/<agent>/workspace -> /workspace
```

Each long-running specialist gateway should continue to run as its own Docker Compose service. Atlas remains the default coordinator, while specialists operate in isolated lanes and exchange durable work through shared Kanban plus explicit artifact handoffs.

However, document this as **Team Nexus mode** rather than the default recommendation for all Hermes multi-agent use.

The lightweight alternative remains valid:

- Use one Hermes runtime with multiple profiles when agents are mostly role prompts/personas.
- Use Team Nexus dedicated runtimes when agents need independent gateways, workspaces, sessions, memories, logs, auth state, dashboards, restart lifecycles, or operational isolation.

## Consequences

Positive:

- Agent state is strongly separated: config, sessions, memory, auth files, skills, logs, and gateway runtime files live under the agent's own mounted home.
- Agent work is easier to inspect, reset, archive, or delete independently.
- Compose service names match the mental model of a virtual team: `atlas`, `vega`, `scout`, `forge`, `lumen`, `blitz`, `ledger`, and `sentinel`.
- Gateways can be started, stopped, logged, restarted, and health-checked independently.
- Specialist workspaces provide a safer boundary for terminal/file tool use than shared profile execution in one workspace.
- The architecture can support different gateway identities, credentials, dashboards, and runtime policies per agent if needed later.

Tradeoffs:

- This is more complex than Hermes profiles in a single runtime.
- Built-in profile-oriented Hermes orchestration does not map directly to the runtime model.
- Team Nexus needs project-specific glue such as `scripts/kanban-compose-dispatcher.py` and `shared/team-agents.yaml`.
- The dispatcher requires Docker-outside-of-Docker access through the host Docker socket, which is powerful and security-sensitive.
- Compose, dashboard, nginx, and config duplication can accumulate quickly if not managed.
- A shared repo-root `.env` means runtime isolation does not automatically imply secret isolation; all agents currently receive the same shared environment variables unless per-agent env/auth separation is added.

## Critical assessment

The dedicated runtime model is recommended for Team Nexus because the repo's goal is an autonomous startup strike team with independently operating specialists. It would be overly complex for a simple local assistant setup, but it is proportionate for concurrent gateways and isolated operator lanes.

The main risk is not the core decision. The main risk is letting bespoke platform glue grow faster than operational value. Team Nexus should therefore keep the runtime boundary while reducing duplication and centralizing source-of-truth data.

## Implementation notes

Keep:

- One Docker Compose gateway service per agent.
- One mounted Hermes home per agent.
- One mounted workspace per agent.
- Shared project context mounted read-only, with `/shared/project/artifacts` as the explicit writable handoff submount.
- Shared Kanban as the durable collaboration source of truth.
- Embedded Hermes gateway dispatch disabled for all agents.
- The Compose-aware dispatcher as the single owner of automatic worker spawning.

Simplify:

- Treat `shared/team-agents.yaml` as the registry for agent slug, service name, display name, role, and port metadata.
- Prefer Compose anchors, generated Compose fragments, or validation scripts over hand-maintained duplicated service blocks.
- Add or maintain config validation to check every `agents/*/home/config.yaml` for expected common settings such as:
  - `terminal.cwd: /workspace`
  - `kanban.dispatch_in_gateway: false`
  - expected toolsets
  - expected auxiliary model defaults
  - expected dashboard identity fields
  - expected security/privacy settings
- Keep dashboards, nginx, and automatic dispatch behind explicit Compose profiles so the minimal stack remains understandable.
- Add per-agent env files or credential separation only when the team needs true secret isolation; do not assume separate containers alone solve shared-key exposure.

Use profiles instead of dedicated runtimes when:

- The agents are mostly alternate personalities or role prompts.
- Only one gateway/orchestrator is needed.
- Independent workspaces, auth state, logs, memory, dashboards, and restart lifecycles are not required.
- Native Hermes profile-oriented dispatch is more valuable than Docker-level isolation.
