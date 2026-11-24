from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import video as common
from tools import workflow_series as ws
from tools import workflow_video as wv
from tools.lib import video_providers


class FakeBackend:


    def __init__(self):
        self.routes = {}
        self.calls = []

    def add(self, path: str, *responses) -> None:
        self.routes[path] = deque(responses)

    def __call__(self, method: str, url: str, token, **kwargs):
        path = urlsplit(url).path
        self.calls.append((method, path, kwargs))
        if method != "GET":
            raise AssertionError(f"recovery must not submit: {method} {path}")
        if path not in self.routes or not self.routes[path]:
            raise AssertionError(f"unexpected request: {method} {url}")
        responses = self.routes[path]
        response = responses.popleft() if len(responses) > 1 else responses[0]
        if isinstance(response, BaseException):
            raise response
        return response

    @property
    def paths(self) -> list[str]:
        return [path for _, path, _ in self.calls]

    def count(self, path: str) -> int:
        return self.paths.count(path)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class WorkflowRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task_file = self.root / "task.json"
        self.out = self.root / "out.mp4"
        self.fake = FakeBackend()

    def tearDown(self):
        self.temp.cleanup()

    def make_state(self, **updates) -> dict:
        state = {
            "version": 1,
            "protocol": "comfy_workflow_v1",
            "prompt_id": "p1",
            "phase": "submitted",
            "workflow_id": "wf",
            "base_url": "https://example.test",
            "view_path": "/api/comfy/proxy/view",
            "out": str(self.out),
            "created_at": "2026-11-22T01:49:08Z",
            "http_post_count": 1,
        }
        state.update(updates)
        self.task_file.write_text(json.dumps(state), encoding="utf-8")
        return state

    def args(self, **updates) -> argparse.Namespace:
        value = argparse.Namespace(
            task_file=str(self.task_file), out=str(self.out), timeout=0,
            interval=0, require_audio=False, poll_style="result",
            recover_stale=True,
        )
        for key, item in updates.items():
            setattr(value, key, item)
        return value

    def saved_state(self) -> dict:
        return json.loads(self.task_file.read_text(encoding="utf-8"))

    def poll(self, args=None):
        with patch.object(wv, "_http", new=self.fake), patch.object(
                wv.common, "_validate",
                return_value={"has_audio": True, "decode_ok": True, "duration_s": 14.0}):
            return wv.cmd_poll(args or self.args())

    def add_empty_recovery(self) -> None:
        self.fake.add("/api/concurrent/assets", {"success": True, "assets": []})
        self.fake.add("/api/images", [])

    def test_result_500_empty_history_and_no_asset_stops_without_post(self):
        self.make_state()
        self.add_empty_recovery()
        self.fake.add("/api/workflow/result",
                      wv.WorkflowBackendError("HTTP 500", http_status=500))
        self.fake.add("/api/comfy/proxy/history", {})
        with self.assertRaises(wv.WorkflowRecoveryError):
            self.poll()
        state = self.saved_state()
        self.assertEqual(state["phase"], "submitted")
        self.assertEqual(state["backend_status"], "STALE_OR_UNAVAILABLE")
        self.assertFalse(self.out.exists())
        self.assertEqual(self.fake.count("/api/workflow/result"), 1)
        self.assertEqual(self.fake.count("/api/comfy/proxy/history"), 1)

    def test_pending_past_120_seconds_then_succeeds_without_history_or_post(self):
        for resumed in (False, True):
            with self.subTest(resumed=resumed):
                self.out.unlink(missing_ok=True)
                self.fake = FakeBackend()
                self.make_state()
                if resumed:
                    self.add_empty_recovery()
                pending = {"success": True, "pending": True,
                           "prompt_id": "p1", "results": []}
                complete = {"success": True, "pending": False, "prompt_id": "p1",
                            "results": [{"type": "video", "url": "/output/2026/a.mp4",
                                         "filename": "a.mp4"}]}
                self.fake.add("/api/workflow/result", *([pending] * 13), complete)
                self.fake.add("/output/2026/a.mp4", b"live-video")
                clock = FakeClock()
                with patch.object(wv.time, "monotonic", new=clock.monotonic), \
                        patch.object(wv.time, "sleep", new=clock.sleep), \
                        patch.object(wv.common, "_save_state"):
                    result = self.poll(self.args(
                        recover_stale=resumed, timeout=900, interval=10))
                self.assertEqual(result["phase"], "complete")
                self.assertEqual(clock.now, 130)
                self.assertEqual(clock.sleeps, [10] * 13)
                self.assertEqual(self.fake.count("/api/workflow/result"), 14)
                self.assertEqual(self.fake.count("/api/comfy/proxy/history"), 0)
                self.assertEqual(self.fake.count("/api/concurrent/assets"),
                                 1 if resumed else 0)
                self.assertEqual(self.saved_state()["http_post_count"], 1)

    def test_direct_empty_history_is_not_treated_as_running(self):
        self.make_state(last_poll_style="history")
        self.add_empty_recovery()
        self.fake.add("/api/comfy/proxy/history", {})
        with self.assertRaises(wv.WorkflowRecoveryError):
            self.poll(self.args(poll_style="history"))
        self.assertEqual(self.fake.count("/api/workflow/result"), 0)
        self.assertEqual(self.saved_state()["history_confirmed"], False)

    def test_exact_concurrent_asset_recovers_and_validates(self):
        self.make_state()
        self.fake.add("/api/concurrent/assets", {"assets": [{
            "localFile": "1_a.mp4", "originalFile": "a.mp4",
            "promptId": "p1", "workflowId": "wf",
            "url": "/output/concurrent/1_a.mp4",
        }]})
        self.fake.add("/output/concurrent/1_a.mp4", b"recovered-video")
        result = self.poll()
        self.assertEqual(result["phase"], "complete")
        self.assertEqual(result["recovery_source"], "concurrent_assets")
        self.assertEqual(self.out.read_bytes(), b"recovered-video")
        self.assertEqual(self.saved_state()["phase"], "complete")
        self.assertEqual(self.fake.paths,
                         ["/api/concurrent/assets", "/output/concurrent/1_a.mp4"])

    def test_saved_result_url_recovers_without_history(self):
        self.make_state(result_url="/output/2026/a.mp4")
        self.fake.add("/api/concurrent/assets", {"assets": []})
        self.fake.add("/output/2026/a.mp4", b"saved-result")
        result = self.poll()
        self.assertEqual(result["recovery_source"], "saved_result_url")
        self.assertEqual(self.out.read_bytes(), b"saved-result")
        self.assertEqual(self.fake.count("/api/images"), 0)
        self.assertEqual(self.fake.count("/api/workflow/result"), 0)

    def test_multiple_exact_assets_and_directory_candidates_are_ambiguous(self):
        self.make_state()
        assets = [
            {"promptId": "p1", "workflowId": "wf", "originalFile": "a.mp4",
             "url": "/output/concurrent/a.mp4"},
            {"promptId": "p1", "workflowId": "wf", "originalFile": "b.mp4",
             "url": "/output/concurrent/b.mp4"},
        ]
        self.fake.add("/api/concurrent/assets", {"assets": assets})
        self.fake.add("/api/images", [
            {"relativePath": "concurrent/a.mp4"},
            {"relativePath": "concurrent/b.mp4"},
        ])
        self.fake.add("/api/workflow/result", {"pending": True, "results": []})
        with self.assertRaises(wv.WorkflowBackendError):
            self.poll()
        self.assertEqual(self.saved_state()["recovery"]["status"], "ambiguous")
        self.assertFalse(self.out.exists())
        self.assertNotIn("/output/concurrent/a.mp4", self.fake.paths)
        self.assertNotIn("/output/concurrent/b.mp4", self.fake.paths)

    def test_unique_output_listing_alone_is_never_claimed(self):
        self.make_state()
        self.fake.add("/api/concurrent/assets", {"assets": []})
        self.fake.add("/api/images", [{"relativePath": "2026/only-one.mp4"}])
        self.fake.add("/api/workflow/result", {"pending": True, "results": []})
        with self.assertRaises(wv.WorkflowBackendError):
            self.poll()
        self.assertNotIn("/output/2026/only-one.mp4", self.fake.paths)
        self.assertFalse(self.out.exists())

    def test_result_500_uses_completed_history(self):
        self.make_state()
        self.fake.add("/api/workflow/result",
                      wv.WorkflowBackendError("HTTP 500", http_status=500))
        self.fake.add("/api/comfy/proxy/history", {"p1": {
            "status": {"status_str": "success", "completed": True},
            "outputs": {"9": {"images": [{
                "filename": "a.mp4", "subfolder": "2026", "type": "output",
            }]}},
        }})
        self.fake.add("/api/comfy/proxy/view", b"history-video")
        result = self.poll(self.args(recover_stale=False))
        self.assertEqual(result["phase"], "complete")
        self.assertEqual(self.out.read_bytes(), b"history-video")
        self.assertEqual(self.fake.paths, [
            "/api/workflow/result", "/api/comfy/proxy/history", "/api/comfy/proxy/view",
        ])

    def test_result_and_history_500_still_recover_exact_asset(self):
        self.make_state()
        self.fake.add("/api/workflow/result",
                      wv.WorkflowBackendError("HTTP 500", http_status=500))
        self.fake.add("/api/comfy/proxy/history",
                      wv.WorkflowBackendError("HTTP 500", http_status=500))
        self.fake.add("/api/concurrent/assets", {"assets": [{
            "promptId": "p1", "workflowId": "wf", "originalFile": "a.mp4",
            "url": "/output/concurrent/a.mp4",
        }]})
        self.fake.add("/output/concurrent/a.mp4", b"durable-video")
        result = self.poll(self.args(recover_stale=False))
        self.assertEqual(result["recovery_source"], "concurrent_assets")
        self.assertEqual(self.out.read_bytes(), b"durable-video")

    def test_live_history_allows_existing_task_to_continue(self):
        self.make_state()
        self.add_empty_recovery()
        self.fake.add(
            "/api/workflow/result",
            wv.WorkflowBackendError("HTTP 500", http_status=500),
            {"pending": False, "prompt_id": "p1", "results": [
                {"type": "video", "url": "/output/2026/a.mp4", "filename": "a.mp4"},
            ]},
        )
        self.fake.add("/api/comfy/proxy/history", {"p1": {
            "status": {"status_str": "running", "completed": False}, "outputs": {},
        }})
        self.fake.add("/output/2026/a.mp4", b"live-video")
        result = self.poll(self.args(timeout=2))
        self.assertEqual(result["recovery_source"], "result")
        self.assertEqual(self.fake.count("/api/workflow/result"), 2)
        self.assertEqual(self.fake.count("/api/comfy/proxy/history"), 1)
        self.assertEqual(self.out.read_bytes(), b"live-video")

    def test_pending_stops_only_at_900_second_deadline(self):
        self.make_state()
        self.fake.add("/api/workflow/result", {"pending": True, "results": []})
        clock = FakeClock()
        with patch.object(wv.time, "monotonic", new=clock.monotonic), \
                patch.object(wv.time, "sleep", new=clock.sleep), \
                patch.object(wv.common, "_save_state"):
            with self.assertRaisesRegex(wv.WorkflowBackendError, "轮询超时"):
                self.poll(self.args(recover_stale=False, timeout=900, interval=10))
        self.assertEqual(clock.now, 900)
        self.assertEqual(clock.sleeps, [10] * 90)
        self.assertEqual(self.fake.count("/api/workflow/result"), 91)
        self.assertEqual(self.fake.count("/api/comfy/proxy/history"), 0)
        self.assertEqual(self.fake.count("/api/concurrent/assets"), 0)
        self.assertFalse(self.out.exists())


