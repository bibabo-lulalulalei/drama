from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import drama_lint_video


class VideoPlanLintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.fixed = self.root / "fixed.png"
        self.fixed.write_bytes(b"fixed")
        self.tail = self.root / "tail.png"
        self.tail.write_bytes(b"tail")
        self.path = self.root / "video_manifest_ep_1.json"
        self.tail_input = {
            "order": 1,
            "source_type": "frame",
            "source_id": "FRM002",
            "file": "tail.png",
            "role": "previous_tail_reference",
            "adopt": "真实尾帧的连续状态",
            "exclude": "其他帧或占位图",
        }
        self.segment = {
            "segment_id": "SEG003",
            "incoming_seam": {
                "seam_mode": "continuous",
                "previous_segment_id": "SEG002",
            },
            "reference_inputs": [
                self.tail_input,
                {
                    "order": 2,
                    "source_type": "asset",
                    "source_id": "CHR001:v01",
                    "file": "fixed.png",
                    "role": "identity_reference",
                    "adopt": "身份",
                    "exclude": "排版",
                },
            ],
        }

    def tearDown(self):
        self.temp.cleanup()

    def validate(self):
        issues = []
        items = drama_lint_video.video_reference_inputs(self.segment, self.path, issues)
        orders, roles = drama_lint_video.ordered_inputs(
            self.root, items, drama_lint_video.REFERENCE_ROLES,
            "reference", self.path, issues)
        return issues, orders, roles

    def test_real_tail_and_fixed_inputs_pass_in_order(self):
        issues, orders, roles = self.validate()
        self.assertEqual([], issues)
        self.assertEqual([1, 2], orders)
        self.assertEqual({"previous_tail_reference", "identity_reference"}, roles)

    def test_planned_future_tail_is_rejected(self):
        self.segment["planned_reference_inputs"] = [{
            "order": 1,
            "previous_tail_of": "SEG002",
            "file": "future.png",
            "role": "previous_tail_reference",
            "input_status": "awaiting_actual_tail",
        }]
        issues, _, _ = self.validate()
        self.assertIn("video_planned_tail_not_allowed", {item["code"] for item in issues})

    def test_empty_planned_tail_field_is_rejected(self):
        self.segment["planned_reference_inputs"] = []
        issues, _, _ = self.validate()
        self.assertIn("video_planned_tail_not_allowed", {item["code"] for item in issues})

    def test_future_tail_cannot_be_smuggled_into_actual_inputs(self):
        future = dict(self.tail_input)
        future["previous_tail_of"] = "SEG002"
        future["input_status"] = "awaiting_actual_tail"
        self.segment["reference_inputs"][0] = future
        issues, _, _ = self.validate()
        self.assertIn("video_planned_tail_in_actual_inputs", {item["code"] for item in issues})

    def test_missing_real_tail_fails(self):
        self.tail.unlink()
        issues, _, _ = self.validate()
        self.assertIn("reference_input_file_missing", {item["code"] for item in issues})

    def test_missing_fixed_input_still_fails(self):
        self.fixed.unlink()
        issues, _, _ = self.validate()
        self.assertIn("reference_input_file_missing", {item["code"] for item in issues})


if __name__ == "__main__":
    unittest.main()
