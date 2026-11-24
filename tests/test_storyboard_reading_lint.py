from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.drama_lint_storyboards import check_storyboard_reading


class StoryboardReadingLintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "分镜_阅读稿_ep_1.md"
        self.valid = """# 第一集：天上海 · 分镜阅读稿

> 全片 4 秒，竖屏 9:16，日系手绘治愈风。共 1 章 1 个片段、2 个镜头，无字幕、无画面文字。

## 本集故事提要

阿海在云海前替远行的父亲收船，一声铁门响把现实压力带进天台。

---

## 第一章：云海承诺（本章时长：约 4 秒 / 00:00.0 - 00:04.0）

> 本章叙事功能：建立天台仪式，并让铁门声成为现实进入的第一道裂缝。

### 片段一：天台·云海喊话（00:00.0 - 00:04.0，本段包含 2 个镜头）

- **镜头1 (00:00.0-00:02.0)**：[大远景｜第三人称客观视角｜极慢横移｜高机位俯瞰] 云海缓慢翻涌，阿海蹲在围栏边把纸船码齐。声音：<山谷风><晾衣绳铁丝轻鸣>；人声：无。切入：开场建立画面直接进入；切出：横移落幅稳定后硬切到手部。
- **镜头2 (00:02.0-00:04.0)**：[特写｜客观视角｜固定机位｜俯拍手部] 阿海用拇指压平船舷折痕，尾半拍铁门声从画外进入。声音：<纸张摩擦声><铁门轻响>；人声：阿海：“爸爸，收船啦——”。切入：由全景硬切到仪式动作细节；切出：以声音先行承接下一片段。
"""

    def tearDown(self):
        self.temp.cleanup()

    def validate(self, text):
        self.path.write_text(text, encoding="utf-8")
        issues = []
        check_storyboard_reading(self.path, issues)
        return {item["code"] for item in issues}

    def test_chapter_fragment_and_bullet_shape_is_valid(self):
        self.assertEqual(set(), self.validate(self.valid))

    def test_markdown_table_is_rejected(self):
        start = self.valid.index("- **镜头1")
        text = self.valid[:start] + "|镜号|时长|画面|\n|---|---|---|\n|SHOT001|2秒|阿海码船|\n"
        self.assertIn("storyboard_reading_table_forbidden", self.validate(text))

    def test_seg_heading_is_rejected(self):
        text = self.valid.replace("### 片段一：天台·云海喊话", "### SEG001：天台·云海喊话")
        self.assertIn("storyboard_reading_structure_invalid", self.validate(text))

    def test_summary_counts_must_match_body(self):
        text = self.valid.replace("2 个镜头，无字幕", "3 个镜头，无字幕", 1)
        self.assertIn("storyboard_reading_count_mismatch", self.validate(text))

    def test_every_shot_requires_sound_and_cut_fields(self):
        text = self.valid.replace("声音：<山谷风>", "", 1).replace("切出：横移落幅稳定后硬切到手部", "", 1)
        self.assertIn("storyboard_reading_shot_invalid", self.validate(text))


if __name__ == "__main__":
    unittest.main()
