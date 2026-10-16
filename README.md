# notify-human-mcp

An [MCP](https://modelcontextprotocol.io) server that gives your LLM one job: ping
your Discord when it finishes work — in a **standardized format you control from a
file**, not from each model's habits.

The server reads your instructions file at every client launch and hands the text to
the MCP client as its `instructions` field. The client injects it into the LLM's
system prompt each session — the same effect as AGENTS.md, per tool. Edit the file,
and the next session on that machine uses the new format. The LLM never sees the file
path or URL, only the text.

One tool is exposed:

| Tool | Args | Behaviour |
|---|---|---|
| `send` | `message: str` (required), `embed: bool = False` | Posts to your Discord webhook. `embed=False` → markdown text (truncated at 2000 chars with a `... (truncated)` note); `embed=True` → rich embed card (4096-char limit). Returns a short status string. |

If no webhook URL is configured, `send` fails with a clear error and posts nothing.

## Install

Requires [uv](https://docs.astral.sh/uv/). No install step needed — `uvx` fetches and
runs it:

```bash
uvx notify-human-mcp
```

## Per-machine setup

Add one block to your MCP client's config (Claude Desktop, Codex CLI, etc.):

```json
"notify-human": {
  "command": "uvx",
  "args": ["notify-human-mcp"],
  "env": {
    "NOTIFY_HUMAN_WEBHOOK_URL": "https://discord.com/api/webhooks/…",
    "NOTIFY_HUMAN_INSTRUCTIONS_FILE": "/path/to/your-instructions.md"
  }
}
```

| Env var | Required | Meaning |
|---|---|---|
| `NOTIFY_HUMAN_WEBHOOK_URL` | yes | Your Discord webhook URL. Each machine/user gets its own. |
| `NOTIFY_HUMAN_INSTRUCTIONS_FILE` | no | Local instructions file (primary source). |
| `NOTIFY_HUMAN_INSTRUCTIONS_URL` | no | Hosted instructions URL (secondary; fetched at startup). |

Instructions are resolved in order: **file → URL → built-in default**. A missing file
or failed fetch falls through silently — the server always starts.

Restart the client after editing the file; the server re-reads it on every launch.

### Writing the instructions file

This file is the format control. Example:

```markdown
Use the `send` tool exactly once at the end of every task.
Format: one-line status (done / blocked / needs input), then a short summary of
what changed, then next steps. Keep it under 1000 characters. No raw logs.
```

Point several machines at the same file contents (or the same hosted URL) to get one
format everywhere; give a machine its own file to diverge.

**Trust note:** a hosted instructions URL is a control point — whoever can edit that
URL controls what every connected LLM is told. Keep it private and writeable only by
you.

## Development

```bash
uv sync                          # env + dev deps
uv run pytest -q                 # 57 tests, HTTP fully mocked, zero real sockets
uv build                         # sdist + wheel into dist/
```

## Publishing (prepared — not yet run)

First, create a PyPI account and (recommended) an API token scoped to the project.
Then:

```bash
uv build                            # dist/notify_human_mcp-<ver>.tar.gz + .whl
uv publish                          # or: pipx run twine upload dist/*
```

Bump `version` in `pyproject.toml` for each release.

**Optional, later:** list the package in the public [MCP
Registry](https://modelcontextprotocol.io/registry) so others can discover it. The
registry is still in preview, stores metadata only, and verifies repo ownership — a
discovery nicety, never needed for your own machines.

## License

MIT — see [LICENSE](LICENSE).
