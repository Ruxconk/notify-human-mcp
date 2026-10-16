"""Template mode: a JSON file that fixes the message shape.

Prose instructions are advisory — the LLM tries to follow them. A template is
enforced by construction: the LLM calls `send` with named fields (status,
title, body, optional ticket) and the server assembles the final text from the
template, so the format cannot drift. No LLM converts prose to JSON; the repo
ships example templates.

A template is a JSON object:

    {
      "header": "{time} | {repo} — {title} {status_emoji}",
      "lines": ["{ticket_line}", "model: {model} | Machine: {machine}"],
      "statuses": {"done": "✅", "blocked": "🛑"},
      "max_chars": 1000
    }

`header` and each entry of `lines` may use the placeholders: time, repo, title,
status_emoji, ticket_line, model, machine. A line whose only placeholder is
`ticket_line` is dropped when no ticket is given. `statuses` maps the status
the LLM picks to its emoji; `max_chars` is a hard ceiling on the rendered
message (0/absent = no template-level ceiling, Discord limits still apply).
"""

from __future__ import annotations

import os
import socket
from datetime import datetime
from string import Formatter

#: Placeholders usable in header/lines.
PLACEHOLDERS = frozenset(
    {"time", "repo", "title", "status_emoji", "ticket_line", "model", "machine"}
)


class TemplateError(ValueError):
    """Template file is invalid. Message names the problem precisely."""


class _Formatter(Formatter):
    """Rejects unknown keys at render time (defence after load-time check)."""

    def get_value(self, key, args, kwargs):
        name = key if isinstance(key, str) else str(key)
        if name not in kwargs:
            raise TemplateError(f"template used unknown placeholder {name!r}")
        return kwargs[name]


_FORMATTER = _Formatter()


def _names_in(field):
    return {name for _, name, _, _ in Formatter().parse(field) if name}


def load_template(path):
    """Load and validate a template file. Raises TemplateError with a reason."""
    import json

    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        raise TemplateError(f"cannot read template {path}: {e}") from e
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise TemplateError(f"template {path} is not valid JSON: {e}") from e

    if not isinstance(data, dict):
        raise TemplateError(f"template {path} must be a JSON object")
    header = data.get("header")
    if not isinstance(header, str) or not header:
        raise TemplateError(f"template {path} needs a non-empty string 'header'")
    lines = data.get("lines", [])
    if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
        raise TemplateError(f"template {path} 'lines' must be a list of strings")
    statuses = data.get("statuses")
    if (
        not isinstance(statuses, dict)
        or not statuses
        or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in statuses.items()
        )
    ):
        raise TemplateError(
            f"template {path} needs 'statuses' as a non-empty object "
            "mapping status name -> emoji"
        )
    max_chars = data.get("max_chars", 0)
    if not isinstance(max_chars, int) or max_chars < 0:
        raise TemplateError(f"template {path} 'max_chars' must be a non-negative int")

    for field in [header, *lines]:
        unknown = _names_in(field) - PLACEHOLDERS
        if unknown:
            raise TemplateError(
                f"template {path} uses unknown placeholder(s) "
                f"{sorted(unknown)} in {field!r}; allowed: {sorted(PLACEHOLDERS)}"
            )

    return {
        "header": header,
        "lines": lines,
        "statuses": statuses,
        "max_chars": max_chars,
    }


def render_message(
    tmpl,
    *,
    status,
    title,
    body,
    ticket=None,
    model=None,
    now=None,
    repo=None,
    machine=None,
):
    """Assemble the final message. Raises TemplateError on bad input.

    Deterministic: same arguments (and same `now`) -> identical string.
    """
    if status not in tmpl["statuses"]:
        raise TemplateError(
            f"status {status!r} is not defined by the template; "
            f"choose one of: {', '.join(sorted(tmpl['statuses']))}"
        )
    if not title or not title.strip():
        raise TemplateError("title is required and must be non-empty")
    if not body or not body.strip():
        raise TemplateError("body is required and must be non-empty")

    now = now or datetime.now()
    values = {
        "time": now.strftime("%H:%M"),
        "repo": repo
        or os.environ.get("NOTIFY_HUMAN_REPO")
        or os.path.basename(os.getcwd()),
        "title": title.strip(),
        "status_emoji": tmpl["statuses"][status],
        "ticket_line": f"ticket: {ticket.strip()}" if ticket and ticket.strip() else "",
        "model": model or os.environ.get("NOTIFY_HUMAN_MODEL") or "unknown",
        "machine": machine
        or os.environ.get("NOTIFY_HUMAN_MACHINE")
        or socket.gethostname(),
    }

    parts = [_FORMATTER.format(tmpl["header"], **values)]
    for line in tmpl["lines"]:
        rendered = _FORMATTER.format(line, **values)
        if rendered.strip():
            parts.append(rendered)
    parts.append("")
    parts.append(body.strip())
    message = "\n".join(parts)

    limit = tmpl.get("max_chars") or 0
    if limit and len(message) > limit:
        raise TemplateError(
            f"rendered message is {len(message)} chars, over the template's "
            f"max_chars limit of {limit}; shorten the body"
        )
    return message


def build_llm_text(tmpl):
    """Instructions text for template mode (replaces the prose file text)."""
    statuses = ", ".join(f"`{k}`" for k in sorted(tmpl["statuses"]))
    limit = tmpl.get("max_chars") or 0
    lines = [
        "You have the `notify-human` tool for reaching the human on Discord.",
        "Use it whenever their attention is needed: you are blocked, need a "
        "decision or missing info, something important happened mid-task, you "
        "finished, or they asked to be pinged. One message per event.",
        "",
        "This install uses a fixed message template. Call `send` with named "
        "fields and the server assembles the message — do not format it "
        "yourself:",
        "- `status`: one of " + statuses + " — pick the honest one.",
        "- `title`: one short line, the headline.",
        "- `body`: what matters, short bullets, no raw logs.",
        "- `ticket`: tracker id if the work has one (optional).",
    ]
    if limit:
        lines.append(f"- The finished message must stay under {limit} characters.")
    return "\n".join(lines)
