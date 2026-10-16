"""Tests for the MCP server wiring: instructions injection and the send tool."""

import asyncio
from unittest.mock import patch

import pytest

from notify_human_mcp import server

# The server module resolves ToolError across mcp 1.x/2.x; tests use the same.
from notify_human_mcp.server import ToolError


def run(coro):
    return asyncio.run(coro)


def tool_schema(tool):
    """Input schema under both SDK shapes (mcp 2.x input_schema, 1.x inputSchema)."""
    return getattr(tool, "input_schema", None) or tool.inputSchema


def result_text(res):
    """First text block under both SDK shapes (2.x CallToolResult, 1.x tuple)."""
    if isinstance(res, tuple):  # mcp 1.x: (content_blocks, structured)
        return res[0][0].text
    return res.content[0].text


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
    schema = tool_schema(tool)
    assert schema["required"] == ["message"]
    assert schema["properties"]["message"]["type"] == "string"
    assert schema["properties"]["embed"]["default"] is False


def test_send_has_a_description_for_the_llm():
    tool = run(server.build_server().list_tools())[0]
    assert tool.description and "Discord" in tool.description


def test_send_description_includes_configured_instructions_path():
    s = server.build_server(
        instructions="X", instructions_path="/etc/notify-human/instructions.md"
    )
    tool = run(s.list_tools())[0]
    assert "/etc/notify-human/instructions.md" in tool.description
    assert "already" in tool.description  # conditional: read only if not in context


def test_send_description_without_path_carries_fallback_rules():
    tool = run(server.build_server().list_tools())[0]
    assert "read" not in tool.description  # no path -> no read hint
    assert "1000" in tool.description  # short hard rules still present


def test_send_description_stays_under_context_budget():
    tool = run(
        server.build_server(
            instructions_path="/etc/notify-human/instructions.md"
        ).list_tools()
    )[0]
    assert len(tool.description) <= 700


# --- send: missing webhook --------------------------------------------------


def test_send_without_webhook_errors_and_does_not_post():
    s = server.build_server(webhook_url=None)
    with (
        patch.object(server.discord, "send_to_webhook") as m,
        pytest.raises(ToolError) as ei,
    ):
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
    text = result_text(res)
    assert "sent" in text and str(len(msg)) in text and "embed=False" in text


def test_send_embed_posts_embed_payload():
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    with _ok() as m:
        res = run(s.call_tool("send", {"message": "hi", "embed": True}))
    _, payload = m.call_args[0]
    assert payload["embeds"][0]["description"] == "hi"
    assert "embed=True" in result_text(res)


def test_send_rejects_over_limit_plain_and_posts_nothing():
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    with (
        patch.object(server.discord, "send_to_webhook") as m,
        pytest.raises(ToolError) as ei,
    ):
        run(s.call_tool("send", {"message": "x" * 2500}))
    m.assert_not_called()
    assert "2000" in str(ei.value)


def test_send_rejects_over_limit_embed_and_posts_nothing():
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    with (
        patch.object(server.discord, "send_to_webhook") as m,
        pytest.raises(ToolError) as ei,
    ):
        run(s.call_tool("send", {"message": "x" * 5000, "embed": True}))
    m.assert_not_called()
    assert "4096" in str(ei.value)


def test_over_limit_rejection_is_deterministic():
    def reason(embed):
        s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
        try:
            run(s.call_tool("send", {"message": "x" * 3000, "embed": embed}))
        except ToolError as e:
            return str(e)

    assert reason(False) == reason(False)
    assert reason(True) == reason(True)


def test_send_reports_http_failure_as_error():
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    with (
        patch.object(
            server.discord, "send_to_webhook", return_value=(False, "HTTP 400: bad")
        ),
        pytest.raises(ToolError) as ei,
    ):
        run(s.call_tool("send", {"message": "hi"}))
    assert "HTTP 400" in str(ei.value)


def test_send_rejects_empty_message():
    s = server.build_server(webhook_url="http://127.0.0.1:9/hook")
    with (
        patch.object(server.discord, "send_to_webhook") as m,
        pytest.raises(ToolError),
    ):
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


