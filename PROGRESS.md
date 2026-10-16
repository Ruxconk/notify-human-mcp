# PROGRESS — notify-human-mcp

Ledger for building the `notify-human` MCP server. Source docs: `requirements.md`
(requirements + design), `PUBLISHING.md` (distribution plan), reference tool
`/home/rux/bootstrap-blackwall-llm/scripts/notify-rux/notify-rux.py`.

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done + evidence below.

## Non-negotiable process rules

1. **TDD is MANDATORY.** For every behaviour, write the failing test first, run it and
   watch it fail for the expected reason, write the minimum code to pass, run again,
   then refactor. No production line ships without a test that failed before it existed.
   Test-first applies to T2 (config + Discord logic), T3 (tool contract) and T5
   (end-to-end proofs). T1/T6/T7/T8 are packaging/docs — no tests, but they still
   require the stated acceptance command to be run and its output recorded.
2. **Atomic commits, Conventional Commits v1.0.0**
   (https://www.conventionalcommits.org/en/v1.0.0/). Format `<type>[optional scope]:
   <description>`; types in use: `feat`, `fix`, `docs`, `test`, `refactor`, `build`,
   `chore`, `perf`, `ci`. One logical change per commit; the tree must build and the
   tests must pass at every commit. Scope = `config`, `discord`, `server`, `packaging`,
   `docs`, `tests`. Breaking change → `!` / `BREAKING CHANGE:` footer (none expected).
3. **Comment in this file as you go.** When a task changes state, append a
   `> **Comment:**` blockquote inside that task's bullet recording: what was done, the
   exact command run, and the observed result (counts, failures seen first, commit
   hash). Deviations, surprises and follow-ups go in the same place. The Evidence log at
   the bottom stays the final roll-up; the per-task comments are the running narrative.
   Never mark `[x]` without a comment containing a real command + real output.

## Binding constraints (carry-over; no AGENTS.md in this repo)

- **ONE-LLM RULE:** this box runs exactly one LLM (the agent). NEVER load a model or
  inference server (no llama-server, no GGUF, no llama-cpp-python). This task is pure
  build + mock testing; there is no model in a Discord-webhook tool.
- **NEVER post to real Discord while developing.** Test the post path against a fake
  local webhook (`http://127.0.0.1:9/...` → connection refused → exit 1, nothing
  posted) or monkeypatch the HTTP call in pytest.
- Shell trap: `VAR=x cmd1 | cmd2` binds VAR to `cmd1` only.
- Notification discipline (only if pinging via notify-rux): ≤1000 chars, exactly one
  per prompt, at the end, lead with the actionable.

## Decisions already made (do not re-litigate)

- Python + official `mcp` SDK, **FastMCP**.
- Exactly one tool: `send(message: str, embed: bool = False)` → short status string.
  `embed=False` → Discord markdown; `embed=True` → rich embed card.
- Env vars (per-install): `NOTIFY_HUMAN_WEBHOOK_URL` (required),
  `NOTIFY_HUMAN_INSTRUCTIONS_FILE` (local path, primary),
  `NOTIFY_HUMAN_INSTRUCTIONS_URL` (hosted URL, secondary — implement now).
- Instructions at process start, in order **file → URL (fetch) → built-in default**,
  passed as `FastMCP("notify-human", instructions=...)`. Re-read on every client
  launch. The LLM sees text only — never a path or URL.
- PyPI package `notify-human-mcp`, MIT (existing LICENSE), dep on `mcp`, console entry
  point so `uvx notify-human-mcp` runs it.
- Out of scope: LLM-to-LLM conversation over Discord (bot token, two-way).

## Amended Definition of Done

Original DoD item 5 said "commit requirements.md and PUBLISHING.md". Overridden by
explicit instruction: both are now in `.gitignore` and stay local-only. All other DoD
items stand unchanged.

## Tasks

