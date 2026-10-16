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

- [ ] **T2 — Core logic (reused from notify-rux.py).**
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

- [ ] **T3 — FastMCP wiring.** `FastMCP("notify-human", instructions=<resolved text>)`;
  tool `send(message: str, embed: bool = False) -> str`. Missing webhook URL → clear
  error string, nothing posted. Success → short status string (e.g.
  `sent 143 chars to Discord (embed=False)`). Acceptance: server starts over stdio.

- [ ] **T4 — pytest, zero real network.** `unittest.mock` on `urlopen` (and the
  instructions-URL fetch). Cases: truncation boundary (1999/2000/2001 chars, note
  present, final length ≤ 2000), plain payload shape, embed payload shape, instructions
  precedence file > URL > default, missing file falls through, failed URL fetch falls
  through, missing webhook → error and no HTTP call, HTTP 200/204 success, HTTP 4xx and
  `URLError` → failure string. Acceptance: `uv run pytest -q` green.

- [ ] **T5 — DoD proof runs (executed, not asserted).**
  - **D1:** driver script using `mcp.client.stdio` → `initialize` response carries a
    non-empty `instructions` field sourced from the file; `tools/list` shows exactly
    `send` with `message` required and `embed` defaulting to false.
  - **D2:** `send` posts the correct payload — proven against a fake local webhook
    (throwaway `http.server` on 127.0.0.1 capturing the POST body; plus
    `http://127.0.0.1:9/` → connection refused → failure string, nothing posted).
  - **D3:** truncation at 2000 with `... (truncated)`; both `embed=False` and
    `embed=True` produce valid Discord payloads (dump the JSON bodies).
  - **D4:** pytest green with mocked HTTP.

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

Commits are made per task as it completes — NOT batched at the end. Planned sequence
(extra commits are fine if a task splits; a commit is never amended after push):

| # | Commit | Task |
|---|---|---|
| 1 | `chore: add gitignore and progress ledger` | T0 |
| 2 | `build(packaging): add pyproject skeleton and package layout` | T1 |
| 3 | `test(config): add failing tests for env and instructions resolver` | T2a |
| 4 | `feat(config): resolve webhook URL and instructions file/URL/default` | T2a |
| 5 | `test(discord): add failing tests for truncation and payload builders` | T2b |
| 6 | `feat(discord): add truncation, payload builders and webhook POST` | T2b |
| 7 | `test(server): add failing tests for send tool contract` | T3 |
| 8 | `feat(server): expose send tool with instructions injection` | T3 |
| 9 | `test: cover HTTP failures and instructions fallbacks` | T4 |
| 10 | `docs(readme): document install, per-machine config and publish steps` | T6 |
| 11 | `chore: verify wheel build and console entry point` (dist/ stays ignored; commit only if anything changes) | T7 |
| 12 | `docs(progress): record task evidence` (final ledger update) | T8 |

T5 proof runs are verification, not code — their output lands in the Evidence log and
in the T3/T4 commit comments. If a proof run exposes a bug, it becomes
`fix(<scope>): …` with its own failing test first.

## Evidence log

- **T0:** `.gitignore` written (198 B) with the two local docs + python/editor
  patterns; `PROGRESS.md` created. No code written yet.
