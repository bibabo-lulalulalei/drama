from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.drama_lint_video_confirmations import (
    ConfirmationEnvelopeRule,
    ConfirmationLedger,
    ConfirmationReporter,
    GenerationConfirmation,
    SegmentAuthorizationRule,
    SegmentCatalog,
    SerialRunBindingRule,
)


class VideoConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.path = Path("video_manifest_ep_1.json")
        self.issues = []
        self.reporter = ConfirmationReporter(self.path, self.issues)
        self.catalog = SegmentCatalog([
            {"segment_id": "SEG001", "episode_segment_index": 1},
            {"segment_id": "SEG002", "episode_segment_index": 2},
        ], self.reporter)
        self.item = {
            "confirmation_id": "VC001",
            "confirmation_source": "batch_preview",
            "confirmation_transport": "user_message",
            "interaction_ask_call_id": "local:vc001",
            "attempt": 1,
            "batch_start_segment_index": 1,
            "batch_end_segment_index": 1,
        }

    def parse(self):
        return ConfirmationEnvelopeRule(self.reporter, lightweight=False).parse(
            self.item, 0, ConfirmationLedger(self.reporter), self.catalog)

    def test_single_new_segment_confirmation_is_accepted(self):
        record = self.parse()
        self.assertIsNotNone(record)
        self.assertNotIn("video_generation_confirmation_too_large", {item["code"] for item in self.issues})

    def test_multi_segment_confirmation_is_rejected(self):
        self.item["batch_end_segment_index"] = 2
        record = self.parse()
        self.assertIsNone(record)
        self.assertIn("video_generation_confirmation_too_large", {item["code"] for item in self.issues})

    def test_serial_confirmation_still_requires_real_continuous_tail(self):
        segment = {
            "segment_id": "SEG002",
            "h3_conversion": {
                "skill_name": "h3-prompt-writing",
                "invocation_channel": "host_skill_tool",
                "invoked": True,
            },
            "incoming_seam": {
                "seam_mode": "continuous",
                "previous_tail_frame_id": "FRM002",
            },
            "reference_inputs": [],
        }
        SegmentAuthorizationRule()._validate_segment(segment, self.reporter)
        self.assertIn("video_continuous_tail_not_ready", {item["code"] for item in self.issues})

    def test_real_tail_reference_satisfies_continuous_gate(self):
        segment = {
            "segment_id": "SEG002",
            "h3_conversion": {
                "skill_name": "h3-prompt-writing",
                "invocation_channel": "host_skill_tool",
                "invoked": True,
            },
            "incoming_seam": {
                "seam_mode": "continuous",
                "previous_tail_frame_id": "FRM002",
            },
            "reference_inputs": [{
                "source_type": "frame",
                "source_id": "FRM002",
                "role": "previous_tail_reference",
                "file": "tail.png",
            }],
        }
        SegmentAuthorizationRule()._validate_segment(segment, self.reporter)
        self.assertNotIn("video_continuous_tail_not_ready", {item["code"] for item in self.issues})


class SerialRunBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / "episodes/ep_1/04_视频片段"
        self.folder.mkdir(parents=True)
        self.cloud = self.root / "00_制作控制/h3_cloud.json"
        self.cloud.parent.mkdir(parents=True)
        self.cloud.write_bytes(b'{"protocol":"comfy_workflow_v1"}')
        self.queue_path = self.folder / "串行执行.json"
        self.path = self.folder / "video_manifest_ep_1.json"
        self.queue = {
            "video_provider": "autodl",
            "cloud_config": "00_制作控制/h3_cloud.json",
            "segments": [{
                "segment_id": "SEG001", "operation": "generate",
                "confirmation_id": "VC001", "duration_s": 14,
            }],
        }
        self.segment = {
            "segment_id": "SEG001", "duration_s": 14, "video_provider": "autodl",
        }
        self.write_queue()
        self.queue_sha256 = hashlib.sha256(self.queue_path.read_bytes()).hexdigest()
        self.cloud_sha256 = hashlib.sha256(self.cloud.read_bytes()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def write_queue(self):
        self.queue_path.write_text(json.dumps(self.queue), encoding="utf-8")

    def validate(self):
        item = {
            "confirmation_id": "VC001",
            "run_plan_file": "episodes/ep_1/04_视频片段/串行执行.json",
            "run_plan_sha256": self.queue_sha256,
            "video_provider": "autodl",
            "video_provider_adapter_version": "1",
            "video_provider_adapter_sha256": "a" * 64,
            "cloud_config_sha256": self.cloud_sha256,
        }
        record = GenerationConfirmation(
            item=item, confirmation_index=0, start=1, end=1, attempt=1,
            confirmation_id="VC001", confirmed_at=None, serial_run=True,
            planning_preview=False, expected_segments=[self.segment],
        )
        issues = []
        SerialRunBindingRule().validate(record, ConfirmationReporter(self.path, issues))
        return {entry["code"] for entry in issues}

    def test_real_queue_and_cloud_hashes_close(self):
        self.assertEqual(set(), self.validate())

    def test_stale_queue_bytes_and_provider_mismatch_are_rejected(self):
        self.queue_path.write_text(
            self.queue_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertIn("video_serial_run_plan_hash_mismatch", self.validate())
        self.write_queue()
        self.queue["video_provider"] = "other"
        self.write_queue()
        self.assertIn("video_generation_provider_queue_mismatch", self.validate())

    def test_cloud_queue_confirmation_and_segment_binding_mismatches_are_rejected(self):
        self.cloud.write_bytes(b"changed")
        self.queue["segments"][0]["confirmation_id"] = "VC000"
        self.segment["video_provider"] = "other"
        self.write_queue()
        codes = self.validate()
        self.assertIn("video_generation_cloud_config_hash_mismatch", codes)
        self.assertIn("video_serial_run_confirmation_mismatch", codes)
        self.assertIn("video_generation_provider_segment_mismatch", codes)


if __name__ == "__main__":
    unittest.main()
