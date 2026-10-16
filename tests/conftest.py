"""Keep every test hermetic: no ambient env vars, no real network."""

import socket

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


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Hard guarantee for DoD #4: any real socket connect fails the test.

    Mocked urlopen never opens a socket, so a green suite plus this guard proves
    zero real network — including nothing ever reaching discord.com.
    """

    def _blocked(*args, **kwargs):
        raise AssertionError("test attempted a real network connection")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
