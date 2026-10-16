"""Tests for the MCP server wiring: instructions injection and the send tool."""

import asyncio
import json
from unittest.mock import patch

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from notify_human_mcp import server


def run(coro):
    return asyncio.run(coro)


# --- server construction ----------------------------------------------------


def test_server_name_and_instructions():
    s = server.build_server(instructions="BE STANDING")
    assert s.name == "notify-human"
    assert s.instructions == "BE STANDING"


def test_instructions_default_to_config_default():
    s = server.build_server(instructions=None)
    assert s.instructions == server.config.DEFAULT_INSTRUCTIONS


def test_exactly_one_tool_named_send():
    tools = run(server.build_server().list_tools())
    assert [t.name for t in tools] == ["send"]


def test_send_schema_requires_message_and_defaults_embed():
    tool = run(server.build_server().list_tools())[0]
    schema = tool.input_schema
    assert schema["required"] == ["message"]
    assert schema["properties"]["message"]["type"] == "string"
    assert schema["properties"]["embed"]["default"] is False


def test_send_has_a_description_for_the_llm():
    tool = run(server.build_server().list_tools())[0]
    assert tool.description and "Discord" in tool.description


# --- send: missing webhook --------------------------------------------------


def test_send_without_webhook_errors_and_does_not_post():
    s = server.build_server(webhook_url=None)
    with patch.object(server.discord, "send_to_webhook") as m:
        with pytest.raises(ToolError) as ei:
            run(s.call_tool("send", {"message": "hi"}))
    m.assert_not_called()
    assert "NOTIFY_HUMAN_WEBHOOK_URL" in str(ei.value)


# --- send: success paths ----------------------------------------------------


def _ok(detail="HTTP 204"):
    return patch.object(server.discord, "send_to_webhook", return_value=(True, detail))


def test_send_plain_posts_content_payload():
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    msg = "hello **world**"
    with _ok() as m:
        res = run(s.call_tool("send", {"message": msg}))
    url, payload = m.call_args[0]
    assert url == "http://127.0.0.1:9/hook"
    assert payload == {"content": msg}
    text = res.content[0].text
    assert "sent" in text and str(len(msg)) in text and "embed=False" in text


def test_send_embed_posts_embed_payload():
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    with _ok() as m:
        res = run(s.call_tool("send", {"message": "hi", "embed": True}))
    _, payload = m.call_args[0]
    assert payload["embeds"][0]["description"] == "hi"
    assert "embed=True" in res.content[0].text


def test_send_reports_truncation():
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    with _ok() as m:
        res = run(s.call_tool("send", {"message": "x" * 2500}))
    _, payload = m.call_args[0]
    assert len(payload["content"]) == 2000
    assert "truncated" in res.content[0].text


def test_send_reports_http_failure_as_error():
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    with patch.object(
        server.discord, "send_to_webhook", return_value=(False, "HTTP 400: bad")
    ):
        with pytest.raises(ToolError) as ei:
            run(s.call_tool("send", {"message": "hi"}))
    assert "HTTP 400" in str(ei.value)


def test_send_rejects_empty_message():
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    with patch.object(server.discord, "send_to_webhook") as m:
        with pytest.raises(ToolError):
            run(s.call_tool("send", {"message": "   "}))
    m.assert_not_called()


def test_send_never_prints_to_stdout(capsys):
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    with _ok():
        run(s.call_tool("send", {"message": "hi"}))
    assert capsys.readouterr().out == ""


# --- entry point ------------------------------------------------------------


def test_main_builds_server_from_env_and_exposes_app(monkeypatch):
    monkeypatch.setenv("NOTIFY_HUMAN_WEBHOOK_URL", "http://127.0.0.1:9/hook")
    monkeypatch.setattr(server, "_run_stdio", lambda app: None)
    server.main()
    assert server._last_server is not None
    assert server._last_server.name == "notify-human"
