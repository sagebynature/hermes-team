# Shared MCP server registry

This directory is the team-wide source of truth for MCP server definitions and helper material.

- `registry/*.mk` — Makefile-compatible server definitions used by `make mcp-register-template`.
- `templates/*.yaml` — YAML snippets showing the native Hermes `mcp_servers` shape.
- `scripts/` — optional helper scripts for more advanced sync/templating.
- `docs/` — notes for server-specific setup and required credentials.

Do not commit secrets here. Keep shared tokens in the repo-root `.env`, or keep agent-specific auth in that agent's local Hermes auth state.

Available team registry entries:

- `time` — stdio time server via `uvx mcp-server-time`.
- `filesystem-workspace` — stdio filesystem server scoped to `/workspace`.
- `filesystem-shared-project` — stdio filesystem server scoped to `/shared/project`.
- `context7` — Upstash Context7 via `npx -y @upstash/context7-mcp`; requires `CONTEXT7_API_KEY` in `.env`.
- `sequential-thinking` — official sequential-thinking server via `npx -y @modelcontextprotocol/server-sequential-thinking`.
