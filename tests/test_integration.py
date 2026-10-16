"""End-to-end HTTP: a real socket round-trip against a local webhook stand-in.

The autouse guard in conftest blocks every non-loopback destination, so these
tests prove the real urllib path (headers, method, JSON body) without touching
Discord. Loopback connects are allowed by design.
"""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

from notify_human_mcp import discord


class _CapturingHandler(BaseHTTPRequestHandler):
    captured: ClassVar = []  # class-level: survives across handler instances

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        type(self).captured.append(
            {
                "path": self.path,
                "method": self.command,
                "content_type": self.headers.get("Content-Type"),
                "user_agent": self.headers.get("User-Agent"),
                "body": body,
            }
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):  # silence the server
        pass


class _Webhook:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _CapturingHandler)
        _CapturingHandler.captured = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.url = f"http://{host}:{port}/webhook"
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_plain_message_round_trips_over_a_real_socket():
    with _Webhook() as hook:
        payload = discord.build_plain_payload("14:05 | repo — thing done ✅")
        ok, detail = discord.send_to_webhook(hook.url, payload)

    assert ok is True, detail
    (req,) = _CapturingHandler.captured
    assert req["method"] == "POST"
    assert req["path"] == "/webhook"
    assert req["content_type"] == "application/json"
    assert req["user_agent"].startswith("notify-human-mcp/")
    assert json.loads(req["body"]) == {"content": "14:05 | repo — thing done ✅"}


def test_embed_payload_round_trips_over_a_real_socket():
    with _Webhook() as hook:
        payload = discord.build_embed_payload("long body", color=0x00FF00)
        ok, detail = discord.send_to_webhook(hook.url, payload)

    assert ok is True, detail
    (req,) = _CapturingHandler.captured
    sent = json.loads(req["body"])
    assert sent["embeds"][0]["description"] == "long body"
    assert sent["embeds"][0]["color"] == 0x00FF00


def test_closed_port_fails_cleanly():
    # Bind then close to guarantee the port is refused, not silently reused.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    dead_port = s.getsockname()[1]
    s.close()

    ok, detail = discord.send_to_webhook(
        f"http://127.0.0.1:{dead_port}/hook", discord.build_plain_payload("x")
    )
    assert ok is False
    assert "Connection refused" in detail or "refused" in detail.lower()
