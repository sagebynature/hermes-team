# Shared MCP server registry

This directory is the team-wide source of truth for MCP server definitions and helper material.

- `registry/*.mk` — Makefile-compatible server definitions used by `make mcp-register-template`.
- `templates/*.yaml` — YAML snippets showing the native Hermes `mcp_servers` shape.
- `scripts/` — optional helper scripts for more advanced sync/templating.
- `docs/` — notes for server-specific setup and required credentials.

Do not commit secrets here. Keep tokens in `agents/<agent>/home/.env` or in the agent's local Hermes auth state.
