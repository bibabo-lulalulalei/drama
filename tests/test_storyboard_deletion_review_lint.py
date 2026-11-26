from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.drama_lint_storyboards import (
    check_director_deletion_review,
    check_segment_shot_count,
)


class DirectorDeletionReviewLintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "导演总控卡_ep_1.md"
        self.segments = [
            {
                "segment_id": "SEG001",
                "shot_ids": ["E01S01-SHOT001", "E01S01-SHOT002"],
            },
            {
                "segment_id": "SEG002",
                "shot_ids": ["E01S02-SHOT001", "E01S02-SHOT002"],
            },
        ]
        self.valid_table = """## 逐段执行区

| 片段 | 戏剧目标 | 镜头职责与删除损失 | 尾态 |
|---|---|---|---|
| SEG001 10s | 通牒落下 | SHOT001 删则通牒发起者无入场；SHOT002 删则通知单证据缺失 | 阿海等待回答 |
| SEG002 10s | 关系改变 | SHOT001/002 删则反问与失语两个必要节拍同时丢失 | 周岚离场 |
"""

    def tearDown(self):
        self.temp.cleanup()

    def validate(self, text, segments=None):
        self.path.write_text(text, encoding="utf-8")
        issues = []
        check_director_deletion_review(
            self.path,
            self.segments if segments is None else segments,
            issues,
        )
        return issues

    def test_reference_style_table_covers_each_shot(self):
        self.assertEqual([], self.validate(self.valid_table))

    def test_heading_style_also_covers_each_shot(self):
        text = """### SEG001｜搬家通牒
- 镜头职责与删除损失：SHOT001 删则入场缺失；SHOT002 删则物证缺失。
### SEG002｜反问与失语
- 镜头职责与删除损失：E01S02-SHOT001 删则反问丢失；E01S02-SHOT002 删则听者失语不可见。
"""
        self.assertEqual([], self.validate(text))

    def test_episode_wide_blanket_claim_does_not_replace_segment_reviews(self):
        text = """### SEG001｜搬家通牒
- 密度与镜头必要性：dialogue_emotional；两句对白与物证不可压缩。
### SEG002｜反问与失语
- 密度与镜头必要性：dialogue_emotional；说者与听者反应不可压缩。
## 内容复核
| 检查项 | 结果 | 说明 |
|---|---|---|
| 镜头职责与删除测试 | 通过 | 全片镜头均有动作、信息、关系或反应职责。 |
"""
        issues = self.validate(text)
        self.assertEqual(
            {"director_segment_deletion_review_missing"},
            {item["code"] for item in issues},
        )
        self.assertEqual(2, len(issues))

    def test_one_shot_cannot_borrow_another_shots_delete_clause(self):
        text = self.valid_table.replace(
            "；SHOT002 删则通知单证据缺失", "；SHOT002 通知单入画", 1,
        )
        issues = self.validate(text)
        self.assertIn(
            "director_shot_deletion_review_missing",
            {item["code"] for item in issues},
        )
        self.assertTrue(any("E01S01-SHOT002" in item["message"] for item in issues))

    def test_non_high_density_segments_keep_dynamic_shot_counts(self):
        issues = []
        check_segment_shot_count(
            "SEG001", 15, 3, "edited", "dialogue_emotional", self.path, issues,
        )
        self.assertEqual([], issues)

    def test_existing_high_density_fifteen_second_minimum_is_unchanged(self):
        issues = []
        check_segment_shot_count(
            "SEG001", 15, 3, "edited", "high_density_short", self.path, issues,
        )
        self.assertIn("segment_shot_count_invalid", {item["code"] for item in issues})


if __name__ == "__main__":
    unittest.main()
