"""Tests for health check HTTP server."""

from __future__ import annotations

import json
import urllib.request

from keypad6160.health import start_health_server


class TestHealthServer:
    def test_health_returns_200(self):
        server = start_health_server(0)  # port 0 = OS picks a free port
        try:
            port = server.server_address[1]
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/health")
            assert resp.status == 200
            data = json.loads(resp.read())
            assert data == {"status": "ok"}
        finally:
            server.shutdown()

    def test_unknown_path_returns_404(self):
        server = start_health_server(0)
        try:
            port = server.server_address[1]
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/other")
                assert False, "Should have raised"
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            server.shutdown()
