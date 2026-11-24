from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.drama_lint_video_confirmations import (
    ConfirmationEnvelopeRule,
    ConfirmationLedger,
    ConfirmationReporter,
    SegmentAuthorizationRule,
    SegmentCatalog,
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


if __name__ == "__main__":
    unittest.main()
