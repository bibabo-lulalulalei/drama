from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
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
        self.fake.add("/output/2026/a.mp4", b"saved-result")
        result = self.poll()
        self.assertEqual(result["recovery_source"], "saved_result_url")
        self.assertEqual(self.out.read_bytes(), b"saved-result")
        self.assertEqual(self.fake.count("/api/concurrent/assets"), 0)
        self.assertEqual(self.fake.count("/api/images"), 0)
        self.assertEqual(self.fake.count("/api/workflow/result"), 0)

    def test_saved_result_url_has_priority_over_concurrent_asset(self):
        self.make_state(result_url="/output/saved.mp4")
        self.fake.add("/output/saved.mp4", b"saved-result")
        result = self.poll()
        self.assertEqual(result["recovery_source"], "saved_result_url")
        self.assertEqual(self.out.read_bytes(), b"saved-result")
        self.assertEqual(self.fake.paths, ["/output/saved.mp4"])

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
        return {"task_id": "task-1", "sha256": "abc", "media": {"duration_s": 14.0}}


class ProviderRequestRecoveryTests(unittest.TestCase):
    def test_existing_task_verifies_complete_original_request_tuple(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "cloud.json"
            config.write_text(json.dumps({
                "protocol": "comfy_workflow_v1",
                "workflow_id": "wf",
                "base_url": "https://example.test",
                "aspect_ratio": "16:9 (Widescreen)",
                "megapixels": 1.0,
            }), encoding="utf-8")
            prompt = root / "prompt.md"
            prompt.write_text("integrated_multimodal_description: <Picture 1>", encoding="utf-8")
            image = root / "image.png"
            image.write_bytes(b"image")
            entry = {"segment_id": "SEG001", "h3_mode": "Ref2VA", "duration_s": 14}
            task_file = root / "task.json"
            output = root / "out.mp4"
            kwargs = {
                "config": str(config), "entry": entry, "images": [str(image)],
                "audio": [], "prompt_file": str(prompt), "output": str(output),
            }
            with patch.object(wv, "_http", return_value={"prompt_id": "p1"}) as http:
                wv.submit_segment(task_file=str(task_file), **kwargs)
                self.assertEqual(http.call_count, 1)
                http.reset_mock()
                wv.verify_task_inputs(str(task_file), **kwargs)
                http.assert_not_called()
                for mutation, expected in (
                    ({"duration_s": 15}, "seconds"),
                    ({"aspect_ratio": "9:16 (Portrait Widescreen)"}, "aspect_ratio"),
                    ({"megapixels": 0.5}, "megapixels"),
                ):
                    with self.subTest(mutation=mutation):
                        changed = dict(entry, **mutation)
                        with self.assertRaisesRegex(wv.WorkflowBackendError, expected):
                            wv.verify_task_inputs(
                                str(task_file), **dict(kwargs, entry=changed))
                        http.assert_not_called()
                with self.assertRaisesRegex(wv.WorkflowBackendError, "out"):
                    wv.verify_task_inputs(
                        str(task_file), **dict(kwargs, output=str(root / "other.mp4")))


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
                    verification = provider.verify_calls[0][1]
                    self.assertEqual(verification["entry"]["segment_id"], "SEG002")
                    self.assertEqual(Path(verification["output"]).resolve(), (root / "out.mp4").resolve())
                    self.assertEqual(Path(verification["prompt_file"]).resolve(), (root / "prompt.md").resolve())

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

    def test_returned_media_must_match_requested_duration_within_encoding_tolerance(self):
        cases = [
            ({}, "缺少有限非负"),
            ({"duration_s": float("nan")}, "缺少有限非负"),
            ({"duration_s": 13.49}, "超过 0.5 秒"),
        ]
        for media, message in cases:
            with self.subTest(media=media), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "prompt.md").write_text("prompt", encoding="utf-8")
                entry = {
                    "segment_id": "SEG001", "duration_s": 14,
                    "task_file": "task.json", "output_file": "out.mp4",
                    "prompt_file": "prompt.md", "images": [], "audio": [],
                }
                provider = FakeProvider()
                provider.poll_segment = lambda **kwargs: {
                    "task_id": "task-1", "sha256": "abc", "media": media,
                }
                context = ws.SegmentExecutionContext(
                    root=root, queue={"cloud_config": "cloud.json"}, entry=entry,
                    by_id={}, run_state={"segments": {}},
                    args=argparse.Namespace(timeout=1, interval=0), output=root / "out.mp4",
                    provider=provider,
                )
                with patch.object(ws, "_images", return_value=[]):
                    with self.assertRaisesRegex(ws.SeriesError, message):
                        ws.GeneratedSegmentStrategy().execute(context)

    def test_returned_media_accepts_half_second_encoding_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "prompt.md").write_text("prompt", encoding="utf-8")
            entry = {
                "segment_id": "SEG001", "duration_s": 14,
                "task_file": "task.json", "output_file": "out.mp4",
                "prompt_file": "prompt.md", "images": [], "audio": [],
            }
            provider = FakeProvider()
            provider.poll_segment = lambda **kwargs: {
                "task_id": "task-1", "sha256": "abc",
                "media": {"duration_s": 14.5},
            }
            context = ws.SegmentExecutionContext(
                root=root, queue={"cloud_config": "cloud.json"}, entry=entry,
                by_id={}, run_state={"segments": {}},
                args=argparse.Namespace(timeout=1, interval=0), output=root / "out.mp4",
                provider=provider,
            )
            with patch.object(ws, "_images", return_value=[]):
                _, receipt = ws.GeneratedSegmentStrategy().execute(context)
            self.assertEqual(receipt["media"]["duration_s"], 14.5)

    def test_direct_execution_rejects_unknown_operation_and_multiple_generates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = {
                "segment_id": "SEG001", "operation": "unknown",
                "output_file": "out.mp4", "task_file": "task.json",
            }
            with self.assertRaisesRegex(ws.SeriesError, "拒绝落入生成路径"):
                ws._execute_one(
                    root, {"cloud_config": "cloud.json"}, entry, {},
                    {"segments": {}}, root / "run.json",
                    argparse.Namespace(timeout=1, interval=0), FakeProvider())
        entries = [
            {"segment_id": "SEG001", "operation": "generate"},
            {"segment_id": "SEG002", "operation": "generate"},
        ]
        args = argparse.Namespace(
            authorized_segment=["SEG001", "SEG002"],
            confirmation=["SEG001=VC001", "SEG002=VC002"])
        with self.assertRaisesRegex(ValueError, "最多一个新 generate"):
            ws._authorized_scope(entries, args)

    def test_series_has_no_direct_autodl_adapter_dependency(self):
        self.assertFalse(hasattr(ws, "wv"))
        self.assertFalse(hasattr(ws, "common"))


class SeriesQueueContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.queue_file = self.root / "queue.json"
        self.run_file = self.root / "run.json"
        self.binding = {"video_provider": "fake", "video_provider_adapter_version": "1"}
        (self.root / "old.mp4").write_bytes(b"old-output")
        (self.root / "old.png").write_bytes(b"old-tail")
        self.output_sha = ws.sha256_file(self.root / "old.mp4")
        self.tail_sha = ws.sha256_file(self.root / "old.png")
        self.old_receipt = {
            "phase": "tail_ready",
            "output_file": "old.mp4",
            "output_sha256": self.output_sha,
            "tail": {
                "file": "old.png",
                "sha256": self.tail_sha,
                "source_video_sha256": self.output_sha,
            },
        }
        old_entry = self.entry("SEG001", "generate")
        self.queue_file.write_text(json.dumps({"segments": [old_entry]}), encoding="utf-8")
        self.run_file.write_text(json.dumps({
            "queue_sha256": ws.sha256_file(self.queue_file),
            **self.binding,
            "segments": {"SEG001": self.old_receipt},
        }), encoding="utf-8")
        self.current_queue = {
            "run_state_file": "run.json",
            "cloud_config": "cloud.json",
            "segments": [self.entry("SEG001", "reuse"), self.entry("SEG002", "generate")],
        }
        self.queue_file.write_text(json.dumps(self.current_queue), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def entry(segment_id, operation):
        return {
            "segment_id": segment_id,
            "operation": operation,
            "duration_s": 14,
            "output_file": "old.mp4" if segment_id == "SEG001" else "new.mp4",
            "task_file": f"{segment_id}.task.json",
            "tail_file": "old.png" if segment_id == "SEG001" else "new.png",
            "prompt_file": f"{segment_id}.md",
            "images": [],
            "audio": [],
        }

    def test_next_queue_version_preserves_history_and_superseded_hash(self):
        previous_sha = json.loads(self.run_file.read_text(encoding="utf-8"))["queue_sha256"]
        state = ws._load_run_state(
            self.run_file, self.queue_file, self.binding, self.root, self.current_queue)
        self.assertEqual(state["queue_sha256"], ws.sha256_file(self.queue_file))
        self.assertEqual(state["superseded_queue_sha256"], [previous_sha])
        self.assertEqual(state["segments"]["SEG001"], self.old_receipt)

    def test_queue_change_cannot_reauthorize_or_redirect_history(self):
        for mutation in ("operation", "output", "order", "incomplete", "missing_sha"):
            with self.subTest(mutation=mutation):
                queue = json.loads(json.dumps(self.current_queue))
                state = json.loads(self.run_file.read_text(encoding="utf-8"))
                self.run_file.write_text(json.dumps(state), encoding="utf-8")
                if mutation == "operation":
                    queue["segments"][0]["operation"] = "generate"
                elif mutation == "output":
                    queue["segments"][0]["output_file"] = "other.mp4"
                elif mutation == "order":
                    queue["segments"].reverse()
                elif mutation == "incomplete":
                    state["segments"]["SEG001"]["phase"] = "complete"
                    self.run_file.write_text(json.dumps(state), encoding="utf-8")
                else:
                    state.pop("queue_sha256")
                    self.run_file.write_text(json.dumps(state), encoding="utf-8")
                self.queue_file.write_text(json.dumps(queue), encoding="utf-8")
                with self.assertRaises(ws.SeriesError):
                    ws._load_run_state(
                        self.run_file, self.queue_file, self.binding, self.root, queue)

    def test_second_run_reuses_first_segment_and_generates_only_new_segment(self):
        provider = FakeProvider()
        args = argparse.Namespace(
            queue=str(self.queue_file), project_root=str(self.root),
            authorized_segment=["SEG002"], confirmation=["SEG002=VC002"],
            timeout=1, interval=0,
        )
        new_tail = {
            "file": "new.png", "sha256": "new-tail", "source_video_sha256": "abc",
        }
        with patch.object(ws, "cmd_preflight", return_value={
                "ok": True, "project_root": str(self.root)}) as preflight, \
                patch.object(ws, "_resolve_provider", return_value=(provider, self.binding, None)), \
                patch.object(ws, "_extract_tail", return_value=new_tail):
            result = ws.cmd_run(args)
        self.assertTrue(preflight.call_args.args[0].require_confirmed)
        self.assertTrue(result["ok"])
        self.assertEqual(result["completed_segments"], ["SEG001", "SEG002"])
        self.assertEqual(len(provider.submit_calls), 1)
        self.assertEqual(provider.submit_calls[0]["entry"]["segment_id"], "SEG002")
        state = json.loads(self.run_file.read_text(encoding="utf-8"))
        self.assertEqual(state["segments"]["SEG001"]["phase"], "reused_tail_ready")
        self.assertEqual(state["segments"]["SEG002"]["confirmation_id"], "VC002")
        self.assertEqual(state["queue_sha256"], ws.sha256_file(self.queue_file))


class ExecutionConfirmationBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / "episodes/ep_1/04_视频片段"
        self.folder.mkdir(parents=True)
        self.queue_file = self.folder / "串行执行.json"
        self.manifest_file = self.folder / "video_manifest_ep_1.json"
        self.binding = {
            "video_provider": "autodl",
            "video_provider_adapter_version": "1",
            "video_provider_adapter_sha256": "a" * 64,
            "cloud_config_sha256": "b" * 64,
        }
        self.queue = {
            "schema_version": "1.0",
            "video_provider": "autodl",
            "segments": [{
                "segment_id": "SEG001", "operation": "generate",
                "confirmation_id": "VC001", "duration_s": 14,
            }],
        }
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def confirmation(self, confirmation_id="VC001", *, supersedes=None):
        return {
            "confirmation_id": confirmation_id,
            "batch_start_segment_index": 1,
            "batch_end_segment_index": 1,
            "planned_video_count": 1,
            "duration_s": 14,
            "model": "H3",
            "interaction_ask_result": "generate",
            "interaction_ask_call_id": "local:confirmation-1",
            "user_message": "确认生成当前 SEG",
            "confirmed_at": "2026-11-25T00:00:00+00:00",
            "confirmation_transport": "user_message",
            "execution_mode": "serial_real_tail_chain",
            "run_plan_file": "episodes/ep_1/04_视频片段/串行执行.json",
            "run_plan_sha256": ws.sha256_file(self.queue_file),
            "supersedes_confirmation_ids": supersedes or [],
            **self.binding,
        }

    def save(self, confirmations=None):
        self.queue_file.write_text(json.dumps(self.queue), encoding="utf-8")
        manifest = {
            "segments": [{
                "segment_id": "SEG001", "episode_segment_index": 1,
                "duration_s": 14, "video_provider": "autodl",
            }],
            "generation_confirmations": confirmations or [self.confirmation()],
        }
        self.manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    def verify(self, binding=None):
        ws._verify_execution_confirmations(
            self.queue_file, self.root, self.queue, binding or self.binding)

    def test_initial_preflight_returns_binding_without_confirmation_cycle(self):
        self.manifest_file.unlink()
        prompt = self.folder / "prompt.md"
        prompt.write_text("compiled H3 prompt", encoding="utf-8")
        image = self.folder / "input.png"
        image.write_bytes(b"image")
        relative = lambda path: path.relative_to(self.root).as_posix()
        self.queue["segments"][0].update({
            "prompt_file": relative(prompt),
            "images": [{"file": relative(image)}],
            "audio": [],
            "output_file": "episodes/ep_1/04_视频片段/out.mp4",
            "task_file": "episodes/ep_1/04_视频片段/task.json",
            "tail_file": "episodes/ep_1/04_视频片段/tail.png",
        })
        self.queue_file.write_text(json.dumps(self.queue), encoding="utf-8")
        provider = SimpleNamespace(prompt_markers=lambda prompt, records: {})
        base_args = {"queue": str(self.queue_file), "project_root": str(self.root),
                     "require_ready": False}
        with patch.object(ws, "_resolve_provider",
                          return_value=(provider, self.binding, None)):
            initial = ws.cmd_preflight(argparse.Namespace(
                **base_args, require_confirmed=False))
            execution = ws.cmd_preflight(argparse.Namespace(
                **base_args, require_confirmed=True))
        self.assertTrue(initial["ok"])
        self.assertEqual(ws.sha256_file(self.queue_file), initial["run_plan_sha256"])
        self.assertEqual("autodl", initial["video_provider"])
        self.assertFalse(execution["ok"])
        self.assertIn("generation_confirmation_binding",
                      {item["code"] for item in execution["issues"]})

    def test_latest_confirmation_binds_real_queue_and_complete_provider_tuple(self):
        self.verify()

    def test_queue_mutation_invalidates_confirmation_bytes(self):
        self.queue_file.write_text(
            self.queue_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ws.SeriesError, "实际路径和字节"):
            self.verify()

    def test_old_confirmation_cannot_authorize_current_segment(self):
        current = self.confirmation("VC002", supersedes=["VC001"])
        current["confirmed_at"] = "2026-11-25T00:01:00+00:00"
        self.save([self.confirmation("VC001"), current])
        with self.assertRaisesRegex(ws.SeriesError, "最新有效确认"):
            self.verify()

    def test_provider_adapter_and_cloud_binding_mismatches_are_rejected(self):
        for field in self.binding:
            with self.subTest(field=field):
                binding = dict(self.binding)
                binding[field] = "changed"
                with self.assertRaises(ws.SeriesError):
                    self.verify(binding)

    def test_replaced_confirmation_must_declare_supersession(self):
        current = self.confirmation("VC002")
        current["confirmed_at"] = "2026-11-25T00:01:00+00:00"
        self.queue["segments"][0]["confirmation_id"] = "VC002"
        self.queue_file.write_text(json.dumps(self.queue), encoding="utf-8")
        current["run_plan_sha256"] = ws.sha256_file(self.queue_file)
        self.save([self.confirmation("VC001"), current])
        with self.assertRaisesRegex(ws.SeriesError, "显式替代"):
            self.verify()


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

    def test_adapter_binding_changes_when_execution_dependency_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "adapter.py"
            dependency = root / "lib/dependency.py"
            dependency.parent.mkdir()
            source.write_text("adapter = 1", encoding="utf-8")
            dependency.write_text("value = 1", encoding="utf-8")
            adapter = SimpleNamespace(
                __file__=str(source), PROVIDER_ID="fake", ADAPTER_VERSION="1",
                EXECUTION_DEPENDENCY_FILES=("lib/dependency.py",),
            )
            before = video_providers.adapter_binding(adapter)
            dependency.write_text("value = 2", encoding="utf-8")
            after = video_providers.adapter_binding(adapter)
        self.assertNotEqual(
            before["video_provider_adapter_sha256"],
            after["video_provider_adapter_sha256"],
        )

    def test_adapter_binding_rejects_dependency_outside_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "adapter.py"
            source.write_text("adapter = 1", encoding="utf-8")
            adapter = SimpleNamespace(
                __file__=str(source), PROVIDER_ID="fake", ADAPTER_VERSION="1",
                EXECUTION_DEPENDENCY_FILES=("../outside.py",),
            )
            with self.assertRaises(video_providers.ProviderSelectionError):
                video_providers.adapter_binding(adapter)

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
