from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import drama_rollback as rollback


class RollbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.control = self.root / "00_制作控制"
        self.control.mkdir(parents=True)
        self.state_path = self.control / "制作状态.json"
        self.state = self.full_state()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def statuses(value="confirmed"):
        return {
            stage: value for stage in rollback.EPISODE_STAGES
        }

    def full_state(self):
        return {
            "revision": 3,
            "current_stage": "final",
            "current_episode": "ep_2",
            "phases": {
                stage: "confirmed" if stage != "final" else "in_progress"
                for stage in rollback.STAGES
            },
            "episodes": {
                "ep_1": {"stage_status": self.statuses()},
                "ep_2": {"stage_status": self.statuses()},
                "ep_3": {"stage_status": self.statuses("pending")},
            },
        }

    def lightweight_state(self):
        return {
            "revision": 2,
            "current_stage": "final",
            "current_episode": "ep_1",
            "phases": {
                "planning": "confirmed",
                "script": "merged",
                "assets": "merged",
                "storyboard": "merged",
                "keyframes": "merged",
                "video": "merged",
                "final": "awaiting_confirmation",
            },
            "episodes": {
                "ep_1": {"stage_status": {
                    "script": "merged",
                    "assets": "merged",
                    "storyboard": "merged",
                    "keyframes": "merged",
                    "video": "merged",
                    "final": "awaiting_confirmation",
                }},
            },
        }

    def save_state(self, state=None):
        self.state_path.write_text(
            json.dumps(self.state if state is None else state), encoding="utf-8")

    def test_later_episode_requires_explicit_cascade(self):
        with self.assertRaisesRegex(ValueError, "later episodes already progressed"):
            rollback.rollback_state(self.state, "storyboard", "ep_1")

    def test_cascade_invalidates_only_started_later_episodes(self):
        original = json.loads(json.dumps(self.state))
        updated = rollback.rollback_state(
            self.state, "storyboard", "ep_1", cascade_later_episodes=True)
        self.assertEqual(self.state, original)
        self.assertEqual(updated["revision"], 4)
        self.assertEqual(updated["current_stage"], "storyboard")
        self.assertEqual(updated["current_episode"], "ep_1")
        self.assertEqual(updated["phases"]["script"], "confirmed")
        self.assertEqual(updated["phases"]["storyboard"], "in_progress")
        self.assertEqual(updated["phases"]["video"], "invalidated")
        self.assertEqual(updated["episodes"]["ep_1"]["stage_status"]["storyboard"], "in_progress")
        self.assertEqual(updated["episodes"]["ep_1"]["stage_status"]["final"], "invalidated")
        self.assertTrue(all(
            value == "invalidated"
            for value in updated["episodes"]["ep_2"]["stage_status"].values()
        ))
        self.assertTrue(all(
            value == "pending"
            for value in updated["episodes"]["ep_3"]["stage_status"].values()
        ))

    def test_future_or_unstarted_episode_stage_is_rejected(self):
        state = self.full_state()
        state["current_episode"] = "ep_1"
        with self.assertRaisesRegex(ValueError, "future episode"):
            rollback.rollback_state(state, "script", "ep_2")
        state["episodes"]["ep_1"]["stage_status"]["video"] = "pending"
        with self.assertRaisesRegex(ValueError, "unstarted stage"):
            rollback.rollback_state(state, "video", "ep_1")

    def test_project_script_rollback_does_not_start_every_episode(self):
        updated = rollback.rollback_state(self.state, "script")
        self.assertEqual(updated["current_stage"], "script")
        self.assertIsNone(updated["current_episode"])
        self.assertEqual(updated["phases"]["script"], "in_progress")
        for episode_state in updated["episodes"].values():
            self.assertEqual(episode_state["stage_status"]["script"], "invalidated")

    def test_lightweight_non_planning_request_returns_to_final_repair(self):
        state = self.lightweight_state()
        updated = rollback.rollback_state(
            state, "video", workflow_mode="lightweight")
        self.assertEqual(updated["current_stage"], "final")
        self.assertEqual(updated["current_episode"], "ep_1")
        self.assertEqual(updated["revision"], 3)
        self.assertEqual(updated["phases"]["final"], "in_progress")
        self.assertTrue(all(
            updated["phases"][stage] == "merged"
            for stage in rollback.STAGES[1:-1]
        ))
        self.assertEqual(state["current_stage"], "final")
        self.assertEqual(state["phases"]["final"], "awaiting_confirmation")

    def test_lightweight_repair_requires_confirmed_planning(self):
        state = self.lightweight_state()
        state["phases"]["planning"] = "in_progress"
        with self.assertRaisesRegex(ValueError, "confirmed planning"):
            rollback.rollback_state(state, "video", workflow_mode="lightweight")

    def test_cli_dry_run_does_not_write_state_or_log(self):
        self.save_state()
        before = self.state_path.read_bytes()
        output = io.StringIO()
        with redirect_stdout(output):
            code = rollback.main([
                "--project-root", str(self.root),
                "--to-stage", "storyboard",
                "--episode", "ep_1",
                "--cascade-later-episodes",
                "--dry-run",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "dry_run")
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertFalse((self.control / "操作日志.jsonl").exists())

    def test_log_failure_restores_original_state(self):
        self.save_state()
        args = type("Args", (), {
            "to_stage": "storyboard",
            "episode": "ep_1",
            "cascade_later_episodes": True,
            "reason": "test",
        })()
        _, updated = rollback._load_updated_state(self.root, args)
        with patch.object(rollback, "append_log", side_effect=OSError("log failed")):
            code, error = rollback._commit(
                self.root, self.state_path, self.state, updated, args)
        self.assertEqual(code, 2)
        self.assertEqual(error["error"], "rollback_log_failed")
        self.assertTrue(error["state_restored"])
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), self.state)


if __name__ == "__main__":
    unittest.main()
