import datetime as dt
import importlib.util
import io
import json
import pathlib
import sys
import unittest
import urllib.error

MODULE_PATH = pathlib.Path(__file__).parents[1] / "automation" / "recover-actions-runs.py"
SPEC = importlib.util.spec_from_file_location("recover_actions_runs", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeHTTPResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class SequenceOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout=30):
        self.requests.append((request.method, request.full_url))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        status, payload = item
        return FakeHTTPResponse(status, payload)


def http_error(code, payload):
    return urllib.error.HTTPError(
        "https://api.github.com/test",
        code,
        "error",
        {},
        io.BytesIO(json.dumps(payload).encode()),
    )


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 8, 6, 19, 0, tzinfo=dt.timezone.utc)

    def test_skips_self(self):
        opener = SequenceOpener([])
        api = MODULE.GitHubAPI("o/r", "t", opener=opener, sleep=lambda _: None)
        result = MODULE.recover_run(
            api,
            42,
            self_run_id=42,
            stale_minutes=60,
            now=self.now,
        )
        self.assertEqual(result["result"], "self-skipped")
        self.assertEqual(opener.requests, [])

    def test_terminal_run_is_not_modified(self):
        opener = SequenceOpener([
            (200, {"id": 1, "status": "completed", "conclusion": "success"})
        ])
        api = MODULE.GitHubAPI("o/r", "t", opener=opener, sleep=lambda _: None)
        result = MODULE.recover_run(
            api, 1, self_run_id=None, stale_minutes=60, now=self.now
        )
        self.assertEqual(result["result"], "already-terminal")
        self.assertEqual([method for method, _ in opener.requests], ["GET"])

    def test_fresh_active_run_is_not_cancelled(self):
        active = {
            "id": 4,
            "status": "in_progress",
            "created_at": "2026-08-06T18:30:00Z",
        }
        opener = SequenceOpener([(200, active)])
        api = MODULE.GitHubAPI("o/r", "t", opener=opener, sleep=lambda _: None)
        result = MODULE.recover_run(
            api, 4, self_run_id=None, stale_minutes=60, now=self.now
        )
        self.assertEqual(result["result"], "not-stale")
        self.assertFalse(result["stale"])
        self.assertEqual([method for method, _ in opener.requests], ["GET"])

    def test_force_cancel_resolves_after_normal_cancel_stays_active(self):
        active = {
            "id": 2,
            "status": "in_progress",
            "created_at": "2026-08-06T17:00:00Z",
        }
        completed = {
            "id": 2,
            "status": "completed",
            "conclusion": "cancelled",
            "created_at": "2026-08-06T17:00:00Z",
        }
        opener = SequenceOpener([
            (200, active),
            (202, {}),
            *((200, active),) * 6,
            (202, {}),
            (200, completed),
        ])
        api = MODULE.GitHubAPI("o/r", "t", opener=opener, sleep=lambda _: None)
        result = MODULE.recover_run(
            api, 2, self_run_id=None, stale_minutes=60, now=self.now
        )
        self.assertEqual(result["result"], "force-cancel-resolved")
        methods = [method for method, _ in opener.requests]
        self.assertEqual(methods.count("POST"), 2)

    def test_stale_run_attempts_delete_after_cancel_endpoints_fail(self):
        active = {
            "id": 3,
            "status": "in_progress",
            "created_at": "2026-07-23T14:00:00Z",
        }
        opener = SequenceOpener([
            (200, active),
            http_error(422, {"message": "cannot cancel"}),
            *((200, active),) * 6,
            http_error(422, {"message": "cannot force cancel"}),
            *((200, active),) * 6,
            (200, active),
            (204, {}),
            http_error(404, {"message": "not found"}),
        ])
        api = MODULE.GitHubAPI("o/r", "t", opener=opener, sleep=lambda _: None)
        result = MODULE.recover_run(
            api, 3, self_run_id=None, stale_minutes=60, now=self.now
        )
        self.assertEqual(result["result"], "delete-resolved")
        methods = [method for method, _ in opener.requests]
        self.assertIn("DELETE", methods)

    def test_server_errors_are_retried(self):
        opener = SequenceOpener([
            http_error(500, {"message": "server error"}),
            http_error(500, {"message": "server error"}),
            http_error(500, {"message": "server error"}),
            http_error(500, {"message": "server error"}),
            (202, {}),
        ])
        api = MODULE.GitHubAPI("o/r", "t", opener=opener, sleep=lambda _: None)
        response = api.cancel(9, "force-cancel")
        self.assertEqual(response.status, 202)
        self.assertEqual(len(opener.requests), 5)

    def test_run_id_parser_accepts_commas_and_spaces(self):
        self.assertEqual(MODULE.parse_run_ids(["3, 1", "2"]), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
