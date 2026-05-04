# ADR-0001: Run one Docker Compose service per Hermes agent

Status: Accepted

Date: 2026-05-04

## Context

Team Nexus needs multiple named agents with different roles, memories, sessions, skills, logs, workspaces, and gateway identities. A single Hermes home with many profiles would be simpler to launch, but it would couple agent state and make filesystem, credential, and gateway isolation weaker.

## Decision

Run each specialist as its own Docker Compose service using the shared `team-nexus-agent:latest` image.

Each service gets a dedicated mounted Hermes home:

```text
agents/<agent>/home -> /opt/data
```

and a dedicated workspace:

```text
agents/<agent>/workspace -> /workspace
```

## Consequences

Positive:

- Agents have isolated config, memory, sessions, logs, skills, and auth state.
- Gateways can run independently.
- Specialist workspaces are easier to inspect and reset.
- Container boundaries match the mental model of a virtual team.

Tradeoffs:

- Built-in profile-oriented orchestration does not map directly to the runtime model.
- Cross-agent collaboration needs an explicit shared coordination layer.
- Operational commands must target Compose services, not local profiles.

## Implementation notes

- Compose services are named after agent slugs: `atlas`, `vega`, `scout`, `forge`, `lumen`, `blitz`, `ledger`, `sentinel`.
- The `shared/team-agents.yaml` registry maps Kanban assignees to Compose services.
- Only Atlas has the Compose `build:` stanza to avoid building the same image eight times.

