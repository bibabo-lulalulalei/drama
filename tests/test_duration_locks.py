from __future__ import annotations

import hashlib
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
    def plan(semantics: str | None, lightweight: bool = False) -> dict:
        scale = {
            "episode_count": 1,
        }
        if semantics is not None:
            scale["duration_semantics"] = semantics
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

    def write_storyboard(self, duration_s: int | float) -> None:
        path = self.episode / "02_分镜/storyboard_ep_1.json"
        path.write_text(json.dumps({
            "episode_id": "ep_1",
            "duration_s": duration_s,
            "duration_display": f"{duration_s}秒",
            "shots": [],
            "segments": [],
        }, ensure_ascii=False), encoding="utf-8")

    def write_storyboard_with_timing(
        self,
        shot_durations: list[float],
        segment_duration: int,
        storyboard_duration: int,
    ) -> None:
        storyboard_dir = self.episode / "02_分镜"
        director_path = storyboard_dir / "导演总控卡_ep_1.md"
        director_path.write_text("# 导演总控卡\n", encoding="utf-8")
        headers = [f"列{index}" for index in range(1, 16)]
        (storyboard_dir / "分镜_完整分镜表_ep_1.md").write_text(
            "| " + " | ".join(headers) + " |\n"
            "| " + " | ".join("---" for _ in headers) + " |\n",
            encoding="utf-8",
        )
        shot_ids = [f"E01S01-SHOT{index:03d}" for index in range(1, len(shot_durations) + 1)]
        data = {
            "episode_id": "ep_1",
            "duration_s": storyboard_duration,
            "duration_display": f"{storyboard_duration}秒",
            "director_control_card": "episodes/ep_1/02_分镜/导演总控卡_ep_1.md",
            "source_markdown": "episodes/ep_1/02_分镜/分镜_完整分镜表_ep_1.md",
            "shots": [
                {
                    "shot_id": shot_id,
                    "segment_id": "SEG001",
                    "scene_id": "E01S01",
                    "duration_s": duration,
                }
                for shot_id, duration in zip(shot_ids, shot_durations)
            ],
            "segments": [{
                "segment_id": "SEG001",
                "duration_s": segment_duration,
                "shot_ids": shot_ids,
                "shot_mode": "edited",
                "density_profile": "micro_film",
                "tail_mode": "cuttable_completion",
                "reference_input_plan": [],
                "keyframe_requests": [],
            }],
        }
        (storyboard_dir / "storyboard_ep_1.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8",
        )

    def write_delivery(self, duration_s: int | float, lightweight: bool) -> None:
        master = "episodes/ep_1/05_成片/master.mp4"
        master_bytes = b"test media placeholder"
        (self.root / master).write_bytes(master_bytes)
        report = "episodes/ep_1/05_成片/质检_基础_无字幕_v01_ep_1.json"
        (self.root / report).write_text(json.dumps({
            "status": "passed",
            "media_file": master,
            "media_sha256": hashlib.sha256(master_bytes).hexdigest(),
            "expected": {"duration_s": duration_s},
            "observed": {"duration_s": duration_s},
        }, ensure_ascii=False), encoding="utf-8")
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
            "duration_display": f"{int(round(float(duration_s)))}秒",
            "clean_master": master,
            "outputs": [master],
            "basic_qc_reports": [report],
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

    def test_reference_exact_duration_plan_needs_no_duration_semantics(self):
        plan = self.plan(None)
        plan_issues: list[dict] = []
        expected = check_plan_durations(self.root, plan, plan_issues)
        self.assertEqual({"ep_1": 10}, expected)
        self.assertNotIn("duration_semantics_invalid", self.codes(plan_issues))

        self.write_storyboard(10)
        storyboard_issues: list[dict] = []
        check_storyboards(self.root, expected, plan, storyboard_issues)
        self.assertNotIn("storyboard_duration_mismatch", self.codes(storyboard_issues))

        self.write_delivery(10, lightweight=False)
        delivery_issues: list[dict] = []
        check_delivery(self.root, expected, delivery_issues, lightweight=False)
        self.assertNotIn("delivery_duration_mismatch", self.codes(delivery_issues))

    def test_reference_exact_duration_plan_rejects_downstream_mismatch(self):
        plan = self.plan(None)
        expected = self.expected_durations(plan)
        self.write_storyboard(9)
        storyboard_issues: list[dict] = []
        check_storyboards(self.root, expected, plan, storyboard_issues)
        self.assertIn("storyboard_duration_mismatch", self.codes(storyboard_issues))

        self.write_delivery(9, lightweight=False)
        delivery_issues: list[dict] = []
        check_delivery(self.root, expected, delivery_issues, lightweight=False)
        self.assertIn("delivery_duration_mismatch", self.codes(delivery_issues))

    def test_fractional_shots_retimed_to_integer_segment_close_exactly(self):
        plan = self.plan("planning_estimate")
        expected = self.expected_durations(plan)
        self.write_storyboard_with_timing([2.4, 2.6], 5, 5)
        issues: list[dict] = []
        check_storyboards(self.root, expected, plan, issues)
        self.assertNotIn("segment_duration_mismatch", self.codes(issues))
        self.assertNotIn("shot_duration_total_mismatch", self.codes(issues))

    def test_fractional_shot_sum_cannot_round_into_integer_segment(self):
        plan = self.plan("planning_estimate")
        expected = self.expected_durations(plan)
        self.write_storyboard_with_timing([2.2, 2.2], 4, 4)
        issues: list[dict] = []
        check_storyboards(self.root, expected, plan, issues)
        self.assertIn("segment_duration_mismatch", self.codes(issues))
        self.assertIn("shot_duration_total_mismatch", self.codes(issues))

    def test_reference_exact_duration_plan_rejects_fractional_confirmed_duration(self):
        plan = self.plan(None)
        plan["scale_plan"].update({
            "episode_durations_s": [9.6],
            "episode_duration_displays": ["10秒"],
            "total_duration_s": 9.6,
            "total_duration_display": "10秒",
        })
        issues: list[dict] = []
        expected = check_plan_durations(self.root, plan, issues)
        self.assertEqual({"ep_1": None}, expected)
        self.assertIn("episode_duration_integer_invalid", self.codes(issues))
        self.assertIn("total_duration_integer_invalid", self.codes(issues))

    def test_lightweight_plan_rejects_fractional_confirmed_duration(self):
        plan = self.plan("planning_estimate", lightweight=True)
        plan["scale_plan"].update({
            "episode_durations_s": [9.6],
            "episode_duration_displays": ["10秒"],
            "total_duration_s": 9.6,
            "total_duration_display": "10秒",
        })
        issues: list[dict] = []
        check_plan_durations(self.root, plan, issues)
        self.assertIn("episode_duration_integer_invalid", self.codes(issues))
        self.assertIn("total_duration_integer_invalid", self.codes(issues))

    def test_legacy_user_locked_fractional_duration_keeps_read_compatibility(self):
        plan = self.plan("user_locked")
        plan["scale_plan"].update({
            "episode_durations_s": [9.6],
            "episode_duration_displays": ["10秒"],
            "total_duration_s": 9.6,
            "total_duration_display": "10秒",
        })
        issues: list[dict] = []
        expected = check_plan_durations(self.root, plan, issues)
        self.assertEqual({"ep_1": 10}, expected)
        self.assertNotIn("episode_duration_integer_invalid", self.codes(issues))
        self.assertNotIn("total_duration_integer_invalid", self.codes(issues))

    def test_reference_exact_duration_rejects_fractional_storyboard_total(self):
        plan = self.plan(None)
        expected = self.expected_durations(plan)
        self.write_storyboard(9.6)
        issues: list[dict] = []
        check_storyboards(self.root, expected, plan, issues)
        self.assertIn("storyboard_duration_mismatch", self.codes(issues))

    def test_invalid_shot_numbers_cannot_close_by_arithmetic_or_nan_comparison(self):
        plan = self.plan("planning_estimate")
        expected = self.expected_durations(plan)
        cases = [
            [6, -2],
            [True, 3],
            [float("nan"), 4],
            [float("inf"), 4],
            ["4", 4],
            [0, 4],
        ]
        for shot_durations in cases:
            with self.subTest(shot_durations=shot_durations):
                self.write_storyboard_with_timing(shot_durations, 4, 4)
                issues: list[dict] = []
                check_storyboards(self.root, expected, plan, issues)
                self.assertIn("shot_duration_invalid", self.codes(issues))

    def test_delivery_uses_media_tolerance_instead_of_integer_rounding(self):
        plan = self.plan(None)
        expected = self.expected_durations(plan)
        self.write_delivery(9.5, lightweight=False)
        issues: list[dict] = []
        check_delivery(self.root, expected, issues, lightweight=False)
        self.assertNotIn("delivery_duration_mismatch", self.codes(issues))
        self.assertNotIn("basic_qc_report_duration_mismatch", self.codes(issues))

        self.write_delivery(9.49, lightweight=False)
        issues = []
        check_delivery(self.root, expected, issues, lightweight=False)
        self.assertIn("delivery_duration_mismatch", self.codes(issues))

    def test_delivery_requires_nonempty_qc_bound_to_current_master_bytes(self):
        plan = self.plan(None)
        expected = self.expected_durations(plan)
        self.write_delivery(10, lightweight=False)
        manifest_path = self.episode / "05_成片/delivery_manifest_ep_1.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["basic_qc_reports"] = []
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        issues: list[dict] = []
        check_delivery(self.root, expected, issues, lightweight=False)
        self.assertIn("basic_qc_reports_count_invalid", self.codes(issues))

        self.write_delivery(10, lightweight=False)
        (self.root / "episodes/ep_1/05_成片/master.mp4").write_bytes(b"changed media")
        issues = []
        check_delivery(self.root, expected, issues, lightweight=False)
        self.assertIn("basic_qc_report_media_hash_mismatch", self.codes(issues))

    def test_non_default_segment_duration_requires_real_exception_reason(self):
        plan = self.plan("planning_estimate")
        expected = self.expected_durations(plan)
        self.write_storyboard_with_timing([2.4, 2.6], 5, 5)
        issues: list[dict] = []
        check_storyboards(self.root, expected, plan, issues)
        self.assertIn("segment_duration_exception_reason_missing", self.codes(issues))

        storyboard_path = self.episode / "02_分镜/storyboard_ep_1.json"
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
        storyboard["segments"][0]["duration_exception_reason"] = "自然切点向上取整后由既有表演吸收"
        storyboard_path.write_text(json.dumps(storyboard, ensure_ascii=False), encoding="utf-8")
        issues = []
        check_storyboards(self.root, expected, plan, issues)
        self.assertNotIn("segment_duration_exception_reason_missing", self.codes(issues))


if __name__ == "__main__":
    unittest.main()
