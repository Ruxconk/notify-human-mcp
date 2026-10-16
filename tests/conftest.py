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


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}


def _is_loopback(address):
    """True for loopback socket addresses ((host, port[, ...]) tuples)."""
    if isinstance(address, tuple) and address:
        return str(address[0]) in LOOPBACK_HOSTS
    return False


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Hard guarantee for DoD #4: no test may reach the public internet.

    Loopback stays allowed so the integration test can talk to its own local
    HTTP server; every other destination fails the test. Mocked urlopen never
    opens a socket, so a green suite proves nothing ever reached discord.com.
    """
    real_connect = socket.socket.connect
    real_create = socket.create_connection

    def _connect(self, address, *args, **kwargs):
        if _is_loopback(address):
            return real_connect(self, address, *args, **kwargs)
        raise AssertionError(f"test attempted a real network connection: {address}")

    def _create(address, *args, **kwargs):
        if _is_loopback(address):
            return real_create(address, *args, **kwargs)
        raise AssertionError(f"test attempted a real network connection: {address}")

    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket, "create_connection", _create)
