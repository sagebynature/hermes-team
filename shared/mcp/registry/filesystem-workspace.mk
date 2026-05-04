# Example filesystem MCP server scoped to the agent-owned /workspace mount.
# Usage: make mcp-register-template AGENT=forge SERVER=filesystem-workspace
MCP_TRANSPORT := command
MCP_COMMAND := npx -y @modelcontextprotocol/server-filesystem /workspace
