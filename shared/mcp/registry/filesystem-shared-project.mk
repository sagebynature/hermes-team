# Example readonly project filesystem MCP server scoped to shared project context.
# Usage: make mcp-register-template AGENT=atlas SERVER=filesystem-shared-project
MCP_TRANSPORT := command
MCP_COMMAND := npx -y @modelcontextprotocol/server-filesystem /shared/project
