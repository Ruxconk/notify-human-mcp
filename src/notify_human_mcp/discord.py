"""Discord webhook layer: truncation, payload building, HTTP POST.

Reuses the logic proven in notify-rux (read message -> build payload -> POST ->
truncate at the limit), with two changes: payload building is separated from
sending so both are testable in isolation, and nothing here writes to stdout —
stdout is the MCP protocol channel, so diagnostics go to stderr.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import USER_AGENT

#: Discord's limit for a message's `content` field.
DISCORD_MAX_CONTENT = 2000

#: Discord's limit for an embed's `description` field. Wider than `content`, so
#: the embed path truncates here rather than at 2000.
EMBED_DESCRIPTION_MAX = 4096

TRUNCATION_NOTE = "\n\n... (truncated)"

#: Seconds to wait for the webhook before giving up.
HTTP_TIMEOUT = 15

#: Blurple — Discord's own brand colour, used for embed cards.
EMBED_COLOR = 0x5865F2


def truncate_message(text, limit=DISCORD_MAX_CONTENT):
    """Clamp `text` to `limit` characters, leaving room for the note.

    Returns (text, was_truncated). When truncated, the result is exactly `limit`
    characters long and ends with TRUNCATION_NOTE.
    """
    if len(text) <= limit:
        return text, False
    keep = limit - len(TRUNCATION_NOTE)
    return text[:keep] + TRUNCATION_NOTE, True


def build_plain_payload(content):
    """Build a Discord payload posting `content` as markdown text."""
    text, _ = truncate_message(content, DISCORD_MAX_CONTENT)
    return {"content": text}


def build_embed_payload(content, color=EMBED_COLOR):
    """Build a Discord payload posting `content` inside a rich embed card."""
    text, _ = truncate_message(content, EMBED_DESCRIPTION_MAX)
    return {"embeds": [{"description": text, "color": color}]}


def send_to_webhook(webhook_url, payload):
    """POST `payload` to `webhook_url`. Returns (ok, detail).

    Never raises: transport and HTTP failures come back as (False, reason) so the
    MCP tool can report them to the LLM instead of crashing the session.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            status = resp.status
            if status in (200, 204):
                return True, f"HTTP {status}"
            body = resp.read().decode("utf-8", errors="replace")
            return False, f"HTTP {status}: {body}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return False, f"HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        return False, f"could not reach webhook: {e.reason}"
    except Exception as e:  # noqa: BLE001 - report, never crash the session
        return False, f"unexpected error: {e}"
