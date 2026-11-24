from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.drama_lint import check_delivery, check_plan_durations
from scripts.drama_lint_storyboards import check_storyboards


class DurationLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.episode = self.root / "episodes/ep_1"
        (self.episode / "02_分镜").mkdir(parents=True)
        (self.episode / "05_成片").mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def plan(semantics: str, lightweight: bool = False) -> dict:
        scale = {
            "episode_count": 1,
            "duration_semantics": semantics,
        }
        if semantics == "planning_estimate" and not lightweight:
            scale.update({
                "estimated_episode_duration_ranges_s": [{"min_s": 10, "max_s": 12}],
                "estimated_episode_duration_displays": ["预估 10-12 秒"],
                "estimated_total_duration_range_s": {"min_s": 10, "max_s": 12},
                "estimated_total_duration_display": "全片预估 10-12 秒",
            })
        else:
            scale.update({
                "episode_durations_s": [10],
                "episode_duration_displays": ["10秒"],
                "total_duration_s": 10,
                "total_duration_display": "10秒",
            })
        return {
            "objective": {
                "target_stage": "final",
                "workflow_mode": "lightweight" if lightweight else "full",
            },
            "scale_plan": scale,
        }

    def expected_durations(self, plan: dict) -> dict[str, int | None]:
        return check_plan_durations(self.root, plan, [])

    def write_storyboard(self, duration_s: int) -> None:
        path = self.episode / "02_分镜/storyboard_ep_1.json"
        path.write_text(json.dumps({
            "episode_id": "ep_1",
            "duration_s": duration_s,
            "duration_display": f"{duration_s}秒",
            "shots": [],
            "segments": [],
        }, ensure_ascii=False), encoding="utf-8")

    def write_delivery(self, duration_s: int, lightweight: bool) -> None:
        master = "episodes/ep_1/05_成片/master.mp4"
        (self.root / master).write_bytes(b"test media placeholder")
        assembly = None if lightweight else {
            "confirmation_purpose": "final_assembly",
            "interaction_ask_call_id": "local:assembly-1",
            "interaction_ask_result": "proceed_assembly",
            "user_message": "确认拼接",
            "confirmed_at": "2026-01-01T00:00:00+00:00",
            "segment_ids": [],
        }
        path = self.episode / "05_成片/delivery_manifest_ep_1.json"
        path.write_text(json.dumps({
            "episode_id": "ep_1",
            "assembly_confirmation": assembly,
            "subtitle_enabled": False,
            "status": "deliverable",
            "duration_s": duration_s,
            "duration_display": f"{duration_s}秒",
            "clean_master": master,
            "outputs": [master],
            "basic_qc_reports": [],
            "source_segments": [],
        }, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def codes(issues: list[dict]) -> set[str]:
        return {item["code"] for item in issues}

    def test_planning_estimate_does_not_create_cross_stage_exact_duration_gate(self):
        plan = self.plan("planning_estimate")
        expected = self.expected_durations(plan)
        self.assertEqual({"ep_1": None}, expected)

        self.write_storyboard(9)
        storyboard_issues: list[dict] = []
        check_storyboards(self.root, expected, plan, storyboard_issues)
        self.assertNotIn("storyboard_duration_mismatch", self.codes(storyboard_issues))

        self.write_delivery(9, lightweight=False)
        delivery_issues: list[dict] = []
        check_delivery(self.root, expected, delivery_issues, lightweight=False)
        self.assertNotIn("delivery_duration_mismatch", self.codes(delivery_issues))

    def test_user_locked_storyboard_duration_mismatch_is_rejected(self):
        plan = self.plan("user_locked")
        expected = self.expected_durations(plan)
        self.assertEqual({"ep_1": 10}, expected)
        self.write_storyboard(9)
        issues: list[dict] = []
        check_storyboards(self.root, expected, plan, issues)
        self.assertIn("storyboard_duration_mismatch", self.codes(issues))

    def test_user_locked_delivery_duration_mismatch_is_rejected(self):
        plan = self.plan("user_locked")
        expected = self.expected_durations(plan)
        self.write_delivery(9, lightweight=False)
        issues: list[dict] = []
        check_delivery(self.root, expected, issues, lightweight=False)
        self.assertIn("delivery_duration_mismatch", self.codes(issues))

    def test_lightweight_delivery_duration_mismatch_is_rejected(self):
        plan = self.plan("planning_estimate", lightweight=True)
        expected = self.expected_durations(plan)
        self.assertEqual({"ep_1": 10}, expected)
        self.write_delivery(9, lightweight=True)
        issues: list[dict] = []
        check_delivery(self.root, expected, issues, lightweight=True)
        self.assertIn("delivery_duration_mismatch", self.codes(issues))

    def test_user_locked_matching_storyboard_and_delivery_pass_duration_gates(self):
        plan = self.plan("user_locked")
        expected = self.expected_durations(plan)
        self.write_storyboard(10)
        storyboard_issues: list[dict] = []
        check_storyboards(self.root, expected, plan, storyboard_issues)
        self.assertNotIn("storyboard_duration_mismatch", self.codes(storyboard_issues))

        self.write_delivery(10, lightweight=False)
        delivery_issues: list[dict] = []
        check_delivery(self.root, expected, delivery_issues, lightweight=False)
        self.assertNotIn("delivery_duration_mismatch", self.codes(delivery_issues))


if __name__ == "__main__":
    unittest.main()
