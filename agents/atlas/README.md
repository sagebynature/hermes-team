# Atlas — Orchestrator / Chief of Staff

Routes work, decomposes startup objectives, tracks decisions, and synthesizes specialist output.

## Mounted paths

Inside container:

- `/opt/data` → this directory's `home/` folder. Hermes stores config, API keys, sessions, skills, memories, logs here.
- `/workspace` → this agent's private workspace.
- `/shared/project` → shared project context, readonly.
- `/shared/skills` → shared skills, readonly.
- `/shared/mcp` → shared MCP scripts/configs, readonly.

## Workspace convention

- `workspace/inbox/` — task briefs received by this agent
- `workspace/outbox/` — deliverables ready for Atlas/Sage
- `workspace/artifacts/` — generated files, prototypes, exports
- `workspace/notes/` — working notes
