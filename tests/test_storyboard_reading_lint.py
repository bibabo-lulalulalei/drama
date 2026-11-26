from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.drama_lint_storyboards import (
    check_storyboard_reading,
    check_storyboard_reading_alignment,
)


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
        self.reference_valid = """## 第一集：天上海

### 本集故事提要

阿海在云海前替远行的父亲收船，一声铁门响把现实压力带进天台。

### 第一章：云海承诺（本章时长：约4秒 / 00:00.0 - 00:04.0）
> 本章叙事功能：建立天台仪式，并让铁门声成为现实进入的第一道裂缝。

#### 片段一：00:00.0 - 00:04.0（常规剪辑型，本段包含 2 个分镜）
- **镜头1 (00:00.0-00:02.0)**：[大远景｜第三人称客观视角｜极慢横移｜高机位俯瞰] 云海缓慢翻涌，阿海蹲在围栏边把纸船码齐。声音：<山谷风><晾衣绳铁丝轻鸣>；人声：无。切入：开场建立画面直接进入；切出：横移落幅稳定后硬切到手部。
- **镜头2 (00:02.0-00:04.0)**：[特写｜客观视角｜固定机位｜俯拍手部] 阿海用拇指压平船舷折痕，尾半拍铁门声从画外进入。声音：<纸张摩擦声><铁门轻响>；人声：阿海：{爸爸，收船啦——}。切入：由全景硬切到仪式动作细节；切出：以声音先行承接下一片段。
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

    def test_reference_heading_levels_fragment_and_voice_format_are_valid(self):
        self.assertEqual(set(), self.validate(self.reference_valid))

    def test_reference_format_keeps_json_time_and_shot_alignment(self):
        self.assertEqual(set(), self.validate_alignment(self.reference_valid, self.storyboard_data()))
        text = self.reference_valid.replace(
            "镜头1 (00:00.0-00:02.0)",
            "镜头1 (00:00.0-00:01.0)",
            1,
        ).replace(
            "镜头2 (00:02.0-00:04.0)",
            "镜头2 (00:01.0-00:04.0)",
            1,
        )
        self.assertIn(
            "storyboard_reading_shot_time_mismatch",
            self.validate_alignment(text, self.storyboard_data()),
        )

    def test_reference_last_fragment_supplies_total_duration(self):
        text = self.reference_valid.replace(
            "#### 片段一：00:00.0 - 00:04.0",
            "#### 片段一：00:00.0 - 00:05.0",
            1,
        )
        self.assertIn(
            "storyboard_reading_duration_mismatch",
            self.validate_alignment(text, self.storyboard_data()),
        )

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

    def test_explicit_cut_inside_one_shot_is_rejected(self):
        text = self.valid.replace(
            "阿海蹲在围栏边把纸船码齐",
            "阿海蹲在围栏边；切至门内中景，赫色起身",
            1,
        )
        self.assertIn("storyboard_reading_internal_cut", self.validate(text))

    def test_continuous_reframe_is_not_mistaken_for_a_cut(self):
        text = self.valid.replace("大远景｜", "特写转中景｜", 1).replace(
            "云海缓慢翻涌", "摄影机连续拉远，云海缓慢翻涌", 1,
        )
        self.assertNotIn("storyboard_reading_internal_cut", self.validate(text))

    def test_opening_cut_in_description_is_not_an_internal_cut(self):
        text = self.valid.replace(
            "云海缓慢翻涌，阿海蹲在围栏边把纸船码齐",
            "建立边界。画面：切至红姑娘近景，她抬眼正视军卒",
            1,
        )
        self.assertNotIn("storyboard_reading_internal_cut", self.validate(text))

    def test_physical_cutting_action_is_not_mistaken_for_an_edit(self):
        text = self.valid.replace("阿海用拇指压平船舷折痕", "阿海用刀切到纸边", 1)
        self.assertNotIn("storyboard_reading_internal_cut", self.validate(text))

    def storyboard_data(self):
        return {
            "duration_s": 4,
            "shots": [
                {"shot_id": "E01S01-SHOT001", "duration_s": 2},
                {"shot_id": "E01S01-SHOT002", "duration_s": 2},
            ],
            "segments": [{
                "segment_id": "SEG001",
                "duration_s": 4,
                "shot_ids": ["E01S01-SHOT001", "E01S01-SHOT002"],
            }],
        }

    def validate_alignment(self, text, data):
        self.path.write_text(text, encoding="utf-8")
        issues = []
        review = check_storyboard_reading(self.path, issues)
        check_storyboard_reading_alignment(review, data, issues)
        return {item["code"] for item in issues}

    def test_reading_and_json_share_segment_shot_order_and_time_axis(self):
        self.assertEqual(set(), self.validate_alignment(self.valid, self.storyboard_data()))

    def test_reading_shot_time_must_match_json_even_when_both_close_independently(self):
        text = self.valid.replace("镜头1 (00:00.0-00:02.0)", "镜头1 (00:00.0-00:01.0)", 1)
        text = text.replace("镜头2 (00:02.0-00:04.0)", "镜头2 (00:01.0-00:04.0)", 1)
        self.assertIn(
            "storyboard_reading_shot_time_mismatch",
            self.validate_alignment(text, self.storyboard_data()),
        )

    def test_reading_fragment_absolute_time_must_match_json_segment_position(self):
        text = self.valid.replace("00:00.0 - 00:04.0，本段", "00:01.0 - 00:05.0，本段", 1)
        text = text.replace("镜头1 (00:00.0-00:02.0)", "镜头1 (00:01.0-00:03.0)", 1)
        text = text.replace("镜头2 (00:02.0-00:04.0)", "镜头2 (00:03.0-00:05.0)", 1)
        self.assertIn(
            "storyboard_reading_segment_time_mismatch",
            self.validate_alignment(text, self.storyboard_data()),
        )

    def test_invalid_reading_structure_does_not_cascade_into_alignment_errors(self):
        text = self.valid.replace("### 片段一：天台·云海喊话", "### SEG001：天台·云海喊话", 1)
        codes = self.validate_alignment(text, self.storyboard_data())
        self.assertIn("storyboard_reading_structure_invalid", codes)
        self.assertNotIn("storyboard_reading_segment_count_mismatch", codes)

    def test_invalid_json_timing_is_left_to_json_checks_without_alignment_cascade(self):
        data = self.storyboard_data()
        data["segments"][0]["duration_s"] = None
        self.assertEqual(set(), self.validate_alignment(self.valid, data))
        data = self.storyboard_data()
        data["segments"][0]["shot_ids"] = [{"bad": "reference"}]
        self.assertEqual(set(), self.validate_alignment(self.valid, data))

    def test_reading_summary_and_segment_count_must_match_json(self):
        text = self.valid.replace("全片 4 秒", "全片 5 秒", 1)
        self.assertIn(
            "storyboard_reading_duration_mismatch",
            self.validate_alignment(text, self.storyboard_data()),
        )
        data = self.storyboard_data()
        data["segments"].append({"segment_id": "SEG002", "duration_s": 4, "shot_ids": []})
        data["duration_s"] = 8
        self.assertIn(
            "storyboard_reading_segment_count_mismatch",
            self.validate_alignment(self.valid, data),
        )


if __name__ == "__main__":
    unittest.main()
