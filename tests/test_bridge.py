"""The transport: what it accepts, what it refuses, and that it never retries."""

from __future__ import annotations

import socket
import unittest

from support import ROOT  # noqa: F401 - puts the repo on sys.path
from stub_bridge import StubBridge, fail, ok

from stmp.bridge import Bridge, BridgeError, Config, ConfigError


class ConfigTests(unittest.TestCase):
    def test_missing_base_url_names_the_setting(self):
        with self.assertRaises(ConfigError) as caught:
            Config.from_settings(None)
        self.assertIn("plugins.entries.stmp.settings.base_url", str(caught.exception))

    def test_scheme_is_required(self):
        with self.assertRaises(ConfigError):
            Config.from_settings("192.168.1.20:8787")

    def test_path_is_refused_with_the_value(self):
        with self.assertRaises(ConfigError) as caught:
            Config.from_settings("http://phone.local:8787/bridge")
        self.assertIn("/bridge", str(caught.exception))

    def test_trailing_slash_is_normalised(self):
        self.assertEqual(Config.from_settings("http://phone.local:8787/").base_url,
                         "http://phone.local:8787")

    def test_timeout_below_the_approval_window_is_refused(self):
        with self.assertRaises(ConfigError) as caught:
            Config.from_settings("http://phone.local:8787", 10)
        self.assertIn("60 s approval window", str(caught.exception))

    def test_timeout_above_the_ceiling_is_refused(self):
        with self.assertRaises(ConfigError):
            Config.from_settings("http://phone.local:8787", 10_000)

    def test_timeout_accepts_a_numeric_string(self):
        self.assertEqual(Config.from_settings("http://phone.local:8787", "90").timeout, 90.0)


class CallTests(unittest.TestCase):
    def test_success_returns_the_json_body(self):
        with StubBridge({"GET /probe": ok(reached="gate passed")}) as stub:
            result = Bridge(Config.from_settings(stub.url)).call("GET", "/probe")
        self.assertTrue(result["ok"])
        self.assertEqual(result["reached"], "gate passed")

    def test_error_envelope_becomes_a_coded_error(self):
        with StubBridge({"POST /gmail/messages/send": fail(403, "caller_unverified", "no name")}) as stub:
            with self.assertRaises(BridgeError) as caught:
                Bridge(Config.from_settings(stub.url)).call("POST", "/gmail/messages/send", body={})
        self.assertEqual(caught.exception.code, "caller_unverified")
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(caught.exception.detail, "no name")

    def test_a_failed_call_is_attempted_exactly_once(self):
        with StubBridge({"POST /tts": fail(403, "denied")}) as stub:
            bridge = Bridge(Config.from_settings(stub.url))
            with self.assertRaises(BridgeError):
                bridge.call("POST", "/tts", body={"text": "hi"})
            self.assertEqual(len(stub.requests), 1)

    def test_non_json_error_is_reported_as_such(self):
        with StubBridge({"GET /logs": (500, b"<html>nope</html>", "text/html")}) as stub:
            with self.assertRaises(BridgeError) as caught:
                Bridge(Config.from_settings(stub.url)).call("GET", "/logs")
        self.assertEqual(caught.exception.code, "bad_response")
        self.assertIn("nope", caught.exception.detail)

    def test_json_body_and_query_are_sent(self):
        with StubBridge({"POST /ssh/ed25519-box": ok(exit=0)}) as stub:
            Bridge(Config.from_settings(stub.url)).call(
                "POST", "/ssh/ed25519-box", query={"dry": True}, body={"command": "uptime"}
            )
            sent = stub.requests[0]
        self.assertEqual(sent["query"], {"dry": "true"})
        self.assertEqual(sent["body"], b'{"command": "uptime"}')
        self.assertEqual(sent["headers"]["content-type"], "application/json")

    def test_nothing_is_listening_is_reported_as_unreachable(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        with self.assertRaises(BridgeError) as caught:
            Bridge(Config.from_settings(f"http://127.0.0.1:{port}")).call("GET", "/probe")
        self.assertEqual(caught.exception.code, "unreachable")

    def test_raw_bytes_are_returned_for_a_streaming_route(self):
        payload = b"\x89PNG\r\n\x1a\nfake"
        with StubBridge({"GET /drive/files/abc/content": (200, payload, "image/png")}) as stub:
            result = Bridge(Config.from_settings(stub.url)).call("GET", "/drive/files/abc/content")
        self.assertEqual(result, payload)


if __name__ == "__main__":
    unittest.main()
