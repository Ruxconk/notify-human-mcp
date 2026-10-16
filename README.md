# notify-human-mcp

An [MCP](https://modelcontextprotocol.io) server that gives your LLM a way to reach
you on Discord **whenever it needs your attention** — a question it can't answer
itself, a blocker, a decision it needs from you, something worth knowing mid-task, or
work that's finished. Not just an end-of-task bell: a general human-attention channel.
Every message arrives in a **standardized format you control from a file**, not from
each model's habits.

The server reads your instructions file at every client launch and hands the text to
the MCP client as its `instructions` field. The client injects it into the LLM's
system prompt each session — the same effect as AGENTS.md, per tool. Edit the file,
and the next session on that machine uses the new format. That text lives in the
conversation history, so it is summarized away when the conversation is compacted;
the `send` tool description therefore also carries the file path with a conditional
hint to re-read it if the rules are no longer in context.

One tool is exposed:

| Tool | Args | Behaviour |
|---|---|---|
| `send` | prose mode: `message: str` (required), `embed: bool = False` · template mode: `status`, `title`, `body` (required), `ticket`, `model` | Posts to your Discord webhook. Prose: `embed=False` → markdown text, `embed=True` → rich embed card; over the limit (2000 plain / 4096 embed) is **rejected with the limit named**, not truncated. Template: the server assembles the text, so shape errors are rejected with the reason. Returns a short status string. |

If no webhook URL is configured, `send` fails with a clear error and posts nothing.

## Install

Requires [uv](https://docs.astral.sh/uv/). The package is not on PyPI yet, so
install from the repository:

```bash
uvx --from git+https://github.com/Ruxconk/notify-human-mcp.git notify-human-mcp
```

## Per-machine setup

Add one block to your MCP client's config (Claude Desktop, Codex CLI, etc.):

```json
"notify-human": {
  "command": "uvx",
  "args": [
    "--from",
    "git+https://github.com/Ruxconk/notify-human-mcp.git",
    "notify-human-mcp"
  ],
  "env": {
    "NOTIFY_HUMAN_WEBHOOK_URL": "https://discord.com/api/webhooks/…",
    "NOTIFY_HUMAN_INSTRUCTIONS_FILE": "/path/to/your-instructions.md"
  }
}
```

For a local checkout, replace the git URL with the directory path:
`"--from", "/path/to/notify-human-mcp"`.

| Env var | Required | Meaning |
|---|---|---|
| `NOTIFY_HUMAN_WEBHOOK_URL` | yes | Your Discord webhook URL. Each machine/user gets its own. |
| `NOTIFY_HUMAN_INSTRUCTIONS_FILE` | no | Instructions file: `.md`/`.txt` = prose, `.json` = template (see below). |
| `NOTIFY_HUMAN_INSTRUCTIONS_URL` | no | Hosted instructions URL (prose only; fetched at startup). |

Instructions are resolved in order: **file → URL → built-in default**. A missing file
or failed fetch falls through silently — the server always starts.

**Restart the MCP client after changing anything.** A stdio server is one long-lived
process: it reads its code, its env and the instructions file at launch and never
looks again. Editing the instructions file, changing an env var, or shipping a new
version does nothing until the client restarts the server — and when you install from
a local path, `uvx` caches the built wheel per content hash, so a rebuilt package
needs that same restart to take effect. If notifications come back in the old format
after you edited the file, this is why.

### Two instruction modes

**Prose mode** (default): a `.md`/`.txt` file of plain-language rules. The LLM reads
them and tries to comply — flexible, zero setup, best-effort.

**Template mode**: point `NOTIFY_HUMAN_INSTRUCTIONS_FILE` at a `.json` file and the
format is enforced by construction. `send` then takes named fields — `status`,
`title`, `body`, optional `ticket`, `model`, `repo` — and the server assembles the
message from the template, so the shape cannot drift. An unknown status or a
missing field is rejected with the reason, nothing posted. Structure:

```json
{
  "header": "{time} | {repo} — {title} {status_emoji}",
  "lines": ["{ticket}", "model: {model} | Machine: {machine}"],
  "statuses": {"done": "✅", "blocked": "🛑", "question": "❓"},
  "max_chars": 1000,
  "embed": true,
  "guidance": "Address him as Rux. Short bullets, one fact each; no raw logs."
}
```

Only `header` and `statuses` are required. Placeholders for `header`/`lines`:
`time`, `repo`, `title`, `status_emoji`, `ticket_line`, `ticket`, `model`,
`machine`. `ticket_line` renders `ticket: X`; `ticket` renders the raw value
verbatim (e.g. `ENG-142 — rotate deploy keys`). A line that renders empty (no
ticket, say) is dropped. `max_chars` is a hard ceiling on the rendered message.
`embed: true` posts a rich card instead of a plain message, which lifts the
Discord limit from 2000 to 4096 characters. `guidance` is free text appended to
the instructions the LLM receives — the place for tone, persona and "when to
ping" rules that a fixed structure cannot express. Working examples:
[examples/](examples) (`template-minimal.json`, `template-full.json`,
`template-team.json`) — copy one and edit the values. Startup logs the mode and
source on stderr; if a prose file and a same-stem `.json` both exist, **JSON
wins**, and a broken JSON file is reported loudly rather than silently
downgrading to prose.

### Writing the instructions file

This file is the format control — and it decides *when* the LLM may ping you, not
just how. Example:

```markdown
Use the `send` tool whenever the human's attention is needed: you are blocked, you
need a decision or missing information, something important happened mid-task, or
you finished. One message per event — no play-by-play.
Format: one-line status first (done / blocked / needs input / FYI), then a short
summary, then what you need from the human (if anything). Keep it under 1000
characters. No raw logs.
```

Point several machines at the same file contents (or the same hosted URL) to get one
format everywhere; give a machine its own file to diverge.

**Trust note:** a hosted instructions URL is a control point — whoever can edit that
URL controls what every connected LLM is told. Keep it private and writeable only by
you.

## Development

```bash
uv sync                          # env + dev deps
uv run pytest -q                 # 85 tests, HTTP mocked or loopback-only, zero real sockets
uvx ruff check src tests         # lint
uvx ruff format --check src tests
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
