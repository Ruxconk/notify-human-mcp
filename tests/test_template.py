"""Template mode: JSON template loading, validation, and exact rendering."""

import json
from datetime import datetime

import pytest

from notify_human_mcp import template

GOOD = {
    "header": "{time} | {repo} — {title} {status_emoji}",
    "lines": ["{ticket_line}", "model: {model} | Machine: {machine}"],
    "statuses": {"done": "✅", "blocked": "🛑", "question": "❓"},
    "max_chars": 1000,
}

NOW = datetime(2026, 10, 16, 14, 5)


def write_template(tmp_path, obj=None, name="t.json"):
    p = tmp_path / name
    p.write_text(json.dumps(obj if obj is not None else GOOD), encoding="utf-8")
    return p


def test_load_valid_template(tmp_path):
    t = template.load_template(write_template(tmp_path))
    assert set(t["statuses"]) == {"done", "blocked", "question"}
    assert t["max_chars"] == 1000


def test_load_rejects_invalid_json(tmp_path):
    p = tmp_path / "t.json"
    p.write_text("{nope", encoding="utf-8")
    with pytest.raises(template.TemplateError) as ei:
        template.load_template(p)
    assert "not valid JSON" in str(ei.value)


def test_load_requires_header(tmp_path):
    bad = dict(GOOD)
    del bad["header"]
    with pytest.raises(template.TemplateError) as ei:
        template.load_template(write_template(tmp_path, bad))
    assert "header" in str(ei.value)


def test_load_requires_statuses_mapping(tmp_path):
    bad = dict(GOOD)
    bad["statuses"] = ["done"]
    with pytest.raises(template.TemplateError) as ei:
        template.load_template(write_template(tmp_path, bad))
    assert "statuses" in str(ei.value)


def test_load_rejects_unknown_placeholder(tmp_path):
    bad = dict(GOOD)
    bad["header"] = "{time} | {nonsense}"
    with pytest.raises(template.TemplateError) as ei:
        template.load_template(write_template(tmp_path, bad))
    assert "nonsense" in str(ei.value)


def test_render_message_is_exact(tmp_path):
    t = template.load_template(write_template(tmp_path))
    msg = template.render_message(
        t,
        status="done",
        title="Thing done",
        body="- bullet one\n- bullet two",
        ticket="PROJ-1",
        model="mikoshi",
        now=NOW,
        repo="notify-human-mcp",
        machine="workbox",
    )
    assert msg == (
        "14:05 | notify-human-mcp — Thing done ✅\n"
        "ticket: PROJ-1\n"
        "model: mikoshi | Machine: workbox\n"
        "\n"
        "- bullet one\n- bullet two"
    )


def test_render_drops_empty_ticket_line(tmp_path):
    t = template.load_template(write_template(tmp_path))
    msg = template.render_message(
        t,
        status="blocked",
        title="Stuck",
        body="need token",
        now=NOW,
        repo="r",
        machine="m",
    )
    assert msg == ("14:05 | r — Stuck 🛑\nmodel: unknown | Machine: m\n\nneed token")


def test_shipped_examples_all_load():
    import pathlib

    examples = pathlib.Path(__file__).resolve().parent.parent / "examples"
    files = sorted(examples.glob("template-*.json"))
    assert len(files) >= 2
    for f in files:
        t = template.load_template(f)  # raises TemplateError if broken
        assert t["statuses"]
