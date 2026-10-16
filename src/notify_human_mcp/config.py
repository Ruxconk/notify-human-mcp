"""Configuration: where to post (webhook) and what instructions to hand the LLM.

Everything comes from the environment so each install configures itself in the
client's MCP config block. No config files, no legacy variable names.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

from . import USER_AGENT

WEBHOOK_URL_ENV = "NOTIFY_HUMAN_WEBHOOK_URL"
INSTRUCTIONS_FILE_ENV = "NOTIFY_HUMAN_INSTRUCTIONS_FILE"
INSTRUCTIONS_URL_ENV = "NOTIFY_HUMAN_INSTRUCTIONS_URL"

#: Seconds to wait for a hosted instructions URL before giving up.
INSTRUCTIONS_URL_TIMEOUT = 10

#: Fallback instructions when neither the file nor the URL yields text.
DEFAULT_INSTRUCTIONS = (
    "You have the `notify-human` tool. Use it whenever the human's attention is "
    "needed: you are blocked, you need a decision or missing information, something "
    "important happened mid-task, you finished a task, or the user asked to be "
    "pinged. One message per event.\n\n"
    "Format the message as Discord markdown:\n"
    "1. A one-line status first (done / blocked / needs input / heads-up).\n"
    "2. Short bullets of what is relevant — no walls of text.\n"
    "3. What you need from the human, if anything.\n\n"
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
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    return text.strip() or None


def _fetch_url(url):
    """Return the text fetched from `url`, or None on any network failure.

    Only I/O and decode failures fall through to the next source. Programming
    errors (and the test suite's socket guard) must propagate, not be mistaken
    for an unreachable URL.
    """
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=INSTRUCTIONS_URL_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return body.strip() or None


def load_instructions(env=None):
    """Resolve the standing instructions for the LLM.

    Sources are tried in order: local file -> hosted URL -> built-in default.
    A missing file or an unreachable URL falls through to the next source, so a
    bad path never stops the server at process start. Non-I/O errors (real bugs)
    propagate instead of being mistaken for a missing source.

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