class FakeProvider:
    PROVIDER_ID = "fake"
    ADAPTER_VERSION = "test"

    def __init__(self):
        self.submit_calls = []
        self.poll_calls = []
        self.verify_calls = []

    def verify_task_inputs(self, task_file, **kwargs):
        self.verify_calls.append((task_file, kwargs))

    def submit_segment(self, **kwargs):
        self.submit_calls.append(kwargs)
        return {"phase": "submitted", "task_id": "new-task"}

    def poll_segment(self, **kwargs):
        self.poll_calls.append(kwargs)
        return {"task_id": "task-1", "sha256": "abc", "media": {}}


class SeriesRecoveryTests(unittest.TestCase):
    def test_series_distinguishes_existing_task_from_new_submission(self):
        for resumed in (False, True):
            with self.subTest(resumed=resumed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                task_file = root / "task.json"
                (root / "prompt.md").write_text("prompt", encoding="utf-8")
                if resumed:
                    task_file.write_text("{}", encoding="utf-8")
                entry = {
                    "segment_id": "SEG002", "duration_s": 14,
                    "task_file": "task.json", "output_file": "out.mp4",
                    "prompt_file": "prompt.md", "images": [], "audio": [],
                }
                provider = FakeProvider()
                context = ws.SegmentExecutionContext(
                    root=root, queue={"cloud_config": "cloud.json"}, entry=entry,
                    by_id={}, run_state={"segments": {}},
                    args=argparse.Namespace(timeout=1, interval=0), output=root / "out.mp4",
                    provider=provider,
                )
                with patch.object(ws, "_images", return_value=[]):
                    _, receipt = ws.GeneratedSegmentStrategy().execute(context)
                self.assertEqual(len(provider.submit_calls), 0 if resumed else 1)
                self.assertEqual(len(provider.verify_calls), 1 if resumed else 0)
                self.assertIs(provider.poll_calls[0]["resumed"], resumed)
                self.assertEqual(receipt["task_id"], "task-1")
                if resumed:
                    self.assertEqual(
                        provider.verify_calls[0][1]["prompt_sha256"],
                        hashlib.sha256(b"prompt").hexdigest())

    def test_recover_without_task_cannot_submit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = FakeProvider()
            entry = {
                "segment_id": "SEG002", "operation": "recover",
                "task_file": "missing.json", "output_file": "out.mp4",
                "prompt_file": "prompt.md", "images": [], "audio": [],
            }
            context = ws.SegmentExecutionContext(
                root=root, queue={"cloud_config": "cloud.json"}, entry=entry,
                by_id={}, run_state={"segments": {}},
                args=argparse.Namespace(timeout=1, interval=0), output=root / "out.mp4",
                provider=provider,
            )
            with patch.object(ws, "_images", return_value=[]):
                with self.assertRaisesRegex(ws.SeriesError, "禁止新 POST"):
                    ws.GeneratedSegmentStrategy().execute(context)
            self.assertEqual(provider.submit_calls, [])
            self.assertEqual(provider.poll_calls, [])

    def test_reuse_operation_needs_no_second_reuse_flag(self):
        entries = [
            {"segment_id": "SEG001", "operation": "reuse"},
            {"segment_id": "SEG002", "operation": "generate"},
        ]
        args = argparse.Namespace(
            authorized_segment=["SEG002"], confirmation=["SEG002=VC001"])
        authorized, last, confirmations = ws._authorized_scope(entries, args)
        self.assertEqual(authorized, {"SEG002"})
        self.assertEqual(last, 1)
        self.assertEqual(confirmations, {"SEG002": "VC001"})

    def test_series_has_no_direct_autodl_adapter_dependency(self):
        self.assertFalse(hasattr(ws, "wv"))
        self.assertFalse(hasattr(ws, "common"))


class ProviderSelectionTests(unittest.TestCase):
    def test_explicit_provider_and_protocol_resolve_autodl(self):
        queue = {"video_provider": "autodl"}
        config = {"protocol": "comfy_workflow_v1"}
        self.assertIs(video_providers.select_adapter(queue, config), wv)

    def test_unknown_missing_conflicting_or_incompatible_provider_is_rejected(self):
        cases = [
            ({"video_provider": "other"}, {"protocol": "comfy_workflow_v1"}),
            ({}, {"protocol": "comfy_workflow_v1"}),
            ({"video_provider": "autodl"}, {}),
            ({"video_provider": "autodl"}, {"video_provider": "other"}),
            ({"video_provider": "autodl"}, {"protocol": "different_protocol"}),
        ]
        for queue, config in cases:
            with self.subTest(queue=queue, config=config):
                with self.assertRaises(video_providers.ProviderSelectionError):
                    video_providers.select_adapter(queue, config)

    def test_adapter_binding_computes_current_install(self):
        binding = video_providers.adapter_binding(wv)
        self.assertEqual(binding["video_provider"], "autodl")
        self.assertEqual(binding["video_provider_adapter_version"], wv.ADAPTER_VERSION)
        self.assertEqual(len(binding["video_provider_adapter_sha256"]), 64)

    def test_run_state_rejects_provider_or_adapter_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue_file = root / "queue.json"
            queue_file.write_text("{}", encoding="utf-8")
            run_file = root / "run.json"
            binding = {"video_provider": "autodl", "video_provider_adapter_version": "1"}
            run_file.write_text(json.dumps({
                "queue_sha256": ws.sha256_file(queue_file), **binding, "segments": {},
            }), encoding="utf-8")
            with self.assertRaises(ws.SeriesError):
                ws._load_run_state(run_file, queue_file, {
                    **binding, "video_provider": "other",
                })

    def test_run_state_rejects_missing_provider_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue_file = root / "queue.json"
            queue_file.write_text("{}", encoding="utf-8")
            run_file = root / "run.json"
            run_file.write_text(json.dumps({
                "queue_sha256": ws.sha256_file(queue_file), "segments": {},
            }), encoding="utf-8")
            with self.assertRaises(ws.SeriesError):
                ws._load_run_state(run_file, queue_file, {
                    "video_provider": "autodl",
                    "video_provider_adapter_version": "1",
                })


class HttpEnvelopeTests(unittest.TestCase):
    def test_output_listing_may_be_top_level_json_list_only_when_requested(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'[{"relativePath":"a.mp4"}]'

        opener = unittest.mock.Mock()
        opener.open.return_value = Response()
        with patch.object(common.urllib.request, "build_opener", return_value=opener):
            value = common._http("GET", "https://example.test/api/images", None,
                                 allow_list=True)
            self.assertEqual(value, [{"relativePath": "a.mp4"}])
            with self.assertRaises(common.BackendError):
                common._http("GET", "https://example.test/api/images", None)


if __name__ == "__main__":
    unittest.main()
