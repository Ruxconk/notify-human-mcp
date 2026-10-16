"""Tests for the Discord layer: truncation, payload builders, webhook POST."""

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from notify_human_mcp import discord


# --- truncation ------------------------------------------------------------


def test_constants_match_discord_limits():
    assert discord.DISCORD_MAX_CONTENT == 2000
    assert discord.TRUNCATION_NOTE == "\n\n... (truncated)"
    assert discord.EMBED_DESCRIPTION_MAX == 4096


@pytest.mark.parametrize("n", [0, 1, 1999, 2000])
def test_no_truncation_at_or_under_limit(n):
    text = "x" * n
    out, was_cut = discord.truncate_message(text)
    assert out == text
    assert was_cut is False


@pytest.mark.parametrize("n", [2001, 3000, 10_000])
def test_truncation_at_limit_keeps_note_and_total_at_2000(n):
    text = "x" * n
    out, was_cut = discord.truncate_message(text)
    assert was_cut is True
    assert out.endswith(discord.TRUNCATION_NOTE)
    assert len(out) == discord.DISCORD_MAX_CONTENT


def test_truncation_leaves_room_for_the_note():
    # The note must fit inside the limit, not be appended past it.
    text = "x" * 5000
    out, _ = discord.truncate_message(text)
    keep = discord.DISCORD_MAX_CONTENT - len(discord.TRUNCATION_NOTE)
    assert out == "x" * keep + discord.TRUNCATION_NOTE


def test_truncation_honours_custom_limit():
    text = "abcdefghijklmnopqrstuvwxyz"
    out, was_cut = discord.truncate_message(text, limit=25)
    assert was_cut is True
    assert out == "abcdefgh" + discord.TRUNCATION_NOTE
    assert len(out) == 25


def test_truncation_preserves_content_when_not_cut():
    out, was_cut = discord.truncate_message("hello **world**")
    assert out == "hello **world**"
    assert was_cut is False


# --- payload builders (pure, no I/O) ---------------------------------------


def test_plain_payload_shape():
    payload = discord.build_plain_payload("hi **there**")
    assert payload == {"content": "hi **there**"}


def test_plain_payload_truncates_at_2000():
    payload = discord.build_plain_payload("x" * 2500)
    assert len(payload["content"]) == 2000
    assert payload["content"].endswith(discord.TRUNCATION_NOTE)


def test_embed_payload_shape():
    payload = discord.build_embed_payload("hello")
    assert payload["embeds"][0]["description"] == "hello"
    assert isinstance(payload["embeds"][0]["color"], int)
    assert set(payload) == {"embeds"}
    assert set(payload["embeds"][0]) == {"description", "color"}


def test_embed_payload_keeps_text_under_embed_limit():
    # Discord allows 4096 in an embed description; do not drop content at 2000.
    text = "y" * 3000
    payload = discord.build_embed_payload(text)
    assert payload["embeds"][0]["description"] == text  # under 4096, untouched


def test_embed_payload_truncates_past_embed_limit():
    payload = discord.build_embed_payload("y" * 5000)
    desc = payload["embeds"][0]["description"]
    assert len(desc) == discord.EMBED_DESCRIPTION_MAX
    assert desc.endswith(discord.TRUNCATION_NOTE)


def test_payloads_are_json_serialisable():
    for p in (discord.build_plain_payload("a"), discord.build_embed_payload("b")):
        assert json.loads(json.dumps(p)) == p


# --- webhook POST -----------------------------------------------------------


def _resp(status=204, body=b""):
    class _R:
        def __init__(self):
            self.status = status

        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return _R()


def test_post_plain_sends_json_body_and_headers():
    with patch.object(discord.urllib.request, "urlopen") as m:
        m.return_value = _resp(204)
        ok, detail = discord.send_to_webhook(
            "http://127.0.0.1:9/hook", discord.build_plain_payload("hello")
        )
    assert ok is True
    assert "204" in detail
    req = m.call_args[0][0]
    assert req.full_url == "http://127.0.0.1:9/hook"
    assert req.method == "POST"
    assert json.loads(req.data.decode()) == {"content": "hello"}
    assert req.get_header("Content-type") == "application/json"
    assert "notify-human" in req.get_header("User-agent")
    assert m.call_args.kwargs["timeout"] == discord.HTTP_TIMEOUT


@pytest.mark.parametrize("status", [200, 204])
def test_post_success_statuses(status):
    with patch.object(discord.urllib.request, "urlopen") as m:
        m.return_value = _resp(status)
        ok, _ = discord.send_to_webhook("http://x/hook", {"content": "a"})
    assert ok is True


def test_post_embed_payload_body():
    with patch.object(discord.urllib.request, "urlopen") as m:
        m.return_value = _resp(204)
        ok, _ = discord.send_to_webhook(
            "http://x/hook", discord.build_embed_payload("hi")
        )
    req = m.call_args[0][0]
    body = json.loads(req.data.decode())
    assert body["embeds"][0]["description"] == "hi"


def test_post_http_error_returns_failure_with_body():
    err = urllib.error.HTTPError(
        "http://x/hook", 400, "Bad Request", {}, io.BytesIO(b'{"code":50035}')
    )
    with patch.object(discord.urllib.request, "urlopen", side_effect=err):
        ok, detail = discord.send_to_webhook("http://x/hook", {"content": "a"})
    assert ok is False
    assert "400" in detail
    assert "50035" in detail


def test_post_unreachable_webhook_returns_failure():
    err = urllib.error.URLError("connection refused")
    with patch.object(discord.urllib.request, "urlopen", side_effect=err):
        ok, detail = discord.send_to_webhook(
            "http://127.0.0.1:9/hook", {"content": "a"}
        )
    assert ok is False
    assert "connection refused" in detail


def test_post_unexpected_error_returns_failure():
    with patch.object(
        discord.urllib.request, "urlopen", side_effect=RuntimeError("boom")
    ):
        ok, detail = discord.send_to_webhook("http://x/hook", {"content": "a"})
    assert ok is False
    assert "boom" in detail


def test_post_never_writes_to_stdout(capsys):
    with patch.object(
        discord.urllib.request, "urlopen", side_effect=urllib.error.URLError("nope")
    ):
        discord.send_to_webhook("http://127.0.0.1:9/hook", {"content": "a"})
    assert capsys.readouterr().out == ""
