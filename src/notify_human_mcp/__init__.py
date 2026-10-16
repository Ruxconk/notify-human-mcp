"""notify-human MCP server package."""

__version__ = "0.1.0"

#: Sent as the User-Agent on every outbound request (webhook POST and any
#: hosted instructions fetch). Defined once here so both modules agree.
USER_AGENT = f"notify-human-mcp/{__version__}"
