"""The notify-human MCP server: one tool, `send`, plus startup instructions.

At process start the instructions are resolved (file -> hosted URL -> built-in
default) and handed to the server as its `instructions` field. The MCP client
injects that text into the LLM's system prompt every session, which is what makes
the notification format standardize-able by editing one file. The LLM receives
text only — never a path or a URL.
"""

from __future__ import annotations

import sys

from . import config, discord

# mcp >= 2 renamed FastMCP to MCPServer; keep working on both major versions.
try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer

try:
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover - mcp 1.x path
    try:
        from mcp.server.fastmcp.exceptions import ToolError
    except ImportError:

        class ToolError(Exception):
            """Fallback used when the installed SDK exposes no ToolError."""


SERVER_NAME = "notify-human"

SEND_DESCRIPTION = (
    "Send one notification to the human's Discord whenever their attention is "
    "needed: you are blocked, need a decision or missing info, have a question or "
    "warning about the current task, something important happened mid-task, you "
    "finished, or the user asked to be pinged. One message per event — do not spam "
    "the user. Keep it short: plain messages truncate at 2000 characters, embeds at "
    "4096. Set embed=True for a rich card instead of plain markdown."
)


def build_server(instructions=None, webhook_url=None):
    """Build the MCP server.

    `instructions` is the standing text for the LLM (None -> config default).
    `webhook_url` overrides the environment; tests pass a fake local URL.
    """
    server = MCPServer(
        name=SERVER_NAME,
        instructions=instructions
        if instructions is not None
        else config.DEFAULT_INSTRUCTIONS,
    )
    url = webhook_url if webhook_url is not None else config.get_webhook_url()

    @server.tool(description=SEND_DESCRIPTION)
    def send(message: str, embed: bool = False) -> str:
        """Post `message` to the configured Discord webhook."""
        if not url:
            raise ToolError(
                "notify-human is not configured: set NOTIFY_HUMAN_WEBHOOK_URL in "
                "this server's environment. Nothing was sent."
            )
        if not message or not message.strip():
            raise ToolError("send needs a non-empty message. Nothing was sent.")

        if embed:
            payload = discord.build_embed_payload(message)
            sent_len = len(payload["embeds"][0]["description"])
            limit = discord.EMBED_DESCRIPTION_MAX
        else:
            payload = discord.build_plain_payload(message)
            sent_len = len(payload["content"])
            limit = discord.DISCORD_MAX_CONTENT

        ok, detail = discord.send_to_webhook(url, payload)
        if not ok:
            raise ToolError(f"notify-human could not post to Discord ({detail}).")

        note = ""
        if sent_len < len(message):
            note = f" (truncated from {len(message)} chars at the {limit} limit)"
        return f"sent {sent_len} chars to Discord (embed={embed}){note}"

    return server


def _run_stdio(server):
    """Block serving MCP over stdio. Split out so tests can stub it."""
    server.run(transport="stdio")


_last_server = None


def main():
    """Console entry point: `notify-human-mcp`."""
    global _last_server
    instructions, source = config.load_instructions()
    print(
        f"notify-human: instructions from {source} "
        f"({len(instructions)} chars), webhook "
        f"{'set' if config.get_webhook_url() else 'NOT SET'}",
        file=sys.stderr,
    )
    _last_server = build_server(instructions=instructions)
    _run_stdio(_last_server)


if __name__ == "__main__":
    main()
