from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import drama_lint_prompts


class StructuredDirectorDraftLintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "draft.md"
        self.speech_lines = [{"spoken_text": "听"}, {"spoken_text": "别动"}]
        self.structured = """# SEG002

输入与连续性：<Picture 1> 是真实尾帧，<Audio 1> 只锁音色。

## integrated_multimodal_description

米谷多说“听。”，随后说“别动。”。

## overall_soundscape

保留机械余响。

## non_diegetic_music

无配乐。

## dialogue_refs

| line_id | spoken_text |
|---|---|
| LINE003 | 听 |
| LINE005 | 别动 |
"""

    def tearDown(self):
        self.temp.cleanup()

    def validate(self, text):
        self.path.write_text(text, encoding="utf-8")
        issues = []
        drama_lint_prompts.check_director_draft_prompt(
            self.path, [1], [], [1], self.speech_lines, False, issues,
        )
        return issues

    def test_fixed_headings_and_dialogue_table_are_valid(self):
        self.assertEqual([], self.validate(self.structured))

    def test_five_natural_paragraphs_remain_valid(self):
        natural = "<图片1>是尾帧，<音频1>只锁音色。\n\n主体事实。\n\n米谷多：{听}；米谷多：{别动}。\n\n切点与尾态。\n\n一致性与禁区。"
        self.assertEqual([], self.validate(natural))

    def test_structured_headings_cannot_be_reordered(self):
        text = self.structured.replace(
            "## overall_soundscape", "## non_diegetic_music", 1,
        ).replace(
            "## non_diegetic_music\n\n无配乐。", "## overall_soundscape\n\n保留机械余响。", 1,
        )
        codes = {item["code"] for item in self.validate(text)}
        self.assertIn("prompt_five_sections_invalid", codes)

    def test_dialogue_table_cannot_omit_a_line(self):
        codes = {item["code"] for item in self.validate(self.structured.replace("| LINE005 | 别动 |\n", ""))}
        self.assertIn("prompt_speech_line_missing", codes)

    def test_dialogue_table_cannot_add_a_line(self):
        text = self.structured + "| LINE999 | 额外台词 |\n"
        codes = {item["code"] for item in self.validate(text)}
        self.assertIn("prompt_speech_line_extra", codes)


if __name__ == "__main__":
    unittest.main()
