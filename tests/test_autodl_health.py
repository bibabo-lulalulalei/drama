from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import autodl_instance as autodl


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.stream = io.BytesIO(body)
        self.status = status

    def read(self, size=-1):
        return self.stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class AutoDLHealthTests(unittest.TestCase):
    def test_json_requirement_parser_accepts_scalar_and_rejects_invalid(self):
        self.assertEqual(autodl._health_json_requirement("running=true"), ("running", True))
        self.assertEqual(
            autodl._health_json_requirement('data.ready="yes"'), ("data.ready", "yes"))
        for value in ("running", "=true", "running={}", "running=not-json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                autodl._health_json_requirement(value)
        with self.assertRaises(ValueError):
            autodl._health_config(None, "running=true")

    def test_http_200_alone_is_not_ready_when_comfy_is_starting(self):
        body = json.dumps({"running": False, "starting": True}).encode()
        with patch.object(autodl.urllib.request, "urlopen", return_value=FakeResponse(body)):
            with self.assertRaises(autodl.AutoDLError) as caught:
                autodl._health_once("https://example.test/api/comfy/status", 1, 200,
                                    ("running", True))
        self.assertTrue(caught.exception.retryable)
        self.assertNotIn("starting", str(caught.exception))

    def test_ready_requires_exact_json_boolean(self):
        body = json.dumps({"running": True, "starting": False}).encode()
        with patch.object(autodl.urllib.request, "urlopen", return_value=FakeResponse(body)) as request:
            result = autodl._health_once(
                "https://example.test/api/comfy/status", 1, 200, ("running", True))
        self.assertEqual(result["observed_json"], {"path": "running", "value": True})
        self.assertEqual(result["required_json"], {"path": "running", "equals": True})
        self.assertNotIn("Authorization", request.call_args.args[0].headers)

    def test_invalid_or_missing_json_is_retryable_without_echoing_body(self):
        for body in (b"not-json-secret", b'{"other":"secret"}', b'{"running":1}'):
            with self.subTest(body=body), patch.object(
                    autodl.urllib.request, "urlopen", return_value=FakeResponse(body)):
                with self.assertRaises(autodl.AutoDLError) as caught:
                    autodl._health_once("https://example.test/status", 1, 200,
                                        ("running", True))
            self.assertTrue(caught.exception.retryable)
            self.assertNotIn("secret", str(caught.exception))

    def test_wait_health_uses_fixed_interval_and_passes_json_requirement(self):
        expected = {"reachable": True, "observed_json": {"path": "running", "value": True}}
        starting = autodl.AutoDLError("starting", retryable=True)
        with patch.object(autodl, "_health_once",
                          side_effect=[starting, starting, expected]) as check, \
                patch.object(autodl, "_pause") as pause:
            result = autodl._wait_health(
                "https://example.test/status", 123.0, 10, 1, 200, ("running", True))
        self.assertEqual(result, expected)
        self.assertEqual(check.call_count, 3)
        self.assertEqual(check.call_args.args[3], ("running", True))
        self.assertEqual(pause.call_args_list, [call(123.0, 10), call(123.0, 10)])

    def test_health_budget_is_independent_but_capped_by_power_deadline(self):
        url = "https://example.test/api/comfy/status"
        for power_deadline, expected_deadline in (
                (None, 400.0), (350.0, 350.0), (500.0, 400.0)):
            with self.subTest(power_deadline=power_deadline):
                run = object.__new__(autodl._PowerRun)
                run.args = argparse.Namespace(
                    health_interval=10, health_timeout=300,
                    request_timeout=30, health_http_status=200)
                run.spec = autodl.POWER_ON
                run.health_url = url
                run.health_json = ("running", True)
                run.deadline = power_deadline
                run.result = {"power_on_post_count": 1, "status_before": "shutdown"}
                with patch.object(autodl.time, "monotonic", return_value=100.0), \
                        patch.object(autodl, "_wait_health", return_value={"reachable": True}) as wait:
                    run.finish()
                self.assertEqual(wait.call_args.args[:3], (url, expected_deadline, 10))
                self.assertEqual(wait.call_args.args[3:], (
                    30, 200, ("running", True)))


if __name__ == "__main__":
    unittest.main()
