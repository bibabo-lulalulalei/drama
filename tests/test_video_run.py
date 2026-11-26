from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import video_run


class VideoRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / "episodes/ep_1/04_视频片段"
        self.folder.mkdir(parents=True)
        self.run_file = self.folder / "串行执行.json"
        cloud = self.root / "00_制作控制/h3_cloud.json"
        cloud.parent.mkdir(parents=True)
        cloud.write_text(json.dumps({"base_url": "https://example.test/"}), encoding="utf-8")
        self.data = {
            "schema_version": "1.0",
            "video_provider": "autodl",
            "cloud_config": "00_制作控制/h3_cloud.json",
            "run_state_file": "episodes/ep_1/04_视频片段/串行运行状态.json",
            "power": {"instance_uuid": "pro-test", "timeout_s": 1200},
            "poll": {"timeout_s": 900, "interval_s": 10},
            "segments": [
                self.segment("SEG001", "reuse", None),
                self.segment("SEG002", "recover", "VC001"),
                self.segment("SEG003", "generate", "VC002"),
            ],
        }
        self.task_file = self.folder / "任务_SEG002_v01_ep_1.json"
        self.data["segments"][1]["task_file"] = (
            "episodes/ep_1/04_视频片段/任务_SEG002_v01_ep_1.json")
        self.task_file.write_text("{}", encoding="utf-8")
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def segment(segment_id, operation, confirmation):
        return {
            "segment_id": segment_id,
            "operation": operation,
            "confirmation_id": confirmation,
        }

    def save(self):
        self.run_file.write_text(json.dumps(self.data), encoding="utf-8")

    def test_fixed_path_and_json_fields_fill_complete_managed_command(self):
        argv, log, _ = video_run.build_command(self.root, "ep_1", True)
        self.assertEqual(self.run_file, self.folder / "串行执行.json")
        self.assertEqual(log, self.folder / "串行运行.log")
        self.assertEqual(argv[3], "run-managed")
        self.assertIn("--execute", argv)
        self.assertEqual(argv[argv.index("--confirm-power") + 1], "pro-test")
        self.assertNotIn("SEG001", argv)
        self.assertIn("SEG002", argv)
        self.assertIn("SEG003", argv)
        self.assertIn("SEG002=VC001", argv)
        self.assertIn("SEG003=VC002", argv)
        self.assertEqual(argv[argv.index("--health-url") + 1], "https://example.test/api/comfy/status")
        self.assertEqual(argv[argv.index("--health-json") + 1], "running=true")
        self.assertEqual(argv[argv.index("--health-interval") + 1], "10")
        self.assertEqual(argv[argv.index("--health-timeout") + 1], "300")
        self.assertEqual(argv[argv.index("--power-timeout") + 1], "1200")
        self.assertEqual(argv[argv.index("--timeout") + 1], "900")
        self.assertEqual(argv[argv.index("--interval") + 1], "10")

    def test_explicit_env_file_is_forwarded_to_both_managed_layers(self):
        argv, _, _ = video_run.build_command(
            self.root, "ep_1", True, "config/custom.env")
        self.assertEqual(argv[3:5], ["--env-file", "config/custom.env"])
        self.assertEqual(argv[5], "run-managed")
        series = argv.index(str(video_run.SKILL_ROOT / "tools/workflow_series.py"))
        self.assertEqual(argv[series + 1:series + 5], [
            "--env-file", "config/custom.env", "run", "--queue",
        ])

    def test_default_is_offline_preflight_without_process_or_log(self):
        binding = {
            "ok": True,
            "run_plan_file": "episodes/ep_1/04_视频片段/串行执行.json",
            "run_plan_sha256": "a" * 64,
            "video_provider": "autodl",
            "video_provider_adapter_version": "1",
            "video_provider_adapter_sha256": "b" * 64,
            "cloud_config_sha256": "c" * 64,
        }
        with patch.object(video_run.workflow_series, "cmd_preflight", return_value=binding) as preflight, \
                patch.object(subprocess, "run") as process:
            result = video_run.run(self.root, "ep_1", False)
        self.assertFalse(preflight.call_args.args[0].require_confirmed)
        for key, value in binding.items():
            self.assertEqual(value, result[key])
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["process_started"])
        self.assertFalse((self.folder / "串行运行.log").exists())
        process.assert_not_called()

    def test_execute_runs_one_fixed_process_and_appends_fixed_log(self):
        log = self.folder / "串行运行.log"
        log.write_bytes(b"original\n")
        with patch.object(video_run.workflow_series, "cmd_preflight", return_value={"ok": True}) as preflight, \
                patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as process:
            result = video_run.run(self.root, "ep_1", True)
        self.assertTrue(preflight.call_args.args[0].require_confirmed)
        process.assert_called_once()
        self.assertEqual(process.call_args.args[0][3], "run-managed")
        self.assertEqual(result["process_exit_code"], 0)
        self.assertEqual(log.read_bytes(), b"original\n")

    def test_recover_without_original_task_stops_before_process(self):
        self.task_file.unlink()
        with patch.object(subprocess, "run") as process:
            with self.assertRaisesRegex(video_run.VideoRunError, "禁止新 POST"):
                video_run.build_command(self.root, "ep_1", True)
        process.assert_not_called()

    def test_second_new_generate_is_rejected_before_process(self):
        self.data["segments"].append(self.segment("SEG004", "generate", "VC003"))
        self.save()
        with patch.object(subprocess, "run") as process:
            with self.assertRaisesRegex(video_run.VideoRunError, "只允许一个新 generate"):
                video_run.build_command(self.root, "ep_1", True)
        process.assert_not_called()

    def test_generate_cannot_consume_tail_from_unfinished_recover(self):
        self.data["segments"][2]["images"] = [{"previous_tail_of": "SEG002"}]
        self.save()
        with self.assertRaisesRegex(video_run.VideoRunError, "未来 tail"):
            video_run.build_command(self.root, "ep_1", True)

    def test_generate_can_consume_existing_reused_tail(self):
        tail = self.folder / "tail_SEG001.png"
        tail.write_bytes(b"tail")
        self.data["segments"][0]["tail_file"] = (
            "episodes/ep_1/04_视频片段/tail_SEG001.png")
        self.data["segments"][2]["images"] = [{"previous_tail_of": "SEG001"}]
        self.save()
        argv, _, _ = video_run.build_command(self.root, "ep_1", True)
        self.assertIn("SEG003=VC002", argv)

    def test_invalid_operation_or_missing_confirmation_stops_before_process(self):
        self.data["segments"][1]["operation"] = "unknown"
        self.save()
        with patch.object(subprocess, "run") as process:
            with self.assertRaises(video_run.VideoRunError):
                video_run.build_command(self.root, "ep_1", True)
        self.data["segments"][1]["operation"] = "generate"
        self.data["segments"][1]["confirmation_id"] = ""
        self.save()
        with self.assertRaises(video_run.VideoRunError):
            video_run.build_command(self.root, "ep_1", True)
        process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
