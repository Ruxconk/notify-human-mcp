"""The notify-human MCP server: one tool, `send`, plus startup instructions.

At process start the instructions are resolved (file -> hosted URL -> built-in
default) and handed to the server as its `instructions` field. The MCP client
injects that text into the LLM's system prompt at session start — but it lives
in the conversation history and dies on context compaction. The tool description
is re-delivered with every request, so when the instructions came from a file,
the description also carries that path with a conditional hint: read it only
if the rules are not already in context. One file read per compaction cycle,
not every turn. With no file (URL/default source) the description's own short
hard rules are the fallback.
"""

from __future__ import annotations

import os
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
    "the user. Keep it under 1000 characters: status line first, short bullets, "
    "the ask last. Messages over 2000 characters (plain) or 4096 (embed) are "
    "rejected, not truncated — shorten before sending. "
    "Set embed=True for a rich card instead of plain markdown."
)

#: Appended only when the instructions came from a local file. Conditional on
#: purpose: the LLM must not re-read the file every turn, only after the rules
#: left its context (compaction).
INSTRUCTIONS_PATH_HINT = (
    " If standing format rules are not already in your context, read {path} "
    "and follow them exactly."
)


TEMPLATE_SEND_DESCRIPTION = (
    "Send one notification to the human's Discord whenever their attention is "
    "needed: you are blocked, need a decision or missing info, have a warning, "
    "something important happened mid-task, you finished, or the user asked to "
    "be pinged. One message per event. Do not format the message yourself: "
    "pass the named fields and the server assembles it from a fixed template. "
    "`status` must be one of the statuses named in the instructions; `title` "
    "is one short headline line; `body` is short bullets, no raw logs; "
    "`ticket` is the tracker id if the work has one. Over-long messages are "
    "rejected with the limit named — shorten and retry; nothing is posted."
)


def build_server(
    instructions=None,
    webhook_url=None,
    instructions_path=None,
    template=None,
):
    """Build the MCP server.

    `instructions` is the standing text for the LLM (None -> config default).
    `webhook_url` overrides the environment; tests pass a fake local URL.
    `instructions_path` is the file the instructions came from; when set, the
    tool description tells the LLM where to re-read them after compaction.
    `template` switches to template mode: `send` takes named fields and the
    message is assembled by the server, so the format cannot drift.
    """
    server = MCPServer(
        name=SERVER_NAME,
        instructions=instructions
        if instructions is not None
        else config.DEFAULT_INSTRUCTIONS,
    )
    url = webhook_url if webhook_url is not None else config.get_webhook_url()

    if template is not None:
        _register_template_send(server, url, template)
        return server

    description = SEND_DESCRIPTION
    if instructions_path:
        description += INSTRUCTIONS_PATH_HINT.format(path=instructions_path)

    @server.tool(description=description)
    def send(message: str, embed: bool = False) -> str:
        """Post `message` to the configured Discord webhook."""
        if not url:
            raise ToolError(
                "notify-human is not configured: set NOTIFY_HUMAN_WEBHOOK_URL in "
                "this server's environment. Nothing was sent."
            )
        if not message or not message.strip():
            raise ToolError("send needs a non-empty message. Nothing was sent.")

        limit = discord.EMBED_DESCRIPTION_MAX if embed else discord.DISCORD_MAX_CONTENT
        if len(message) > limit:
            raise ToolError(
                f"message is {len(message)} chars, over the {limit}-char limit "
                f"for {'embed' if embed else 'plain'} messages. Shorten it and "
                "send again; nothing was posted."
            )

        if embed:
            payload = discord.build_embed_payload(message)
        else:
            payload = discord.build_plain_payload(message)
        sent_len = len(message)

        ok, detail = discord.send_to_webhook(url, payload)
        if not ok:
            raise ToolError(f"notify-human could not post to Discord ({detail}).")
        return f"sent {sent_len} chars to Discord (embed={embed})"

    return server


def _register_template_send(server, url, tmpl):
    """Register the template-mode `send`: named fields in, rendered text out."""
    from . import template as template_mod

    status_values = ", ".join(sorted(tmpl["statuses"]))

    @server.tool(description=TEMPLATE_SEND_DESCRIPTION)
    def send(
        status: str,
        title: str,
        body: str,
        ticket: str = "",
        model: str = "",
    ) -> str:
        """Assemble a notification from the template and post it."""
        if not url:
            raise ToolError(
                "notify-human is not configured: set NOTIFY_HUMAN_WEBHOOK_URL in "
                "this server's environment. Nothing was sent."
            )
        try:
            message = template_mod.render_message(
                tmpl,
                status=status,
                title=title,
                body=body,
                ticket=ticket or None,
                model=model or None,
            )
        except template_mod.TemplateError as e:
            raise ToolError(f"{e} Nothing was posted. (statuses: {status_values})")

        payload = discord.build_plain_payload(message)
        ok, detail = discord.send_to_webhook(url, payload)
        if not ok:
            raise ToolError(f"notify-human could not post to Discord ({detail}).")
        return f"sent {len(message)} chars to Discord (template status={status})"


def _run_stdio(server):
    """Block serving MCP over stdio. Split out so tests can stub it."""
    server.run(transport="stdio")


_last_server = None


def main():
    """Console entry point: `notify-human-mcp`."""
    global _last_server
    res = config.resolve_instructions()
    if res.error:
        print(f"notify-human: WARNING {res.error}", file=sys.stderr)
    print(
        f"notify-human: mode={res.mode} instructions from {res.source} "
        f"({len(res.text)} chars), webhook "
        f"{'set' if config.get_webhook_url() else 'NOT SET'}",
        file=sys.stderr,
    )
    instructions_path = (
        (os.environ.get(config.INSTRUCTIONS_FILE_ENV) or "").strip()
        if res.mode == "prose" and res.source == "file"
        else ""
    )
    _last_server = build_server(
        instructions=res.text,
        instructions_path=instructions_path or None,
        template=res.template,
    )
    _run_stdio(_last_server)


if __name__ == "__main__":
    main()
