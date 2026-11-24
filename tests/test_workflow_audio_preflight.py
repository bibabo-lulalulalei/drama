from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import workflow_series


class WorkflowAudioPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        for name in ("a.wav", "b.wav", "c.wav"):
            (self.root / name).write_bytes(b"placeholder")

    def tearDown(self):
        self.temp.cleanup()

    def validate(self, durations):
        issues = []
        entry = {"audio": list(durations)}
        with patch.object(
                workflow_series, "media_duration",
                side_effect=lambda path: durations[Path(path).name]):
            total = workflow_series._audio_duration_total(
                self.root, entry,
                lambda code, detail: issues.append({"code": code, "detail": detail}),
            )
        return total, issues

    def test_actual_total_at_fifteen_seconds_is_valid(self):
        total, issues = self.validate({"a.wav": 4.0, "b.wav": 3.0, "c.wav": 8.0})
        self.assertEqual(15.0, total)
        self.assertEqual([], issues)

    def test_actual_total_over_fifteen_seconds_is_blocked(self):
        total, issues = self.validate({"a.wav": 4.216893, "b.wav": 3.496893, "c.wav": 8.296893})
        self.assertAlmostEqual(16.010679, total)
        self.assertIn("audio_duration_total", {item["code"] for item in issues})

    def test_each_audio_must_be_two_to_fifteen_seconds(self):
        _, issues = self.validate({"a.wav": 1.9, "b.wav": 3.0, "c.wav": 8.0})
        self.assertIn("audio_duration", {item["code"] for item in issues})


if __name__ == "__main__":
    unittest.main()
