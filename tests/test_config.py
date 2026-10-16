"""Tests for config: webhook URL resolution and the instructions source chain."""

import io
import urllib.error
from unittest.mock import patch

import pytest

from notify_human_mcp import config

FILE_ENV = "NOTIFY_HUMAN_INSTRUCTIONS_FILE"
URL_ENV = "NOTIFY_HUMAN_INSTRUCTIONS_URL"
HOOK_ENV = "NOTIFY_HUMAN_WEBHOOK_URL"


# --- webhook URL -----------------------------------------------------------


def test_webhook_url_read_from_env():
    assert config.get_webhook_url({HOOK_ENV: " https://x/y "}) == "https://x/y"


def test_webhook_url_missing_is_none():
    assert config.get_webhook_url({}) is None


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_webhook_url_blank_is_none(value):
    assert config.get_webhook_url({HOOK_ENV: value}) is None


def test_legacy_notify_rux_env_is_ignored():
    # notify-rux's variable must NOT be picked up: per-install config is explicit.
    assert config.get_webhook_url({"NOTIFY_RUX_WEBHOOK_URL": "https://old"}) is None


def test_no_etc_config_file_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert config.get_webhook_url({}) is None


# --- instructions: precedence ----------------------------------------------


def test_file_wins_over_url(tmp_path):
    f = tmp_path / "instr.md"
    f.write_text("FROM FILE")
    env = {FILE_ENV: str(f), URL_ENV: "http://example.invalid/i.md"}
    with patch.object(config.urllib.request, "urlopen") as m:
        text, source = config.load_instructions(env)
    assert text == "FROM FILE"
    assert source == "file"
    m.assert_not_called()


def test_url_used_when_no_file(tmp_path):
    env = {URL_ENV: "http://example.invalid/i.md"}
    with patch.object(config.urllib.request, "urlopen") as m:
        m.return_value = _resp(b"FROM URL")
        text, source = config.load_instructions(env)
    assert text == "FROM URL"
    assert source == "url"
    called = m.call_args[0][0]
    assert getattr(called, "full_url", called) == "http://example.invalid/i.md"


def test_default_when_no_file_and_no_url():
    text, source = config.load_instructions({})
    assert source == "default"
    assert text == config.DEFAULT_INSTRUCTIONS
    assert text.strip(), "built-in default must be non-empty"


# --- instructions: fallbacks -----------------------------------------------


def test_missing_file_falls_through_to_url(tmp_path):
    env = {FILE_ENV: str(tmp_path / "nope.md"), URL_ENV: "http://example.invalid/i.md"}
    with patch.object(config.urllib.request, "urlopen") as m:
        m.return_value = _resp(b"FROM URL")
        text, source = config.load_instructions(env)
    assert (text, source) == ("FROM URL", "url")


def test_missing_file_falls_through_to_default(tmp_path):
    env = {FILE_ENV: str(tmp_path / "nope.md")}
    text, source = config.load_instructions(env)
    assert source == "default"
    assert text == config.DEFAULT_INSTRUCTIONS


def test_url_failure_falls_through_to_default():
    env = {URL_ENV: "http://127.0.0.1:9/instructions.md"}
    with patch.object(
        config.urllib.request,
        "urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        text, source = config.load_instructions(env)
    assert source == "default"
    assert text == config.DEFAULT_INSTRUCTIONS


def test_empty_file_falls_through(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("   \n\n")
    text, source = config.load_instructions({FILE_ENV: str(f)})
    assert source == "default"
    assert text == config.DEFAULT_INSTRUCTIONS


def test_directory_as_file_falls_through(tmp_path):
    text, source = config.load_instructions({FILE_ENV: str(tmp_path)})
    assert source == "default"
    assert text == config.DEFAULT_INSTRUCTIONS


def test_url_http_error_falls_through_to_default():
    env = {URL_ENV: "http://example.invalid/i.md"}
    err = urllib.error.HTTPError(
        env[URL_ENV], 404, "Not Found", {}, io.BytesIO(b"nope")
    )
    with patch.object(config.urllib.request, "urlopen", side_effect=err):
        text, source = config.load_instructions(env)
    assert source == "default"
    assert text == config.DEFAULT_INSTRUCTIONS


def test_blank_url_body_falls_through_to_default():
    env = {URL_ENV: "http://example.invalid/i.md"}
    with patch.object(config.urllib.request, "urlopen") as m:
        m.return_value = _resp(b"  \n ")
        text, source = config.load_instructions(env)
    assert source == "default"
    assert text == config.DEFAULT_INSTRUCTIONS


def test_url_programming_error_is_not_swallowed():
    # A non-I/O failure must surface, not masquerade as an unreachable URL.
    # The old bare `except Exception` hid real bugs (and the suite's own socket
    # guard) behind a silent fall-through to the default instructions.
    env = {URL_ENV: "http://example.invalid/i.md"}
    with (
        patch.object(config.urllib.request, "urlopen", side_effect=RuntimeError("bug")),
        pytest.raises(RuntimeError, match="bug"),
    ):
        config.load_instructions(env)


def test_url_fetch_has_a_timeout():
    env = {URL_ENV: "http://example.invalid/i.md"}
    with patch.object(config.urllib.request, "urlopen") as m:
        m.return_value = _resp(b"ok")
        config.load_instructions(env)
    assert m.call_args.kwargs.get("timeout") == config.INSTRUCTIONS_URL_TIMEOUT


def test_load_instructions_never_raises_on_garbage_env():
    # A non-mapping env must not blow up the process at startup.
    for garbage in (object(), 42, "not-a-mapping"):
        text, source = config.load_instructions(garbage)
        assert source == "default"
        assert text == config.DEFAULT_INSTRUCTIONS


def _resp(body: bytes):
    class _R:
        status = 200

        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return _R()