# --- template mode: send takes named fields, server assembles ---------------


def _tmpl_file(tmp_path):
    import json as _json

    p = tmp_path / "t.json"
    p.write_text(
        _json.dumps(
            {
                "header": "{time} | {repo} — {title} {status_emoji}",
                "lines": ["{ticket_line}", "model: {model} | Machine: {machine}"],
                "statuses": {"done": "✅", "blocked": "🛑"},
                "max_chars": 1000,
            }
        ),
        encoding="utf-8",
    )
    return p


def test_template_mode_send_takes_named_fields(tmp_path):
    from notify_human_mcp import template

    t = template.load_template(_tmpl_file(tmp_path))
    s = server.build_server(template=t, webhook_url="http://127.0.0.1:9/hook")
    tool = run(s.list_tools())[0]
    props = tool_schema(tool)["properties"]
    assert "message" not in props
    assert {"status", "title", "body", "ticket"} <= set(props)
    assert tool_schema(tool)["required"] == ["status", "title", "body"]


def test_template_mode_rejects_unknown_status(tmp_path):
    from notify_human_mcp import template

    t = template.load_template(_tmpl_file(tmp_path))
    s = server.build_server(template=t, webhook_url="http://127.0.0.1:9/hook")
    with (
        patch.object(server.discord, "send_to_webhook") as m,
        pytest.raises(ToolError) as ei,
    ):
        run(s.call_tool("send", {"status": "frobbed", "title": "x", "body": "y"}))
    m.assert_not_called()
    assert "done" in str(ei.value) and "blocked" in str(ei.value)


def test_template_mode_rejects_missing_required_field(tmp_path):
    from notify_human_mcp import template

    t = template.load_template(_tmpl_file(tmp_path))
    s = server.build_server(template=t, webhook_url="http://127.0.0.1:9/hook")
    with pytest.raises(Exception) as ei:
        run(s.call_tool("send", {"status": "done", "body": "y"}))
    assert "title" in str(ei.value)


def test_template_mode_posts_rendered_message(tmp_path):
    from notify_human_mcp import template

    t = template.load_template(_tmpl_file(tmp_path))
    s = server.build_server(template=t, webhook_url="http://127.0.0.1:9/hook")
    with _ok() as m:
        res = run(
            s.call_tool(
                "send",
                {"status": "done", "title": "Thing", "body": "- a", "ticket": "P-1"},
            )
        )
    _, payload = m.call_args[0]
    text = payload["content"]
    assert " — Thing ✅" in text
    assert "ticket: P-1" in text
    assert text.endswith("- a")
    assert "sent" in result_text(res)


def test_template_mode_respects_max_chars(tmp_path):
    from notify_human_mcp import template

    t = template.load_template(_tmpl_file(tmp_path))
    s = server.build_server(template=t, webhook_url="http://127.0.0.1:9/hook")
    with (
        patch.object(server.discord, "send_to_webhook") as m,
        pytest.raises(ToolError) as ei,
    ):
        run(
            s.call_tool(
                "send",
                {"status": "done", "title": "T", "body": "x" * 1500},
            )
        )
    m.assert_not_called()
    assert "1000" in str(ei.value)


def test_template_mode_embed_flag_posts_card(tmp_path):
    import json as _json

    from notify_human_mcp import template

    p = tmp_path / "t.json"
    p.write_text(
        _json.dumps(
            {
                "header": "{title} {status_emoji}",
                "lines": [],
                "statuses": {"done": "✅"},
                "embed": True,
            }
        ),
        encoding="utf-8",
    )
    t = template.load_template(p)
    s = server.build_server(template=t, webhook_url="http://127.0.0.1:9/hook")
    with _ok() as m:
        run(s.call_tool("send", {"status": "done", "title": "T", "body": "b"}))
    _, payload = m.call_args[0]
    assert "embeds" in payload
    assert payload["embeds"][0]["description"].startswith("T ✅")
