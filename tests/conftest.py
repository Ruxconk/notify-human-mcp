"""Keep every test hermetic: no ambient notify-human env vars leak in."""

import pytest

NOTIFY_VARS = [
    "NOTIFY_HUMAN_WEBHOOK_URL",
    "NOTIFY_HUMAN_INSTRUCTIONS_FILE",
    "NOTIFY_HUMAN_INSTRUCTIONS_URL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in NOTIFY_VARS:
        monkeypatch.delenv(var, raising=False)