- [x] **T0 — `.gitignore` + this ledger.** `.gitignore` created: `requirements.md`,
  `PUBLISHING.md`, `.swp`/`*.swp`/`*.swo`, `__pycache__/`, `*.egg-info/`, `.venv/`,
  `dist/`, `build/`. `PROGRESS.md` is tracked (it is the repo's progress log).
  Acceptance: `git status` no longer lists `requirements.md`/`PUBLISHING.md` as
  untracked.
>
> **Comment (T0):** wrote `.gitignore` (198 B) and this ledger. Command:
> `git check-ignore -v requirements.md PUBLISHING.md` →
> `.gitignore:2:requirements.md` / `.gitignore:3:PUBLISHING.md`; `git status --short`
> → only `?? .gitignore`, `?? PROGRESS.md`. Commit: pending (first commit of the run).

- [ ] **T1 — Packaging skeleton.** `pyproject.toml`: name `notify-human-mcp`, version
  `0.1.0`, MIT license referencing the existing `LICENSE`, `requires-python >=3.10`,
  dependency `mcp`, `[project.scripts] notify-human-mcp = "notify_human_mcp.server:main"`.
  Layout `src/notify_human_mcp/` (`__init__.py`, `config.py`, `discord.py`, `server.py`).
  Acceptance: `uv build` produces sdist + wheel; the console script runs.
>
> **Comment (T1):** `pyproject.toml` (hatchling, src layout, `[project.scripts]
> notify-human-mcp = "notify_human_mcp.server:main"`, dep `mcp>=1`, dev group pytest) +
> empty `src/notify_human_mcp/` modules. Command: `uv build` →
> `Successfully built dist/notify_human_mcp-0.1.0.tar.gz` +
> `notify_human_mcp-0.1.0-py3-none-any.whl`. Commit `eb14270`.
>
> **DEVIATION (recorded before T3):** the installed SDK is **mcp 2.3.0**, where
> `mcp.server.fastmcp.FastMCP` no longer exists — renamed to
> `mcp.server.mcpserver.MCPServer` (same constructor incl. `instructions=`, same
> `@server.tool()` decorator, same `run(transport="stdio")`). The "use FastMCP"
> decision is honored in spirit: same class, current name. Code imports
> `MCPServer` with a `try/except ImportError` fallback to `FastMCP` so the package
> works on both mcp 1.x and 2.x.

- [x] **T2 — Core logic (reused from notify-rux.py).**
  - `config.py`: webhook URL from `NOTIFY_HUMAN_WEBHOOK_URL` only (no `/etc` fallback,
    no legacy `NOTIFY_RUX_*` names); instructions resolver in order
    `NOTIFY_HUMAN_INSTRUCTIONS_FILE` → `NOTIFY_HUMAN_INSTRUCTIONS_URL` (urllib GET,
    timeout) → built-in default string. The resolver never raises: a missing file or a
    failed fetch falls through to the next source.
  - `discord.py`: `DISCORD_MAX_CONTENT = 2000`,
    `TRUNCATION_NOTE = "\n\n... (truncated)"`, `truncate_message()` leaving room for the
    note; payload builders — plain `{"content": ...}` and embed
    `{"embeds": [{"description": ..., "color": ...}]}` (Discord's embed description
    limit is 4096, so the 2000-char truncation belongs to the plain path — verify and
    document); POST via `urllib.request` with `Content-Type: application/json`, 15 s
    timeout, success on 200/204, failures returned as strings. Nothing prints to
    stdout — stdout is the MCP channel; diagnostics go to stderr.
  - Acceptance: payload builders are pure functions, no I/O.

>
> **Comment (T2a — config):** TDD: wrote `tests/test_config.py` first →
> `uv run pytest -q` → **19 failed** (`ModuleNotFoundError`, then `AttributeError: no
> attribute 'load_instructions'` — expected red). Implemented `config.py` →
> **19 passed in 0.13s**. Covers: env-only webhook (blank/whitespace → None, legacy
> `NOTIFY_RUX_*` ignored, no `/etc` fallback), instructions precedence file > URL >
> default, missing/empty/directory file falls through, URL `URLError`/`HTTPError`/
> blank-body falls through, fetch uses `INSTRUCTIONS_URL_TIMEOUT`, garbage env never
> raises. `load_instructions` returns `(text, source)`; `source` is logged to stderr at
> startup only — the LLM sees text, never a path or URL.
>
> **Comment (T2b — discord):** TDD: wrote `tests/test_discord.py` first →
> `uv run pytest -q` → **25 failed, 19 passed** (`AttributeError: no attribute
> 'urllib'` etc. — expected red). Implemented `discord.py` → **44 passed in 0.08s**.
> Truncation: 0/1/1999/2000 untouched; 2001/3000/10000 → exactly 2000 chars ending in
> `\n\n... (truncated)`; custom-limit param tested. Embed path truncates at
> `EMBED_DESCRIPTION_MAX = 4096` (verified: 3000 chars pass through untouched, 5000 →
> 4096 + note) — the 2000 limit is `content`-only, as flagged in the task. POST:
> headers/method/body/timeout asserted via mocked `urlopen`; 200/204 ok; HTTPError
> (400 + body), URLError, generic Exception → `(False, detail)`; stdout stays empty.
> One live-socket test was removed from the suite to keep DoD #4 (zero real network in
> pytest) honest; the closed-port proof moves to T5/D2.

