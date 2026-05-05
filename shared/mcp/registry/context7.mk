# Upstash Context7 MCP server.
# Usage: make mcp-register-template AGENT=atlas SERVER=context7
# Requires CONTEXT7_API_KEY in the agent/container environment.
# The escaped dollar keeps ${CONTEXT7_API_KEY} as a literal in registered config.
MCP_TRANSPORT := command
MCP_COMMAND := npx -y @upstash/context7-mcp --api-key \$${CONTEXT7_API_KEY}
