"""Configuration: where to post (webhook) and what instructions to hand the LLM.

Everything comes from the environment so each install configures itself in the
client's MCP config block. No config files, no legacy variable names.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

WEBHOOK_URL_ENV = "NOTIFY_HUMAN_WEBHOOK_URL"
INSTRUCTIONS_FILE_ENV = "NOTIFY_HUMAN_INSTRUCTIONS_FILE"
INSTRUCTIONS_URL_ENV = "NOTIFY_HUMAN_INSTRUCTIONS_URL"

#: Seconds to wait for a hosted instructions URL before giving up.
INSTRUCTIONS_URL_TIMEOUT = 10

#: Fallback instructions when neither the file nor the URL yields text.
DEFAULT_INSTRUCTIONS = (
    "You have the `notify-human` tool. Use it to send exactly one notification when "
    "you finish a task or when the user asks to be pinged.\n\n"
    "Format the message as Discord markdown:\n"
    "1. A one-line status first (what happened: done / blocked / needs input).\n"
    "2. A short summary of what changed.\n"
    "3. Next steps or what you are waiting on.\n\n"
    "Keep it under 1000 characters. Do not paste raw logs or diffs."
)


def get_webhook_url(env=None):
    """Return the Discord webhook URL from the environment, or None if unset."""
    env = os.environ if env is None else env
    if not isinstance(env, dict) and not hasattr(env, "get"):
        return None
    url = (env.get(WEBHOOK_URL_ENV) or "").strip()
    return url or None


def _read_file(path):
    """Return the file's text, or None if it cannot be read or is blank."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    return text.strip() or None


def _fetch_url(url):
    """Return the text fetched from `url`, or None on any failure."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "notify-human-mcp/0.1"}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=INSTRUCTIONS_URL_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    return body.strip() or None


def load_instructions(env=None):
    """Resolve the standing instructions for the LLM.

    Sources are tried in order: local file -> hosted URL -> built-in default.
    A missing file or a failed fetch falls through; this never raises, because
    it runs at process start and a bad path must not stop the server.

    Returns (text, source) where source is "file", "url" or "default".
    """
    env = os.environ if env is None else env
    if not isinstance(env, dict) and not hasattr(env, "get"):
        return DEFAULT_INSTRUCTIONS, "default"

    path = (env.get(INSTRUCTIONS_FILE_ENV) or "").strip()
    if path:
        text = _read_file(path)
        if text:
            return text, "file"

    url = (env.get(INSTRUCTIONS_URL_ENV) or "").strip()
    if url:
        text = _fetch_url(url)
        if text:
            return text, "url"

    return DEFAULT_INSTRUCTIONS, "default"
