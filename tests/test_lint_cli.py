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
from scripts import drama_lint


class LintCliTests(unittest.TestCase):
    def test_legacy_arguments_remain_accepted_as_no_op_compatibility_flags(self):
        args = drama_lint.parse_args([
            "--fix",
            "--changed-file", "episodes/ep_1/02_分镜/storyboard_ep_1.json",
            "--changed-file", "episodes/ep_1/02_分镜/分镜_阅读稿_ep_1.md",
        ])
        self.assertTrue(args.fix)
        self.assertEqual(len(args.changed_file), 2)
        self.assertEqual(args.stage, "skill")

    def test_legacy_arguments_still_run_selected_check_and_emit_normal_result(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(drama_lint, "check_skill_package", return_value=None) as check:
            output = io.StringIO()
            with redirect_stdout(output):
                code = drama_lint.main([
                    directory,
                    "--stage", "skill",
                    "--fix",
                    "--changed-file", "any.md",
                ])
        self.assertEqual(code, 0)
        check.assert_called_once()
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["release_ready"])
        self.assertEqual(payload["summary"]["error_count"], 0)


if __name__ == "__main__":
    unittest.main()
