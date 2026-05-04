# Architecture Decision Records

Team Nexus decisions are recorded here as ADRs.

## Index

- [ADR-0001: Run one Docker Compose service per Hermes agent](0001-one-compose-service-per-agent.md)
- [ADR-0002: Keep shared project context read-only and agent workspaces isolated](0002-isolated-workspaces-shared-readonly-context.md)
- [ADR-0003: Use Atlas as the default coordinator and synthesizer](0003-atlas-default-coordinator.md)
- [ADR-0004: Use Discord as the human mission room, not the source of truth](0004-discord-human-mission-room.md)
- [ADR-0005: Use Hermes Kanban as the durable collaboration source of truth](0005-kanban-source-of-truth.md)
- [ADR-0006: Use a Compose-aware Kanban dispatcher instead of embedded Hermes profile dispatch](0006-compose-aware-kanban-dispatcher.md)
- [ADR-0007: Keep automatic dispatch explicit rather than hidden inside startup](0007-explicit-dispatcher-startup.md)
- [ADR-0008: Load shared secrets from the repo-root .env](0008-shared-repo-root-env.md)
- [ADR-0009: Use shared read-only skills and MCP registries with agent-local extensions](0009-shared-readonly-skills-and-mcp.md)
- [ADR-0010: Mirror only compact status and handoffs to Discord](0010-compact-discord-status-and-handoffs.md)

## ADR format

Each ADR uses:

- Status
- Context
- Decision
- Consequences
- Implementation notes
