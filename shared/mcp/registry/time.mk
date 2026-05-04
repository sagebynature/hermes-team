# Example stdio MCP server using uvx.
# Usage: make mcp-register-template AGENT=atlas SERVER=time
MCP_TRANSPORT := command
MCP_COMMAND := uvx mcp-server-time