- [x] **T3 — FastMCP wiring.** `MCPServer("notify-human", instructions=<resolved text>)`
  (see mcp 2.x deviation under T1); tool `send(message: str, embed: bool = False) ->
  str`. Missing webhook URL → clear error, nothing posted. Success → short status
  string (`sent 143 chars to Discord (embed=False)`). Acceptance: server starts over
  stdio (proved in T5/D1).
>
> **Comment (T3):** TDD: `tests/test_server.py` first → **13 failed, 44 passed**
> (`no attribute 'build_server'` — expected red) → implemented `server.py` →
> **57 passed in 0.87s**. Covers: name + `instructions` injection (and default
> fallback), exactly one tool `send`, schema `required=["message"]` + `embed` default
> False, missing webhook → `ToolError` naming `NOTIFY_HUMAN_WEBHOOK_URL` with
> `send_to_webhook` asserted not called, plain + embed payload shapes through the tool,
> truncation reported in the status string, HTTP failure → `ToolError`, blank message
> rejected, stdout stays empty. Added `tests/conftest.py` autouse fixture so ambient
> `NOTIFY_HUMAN_*` env can't leak into tests. SDK import is
> `MCPServer` with `FastMCP` fallback; `ToolError` likewise.

- [x] **T4 — pytest, zero real network.** `unittest.mock` on `urlopen` (and the
  instructions-URL fetch). Cases: truncation boundary (1999/2000/2001 chars, note
  present, final length ≤ 2000), plain payload shape, embed payload shape, instructions
  precedence file > URL > default, missing file falls through, failed URL fetch falls
  through, missing webhook → error and no HTTP call, HTTP 200/204 success, HTTP 4xx and
  `URLError` → failure string. Acceptance: `uv run pytest -q` green.
>
> **Comment (T4):** all listed cases were covered by the T2/T3 suites (57 tests). The
> new hardening: `tests/conftest.py::no_real_network` autouse fixture patches
> `socket.socket.connect` and `socket.create_connection` to raise
> `AssertionError("test attempted a real network connection")`. Guard proven
> non-vacuous with a throwaway probe test that tried a direct `socket.connect` and a
> real `urllib.request.urlopen` — both failed with exactly that message; probe deleted
> after. `uv run pytest -q` → **57 passed in 0.86s**, zero sockets opened.

