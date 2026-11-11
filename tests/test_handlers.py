"""The tool layer: argument allowlists, path quoting, streaming, and the messages."""

from __future__ import annotations

import hashlib
import json
import unittest

from support import FakeCtx, TempDirTest
from stub_bridge import StubBridge, fail, ok

from stmp.handlers import MAX_RESULT_CHARS, UsageError, run


class ArgumentTests(TempDirTest):
    def test_unknown_action_lists_the_real_ones(self):
        ctx = FakeCtx("http://127.0.0.1:1")
        with self.assertRaises(UsageError) as caught:
            run(ctx, "stmp_gmail", {"action": "archive"})
        self.assertIn("has no action 'archive'", str(caught.exception))
        self.assertIn("send", str(caught.exception))

    def test_missing_action_lists_the_actions(self):
        with self.assertRaises(UsageError) as caught:
            run(FakeCtx("http://127.0.0.1:1"), "stmp_tts", {})
        self.assertIn("needs an 'action'", str(caught.exception))
        self.assertIn("speak", str(caught.exception))

    def test_unknown_argument_is_refused_with_the_allowlist(self):
        ctx = FakeCtx("http://127.0.0.1:1")
        with self.assertRaises(UsageError) as caught:
            run(ctx, "stmp_gmail", {"action": "send", "to": ["a@b.c"], "subject": "s",
                                    "body": "b", "subjet": "typo"})
        self.assertIn("'subjet'", str(caught.exception))
        self.assertIn("threadId", str(caught.exception))

    def test_missing_required_argument_is_named(self):
        with self.assertRaises(UsageError) as caught:
            run(FakeCtx("http://127.0.0.1:1"), "stmp_gmail",
                {"action": "send", "to": ["a@b.c"]})
        self.assertIn("subject", str(caught.exception))
        self.assertIn("body", str(caught.exception))

    def test_array_must_be_an_array(self):
        with self.assertRaises(UsageError) as caught:
            run(FakeCtx("http://127.0.0.1:1"), "stmp_gmail",
                {"action": "send", "to": "a@b.c", "subject": "s", "body": "b"})
        self.assertIn("JSON array", str(caught.exception))

    def test_integer_must_be_an_integer(self):
        with self.assertRaises(UsageError):
            run(FakeCtx("http://127.0.0.1:1"), "stmp_gmail", {"action": "list", "max": "lots"})

    def test_closed_value_set_is_enforced_locally(self):
        with self.assertRaises(UsageError) as caught:
            run(FakeCtx("http://127.0.0.1:1"), "stmp_audio", {"action": "cue", "cue": "siren"})
        self.assertIn("ping, chime, alarm", str(caught.exception))

    def test_unconfigured_plugin_says_what_to_set(self):
        result = run(FakeCtx(None), "stmp_probe", {"action": "reach"})
        self.assertIn("STMP is not usable yet", result)
        self.assertIn("base_url", result)


