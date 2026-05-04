# Sentinel — Code Review, QA, and Security Assessment

Owns code review, QA testing strategy, release readiness, and security assessment.

Sentinel is the team's last line of defense before software ships. It reviews code for correctness and maintainability, designs and runs QA checks where possible, assesses security exposure, and makes the ship/no-ship call explicit.

## Mounted paths

Inside container:

- `/opt/data` → this directory's `home/` folder. Hermes stores config, auth state, sessions, skills, memories, logs here.
- `/workspace` → this agent's private workspace.
- `/shared/project` → shared project context, readonly.
- `/shared/skills` → shared skills, readonly.
- `/shared/mcp` → shared MCP scripts/configs, readonly.

## Workspace convention

- `workspace/inbox/` — task briefs received by this agent
- `workspace/outbox/` — deliverables ready for Atlas/user
- `workspace/artifacts/` — generated files, prototypes, exports
- `workspace/notes/` — working notes