- [x] **T5 — DoD proof runs (executed, not asserted).** Driver:
  `/tmp/proof_dod.py` (throwaway, not committed) — real `mcp.client.stdio` client
  against `python -m notify_human_mcp.server` subprocesses.
  - **D1:** `initialize.instructions` == exact file text; `tools/list` == `['send']`,
    `required=['message']`, `embed.default=False`.
  - **D2:** fake webhook = `ThreadingHTTPServer` on 127.0.0.1 (ephemeral port)
    captured 4 POST bodies, all `application/json`; closed port
    `127.0.0.1:9` → `isError=True` "could not reach webhook: [Errno 111] Connection
    refused", zero captures; unset webhook → `isError=True` naming
    `NOTIFY_HUMAN_WEBHOOK_URL`, zero captures.
  - **D3:** 2500-char plain → exactly 2000 chars ending `\n\n... (truncated)`;
    5000-char embed → 4096 + note; status strings report the truncation.
  - **D4:** pytest green with mocked HTTP (see T4).
>
> **Comment (T5):** ran `.venv/bin/python /tmp/proof_dod.py` → **ALL PROOFS PASSED**.
> Observed during the run: mcp 2.x client models are snake_case (`input_schema`,
> `is_error`) — driver fixed accordingly; server stderr shows
> `notify-human: instructions from file (61 chars), webhook set`, confirming the
> startup log. No real Discord contact: every URL was 127.0.0.1.

- [ ] **T6 — README replacement.** Overwrite the 18-byte stub with: what it is (one
  tool, `send`), install/run via `uvx notify-human-mcp`, the per-machine client config
  block from PUBLISHING.md (command + the three env vars), how to set the instructions
  file and that edits take effect next session, the file→URL→default order, the trust
  note about a hosted URL, and the **publish commands as documentation only**:
  `uv build` then `uv publish` (or `python -m build` + `twine upload dist/*`), plus a
  clearly-labeled optional later step for the MCP Registry listing.

- [ ] **T7 — PyPI publish PREPARED, NOT run.** Run `uv build`; inspect `dist/` (sdist +
  wheel, entry point present — `unzip -l` / `tar tzf`); smoke the built wheel in a
  throwaway venv (`uvx --from dist/...whl notify-human-mcp`). **Do NOT run
  `uv publish`** — needs the user's PyPI account/token.

- [ ] **T8 — Final sweep + push.** Verify the working tree is clean, every task above
  has a `> **Comment:**` with command + output, and `requirements.md`/`PUBLISHING.md`
  are still ignored (`git status --ignored`). Push `main` to `origin`
  (`https://github.com/Ruxconk/notify-human-mcp.git`).


## Commit plan (atomic, Conventional Commits)

Commits are made per task as it completes — NOT batched at the end. A commit is never
amended after push.

**Reconciled:** rule 1 (TDD) and rule 2 (green tree at every commit) collide if a
failing-test commit is committed on its own. Resolution: each unit is ONE commit
containing its tests + the implementation that makes them pass. The red run is still
executed and its output recorded in the task comment, so TDD is honoured without ever
committing a broken tree.

| # | Commit | Task |
|---|---|---|
| 1 | `chore: add gitignore and progress ledger` | T0 |
| 2 | `build(packaging): add pyproject skeleton and package layout` | T1 |
| 3 | `feat(config): resolve webhook URL and instructions file/URL/default` | T2a |
| 4 | `feat(discord): add truncation, payload builders and webhook POST` | T2b |
| 5 | `feat(server): expose send tool with instructions injection` | T3 |
| 6 | `test: cover HTTP failures and instructions fallbacks` | T4 |
| 7 | `docs(readme): document install, per-machine config and publish steps` | T6 |
| 8 | `chore: verify wheel build and console entry point` (dist/ stays ignored) | T7 |
| 9 | `docs(progress): record task evidence` | T8 |

T5 proof runs are verification, not code — their output lands in the Evidence log and
in the T3/T4 commit comments. If a proof run exposes a bug, it becomes
`fix(<scope>): …` with its own failing test first.

## Evidence log

- **T0:** `.gitignore` written (198 B) with the two local docs + python/editor
  patterns; `PROGRESS.md` created. No code written yet.