class CallTests(TempDirTest):
    def test_path_values_are_quoted(self):
        with StubBridge({"GET /secrets/a%2Fb": ok(name="a/b")}) as stub:
            result = run(FakeCtx(stub.url), "stmp_secrets", {"action": "get", "name": "a/b"})
        self.assertIn('"ok": true', result)

    def test_only_the_actions_query_keys_are_forwarded(self):
        with StubBridge({"GET /gmail/messages": ok(messages=[])}) as stub:
            run(FakeCtx(stub.url), "stmp_gmail",
                {"action": "list", "q": "in:inbox", "max": 5})
            sent = stub.requests[0]
        self.assertEqual(sent["query"], {"q": "in:inbox", "max": "5"})

    def test_a_route_field_named_like_the_selector_is_mapped_explicitly(self):
        with StubBridge({"POST /notifications/n1/action": ok(executed="action")}) as stub:
            run(FakeCtx(stub.url), "stmp_notifications",
                {"action": "act", "id": "n1", "notification_action": "Reply"})
            sent = stub.requests[0]
        self.assertEqual(sent["body"], b'{"action": "Reply"}')

    def test_device_refusal_is_translated_with_a_next_step(self):
        with StubBridge({"POST /gmail/messages/send": fail(403, "denied", "screen locked")}) as stub:
            result = run(FakeCtx(stub.url), "stmp_gmail",
                         {"action": "send", "to": ["a@b.c"], "subject": "s", "body": "b"})
        self.assertIn("STMP call failed: denied", result)
        self.assertIn("screen locked", result)
        self.assertIn("Next:", result)
        self.assertIn("Do not retry", result)

    def test_large_result_is_truncated_with_a_reason(self):
        big = ok(blob="x" * (MAX_RESULT_CHARS + 100))
        with StubBridge({"GET /logs": big}) as stub:
            result = run(FakeCtx(stub.url), "stmp_logs", {"action": "read"})
        self.assertIn("truncated", result)
        self.assertLess(len(result), MAX_RESULT_CHARS + 400)

    def test_help_reports_contract_drift_and_records_the_device(self):
        payload = ok(
            stmp={"appVersion": "0.49.0", "appBuild": 291, "contractVersion": 5},
            plugins=[{"id": "gmail", "routes": [{"method": "GET", "path": "/gmail/profile"}]}],
            sshConnections=["box"],
        )
        with StubBridge({"GET /help": payload}) as stub:
            ctx = FakeCtx(stub.url)
            result = run(ctx, "stmp_help", {"action": "contract"})
        self.assertIn("newer than the", result)
        recorded = ctx.state.get("device")
        self.assertEqual(recorded["contract_version"], 5)
        self.assertEqual(recorded["plugins"], [{"id": "gmail", "routes": 1}])

    def test_help_does_not_rewrite_state_when_nothing_changed(self):
        payload = ok(
            stmp={"appVersion": "0.48.6", "appBuild": 282, "contractVersion": 4},
            plugins=[{"id": "probe", "routes": []}],
        )
        with StubBridge({"GET /help": payload}) as stub:
            ctx = FakeCtx(stub.url)
            run(ctx, "stmp_help", {"action": "contract"})
            first = ctx.state.get("device")
            run(ctx, "stmp_help", {"action": "contract"})
            second = ctx.state.get("device")
        self.assertEqual(first, second)


class StreamingTests(TempDirTest):
    def test_upload_sends_the_file_and_a_guessed_type(self):
        source = self.tmp / "report.csv"
        source.write_text("a,b\n1,2\n", encoding="utf-8")
        with StubBridge({"POST /drive/files/upload": ok(id="f1")}) as stub:
            run(FakeCtx(stub.url), "stmp_drive",
                {"action": "upload", "file_path": str(source)})
            sent = stub.requests[0]
        self.assertEqual(sent["query"]["name"], "report.csv")
        self.assertEqual(sent["query"]["type"], "text/csv")
        self.assertEqual(sent["body"], b"a,b\n1,2\n")
        self.assertEqual(sent["headers"]["content-type"], "text/csv")

    def test_upload_refuses_a_relative_path(self):
        with self.assertRaises(UsageError):
            run(FakeCtx("http://127.0.0.1:1"), "stmp_drive",
                {"action": "upload", "file_path": "report.csv"})

    def test_download_writes_bytes_and_reports_the_hash(self):
        payload = b"binary-ish"
        with StubBridge({"GET /drive/files/f1/content": (200, payload, "application/pdf")}) as stub:
            target = self.tmp / "out.pdf"
            result = json.loads(run(FakeCtx(stub.url, download_dir=str(self.tmp)), "stmp_drive",
                                    {"action": "download", "id": "f1", "save_to": "out.pdf"}))
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(result["bytes"], len(payload))
        self.assertEqual(result["sha256"], hashlib.sha256(payload).hexdigest())

    def test_download_refuses_a_missing_parent_directory(self):
        with self.assertRaises(UsageError):
            run(FakeCtx("http://127.0.0.1:1", download_dir=str(self.tmp)), "stmp_drive",
                {"action": "download", "id": "f1", "save_to": "no/out.pdf"})


if __name__ == "__main__":
    unittest.main()
