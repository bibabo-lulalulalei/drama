from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Protocol

if __package__:
    from .drama_lint_domain import check_unique, episode_dirs, issue, load_json
else:
    from drama_lint_domain import check_unique, episode_dirs, issue, load_json


class StoryboardIndex(Protocol):
    shot_ids: set[str]
    segment_ids: set[str]
    shot_to_segment: dict[Any, Any]
    shot_positions: dict[str, int]


@dataclass(frozen=True)
class HighlightBinding:
    raw: dict[str, Any]

    @property
    def highlight_id(self) -> str:
        return str(self.raw.get("highlight_id") or "")

    @property
    def label(self) -> str:
        return self.highlight_id or "亮点绑定"

    @property
    def segment_id(self) -> Any:
        return self.raw.get("segment_id")


@dataclass(frozen=True)
class InheritedAftereffect:
    raw: dict[str, Any]

    @property
    def binding_id(self) -> str:
        return str(self.raw.get("binding_id") or "")

    @property
    def source_episode_id(self) -> str:
        return str(self.raw.get("source_episode_id") or "")

    @property
    def source_highlight_id(self) -> str:
        return str(self.raw.get("source_highlight_id") or "")

    @property
    def label(self) -> str:
        return self.binding_id or "跨集余震承接"


class HighlightContractChecker:
    def __init__(
        self,
        root: Path,
        episode_id: str,
        data: dict[str, Any],
        storyboard: StoryboardIndex,
        lightweight: bool,
        path: Path,
        issues: list[dict[str, Any]],
    ) -> None:
        self.root = root
        self.episode_id = episode_id
        self.data = data
        self.storyboard = storyboard
        self.lightweight = lightweight
        self.path = path
        self.issues = issues
        self.planned_episode_ids = {item[0] for item in episode_dirs(root)}

    def report(self, code: str, message: str, path: Path | None = None) -> None:
        self.issues.append(issue("error", code, message, path or self.path))

    def run(self) -> None:
        script_path = self.root / f"episodes/{self.episode_id}/01_剧本/script_contract_{self.episode_id}.json"
        script_contract = load_json(script_path, self.issues, required=not self.lightweight)
        highlight_ledger = script_contract.get("highlight_ledger") if isinstance(script_contract, dict) else []
        if isinstance(script_contract, dict) and not isinstance(highlight_ledger, list):
            self.report("highlight_ledger_invalid", "script_contract.highlight_ledger 必须是数组。", script_path)
            highlight_ledger = []
        if not self.lightweight and isinstance(highlight_ledger, list):
            primary_entries = [
                item
                for item in highlight_ledger
                if isinstance(item, dict) and item.get("role") == "primary" and str(item.get("highlight_id") or "").strip()
            ]
            if not primary_entries:
                self.report("primary_highlight_missing", "完整模式每集 script_contract.highlight_ledger 必须至少包含一个有效的 primary 亮点。", script_path)
        primary_highlights = {
            item.get("highlight_id")
            for item in highlight_ledger or []
            if isinstance(item, dict) and item.get("role") == "primary" and isinstance(item.get("highlight_id"), str)
        }
        known_highlights = {
            item.get("highlight_id")
            for item in highlight_ledger or []
            if isinstance(item, dict) and isinstance(item.get("highlight_id"), str)
        }
        bindings = self.data.get("highlight_bindings")
        if not isinstance(bindings, list):
            self.report("highlight_bindings_missing", "storyboard.highlight_bindings 必须是数组并覆盖剧本主要亮点。")
            bindings = []
        binding_ids = check_unique(bindings, "highlight_id", self.path, self.issues, "highlight_bindings")
        self.check_inherited_aftereffects()
        for raw_binding in bindings:
            if not isinstance(raw_binding, dict):
                self.report("highlight_binding_invalid", "highlight_bindings 每项必须是对象。")
                continue
            self.check_binding(HighlightBinding(raw_binding), known_highlights)
        missing_primary = sorted(primary_highlights - binding_ids)
        if missing_primary:
            self.report("primary_highlight_binding_missing", f"以下主要亮点未绑定到分镜：{missing_primary}")

    def check_inherited_aftereffects(self) -> None:
        inherited_aftereffects = self.data.get("inherited_aftereffect_bindings", [])
        if not isinstance(inherited_aftereffects, list):
            self.report("inherited_aftereffect_bindings_invalid", "inherited_aftereffect_bindings 必须是数组。")
            return
        for raw_inherited in inherited_aftereffects:
            if not isinstance(raw_inherited, dict):
                self.report("inherited_aftereffect_binding_invalid", "inherited_aftereffect_bindings 每项必须是对象。")
                continue
            inherited = InheritedAftereffect(raw_inherited)
            shot_refs = inherited.raw.get("shot_ids")
            if not inherited.binding_id or not re.fullmatch(r"ep_[1-9]\d*", inherited.source_episode_id) or not inherited.source_highlight_id:
                self.report("inherited_aftereffect_binding_fields_missing", "inherited_aftereffect_bindings 必须填写 binding_id、source_episode_id 和 source_highlight_id。")
            if not isinstance(shot_refs, list) or not shot_refs or not all(isinstance(ref, str) and ref.strip() for ref in shot_refs):
                self.report("inherited_aftereffect_binding_shots_missing", f"{inherited.label} 必须绑定本集真实 shot_ids。")
            else:
                unknown_refs = sorted(set(shot_refs) - self.storyboard.shot_ids)
                if unknown_refs:
                    self.report("inherited_aftereffect_binding_shot_invalid", f"{inherited.label} 引用了不存在的本集镜头：{unknown_refs}")
            source_path = self.root / f"episodes/{inherited.source_episode_id}/02_分镜/storyboard_{inherited.source_episode_id}.json"
            source_storyboard = load_json(source_path, self.issues, required=False)
            source_bindings = source_storyboard.get("highlight_bindings") if isinstance(source_storyboard, dict) else []
            matching_sources = [
                item
                for item in source_bindings or []
                if isinstance(item, dict)
                and item.get("highlight_id") == inherited.source_highlight_id
                and isinstance(item.get("deferred_aftereffect_ref"), dict)
                and item["deferred_aftereffect_ref"].get("binding_id") == inherited.binding_id
                and item["deferred_aftereffect_ref"].get("episode_id") == self.episode_id
            ]
            if not matching_sources:
                self.report("inherited_aftereffect_source_missing", f"{inherited.label} 找不到来源集对应 deferred_aftereffect_ref。")

    def check_binding(self, binding: HighlightBinding, known_highlights: set[str]) -> None:
        if known_highlights and binding.highlight_id not in known_highlights:
            self.report("highlight_binding_unknown", f"分镜绑定了剧本中不存在的亮点：{binding.highlight_id}")
        if binding.segment_id not in self.storyboard.segment_ids:
            self.report("highlight_binding_segment_invalid", f"{binding.label} 引用了不存在的 segment_id：{binding.segment_id}")
        payoff_positions: list[int] = []
        reaction_positions: list[int] = []
        for field in ("payoff_shot_ids", "reaction_shot_ids"):
            refs = binding.raw.get(field)
            if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref.strip() for ref in refs):
                self.report("highlight_binding_shots_missing", f"{binding.label}.{field} 必须至少包含一个镜头。")
                continue
            unknown_refs = sorted(set(refs) - self.storyboard.shot_ids)
            if unknown_refs:
                self.report("highlight_binding_shot_invalid", f"{binding.label}.{field} 引用了不存在的镜头：{unknown_refs}")
            wrong_segment = sorted(
                ref
                for ref in refs
                if field == "payoff_shot_ids" and self.storyboard.shot_to_segment.get(ref) not in {None, binding.segment_id}
            )
            if wrong_segment:
                self.report("highlight_binding_segment_mismatch", f"{binding.label} 的镜头不属于 {binding.segment_id}：{wrong_segment}")
            valid_positions = [self.storyboard.shot_positions[ref] for ref in refs if ref in self.storyboard.shot_positions]
            if field == "payoff_shot_ids":
                payoff_positions.extend(valid_positions)
            else:
                reaction_positions.extend(valid_positions)
        if payoff_positions and reaction_positions and min(reaction_positions) < min(payoff_positions):
            self.report("highlight_binding_reaction_before_payoff", f"{binding.label} 的反应镜头不得早于兑现镜头。")
        self.check_aftereffect(binding, payoff_positions, reaction_positions)
        for field in ("visual_execution", "performance_execution", "audio_execution", "compile_notes"):
            if not str(binding.raw.get(field) or "").strip():
                self.report("highlight_binding_execution_missing", f"{binding.label} 缺少 {field}。")

    def check_aftereffect(self, binding: HighlightBinding, payoff_positions: list[int], reaction_positions: list[int]) -> None:
        aftereffect_refs = binding.raw.get("aftereffect_shot_ids")
        deferred = binding.raw.get("deferred_aftereffect_ref")
        if not isinstance(aftereffect_refs, list) or not all(isinstance(ref, str) and ref.strip() for ref in aftereffect_refs):
            self.report("highlight_binding_aftereffect_invalid", f"{binding.label}.aftereffect_shot_ids 必须是数组。")
            return
        if aftereffect_refs:
            unknown_refs = sorted(set(aftereffect_refs) - self.storyboard.shot_ids)
            if unknown_refs:
                self.report("highlight_binding_shot_invalid", f"{binding.label}.aftereffect_shot_ids 引用了不存在的本集镜头：{unknown_refs}")
            aftereffect_positions = [self.storyboard.shot_positions[ref] for ref in aftereffect_refs if ref in self.storyboard.shot_positions]
            preceding_positions = payoff_positions + reaction_positions
            if aftereffect_positions and preceding_positions and min(aftereffect_positions) < max(preceding_positions):
                self.report("highlight_binding_aftereffect_before_payoff", f"{binding.label} 的余震镜头不得早于兑现或反应镜头。")
            if deferred not in (None, {}):
                self.report("highlight_binding_aftereffect_scope_conflict", f"{binding.label} 已填写本集余震时 deferred_aftereffect_ref 必须为空。")
            return
        if not isinstance(deferred, dict):
            self.report("highlight_binding_aftereffect_missing", f"{binding.label} 必须填写本集 aftereffect_shot_ids 或跨集 deferred_aftereffect_ref。")
            return
        self.check_deferred_aftereffect(binding, deferred)

    def check_deferred_aftereffect(self, binding: HighlightBinding, deferred: dict[str, Any]) -> None:
        target_episode = str(deferred.get("episode_id") or "")
        binding_id = str(deferred.get("binding_id") or "")
        if not re.fullmatch(r"ep_[1-9]\d*", target_episode) or target_episode not in self.planned_episode_ids:
            self.report("highlight_binding_deferred_episode_invalid", f"{binding.label} deferred_aftereffect_ref.episode_id 必须是计划内分集。")
        elif int(target_episode.split("_", 1)[1]) <= int(self.episode_id.split("_", 1)[1]):
            self.report("highlight_binding_deferred_episode_order_invalid", f"{binding.label} deferred_aftereffect_ref 必须指向后续分集。")
        target_highlight = str(deferred.get("highlight_id") or "")
        if not target_highlight or not binding_id:
            self.report("highlight_binding_deferred_ref_invalid", f"{binding.label} deferred_aftereffect_ref 必须填写 highlight_id 和 binding_id。")
        target_path = self.root / f"episodes/{target_episode}/01_剧本/script_contract_{target_episode}.json"
        target_script = load_json(target_path, self.issues, required=False)
        target_ledger = target_script.get("highlight_ledger") if isinstance(target_script, dict) else []
        target_highlight_ids = {
            str(item.get("highlight_id"))
            for item in target_ledger or []
            if isinstance(item, dict) and str(item.get("highlight_id") or "").strip()
        }
        if target_highlight and target_highlight not in target_highlight_ids:
            self.report("highlight_binding_deferred_highlight_missing", f"{binding.label} deferred_aftereffect_ref.highlight_id 必须存在于目标集 script_contract.highlight_ledger。")


def check_highlight_contracts(
    root: Path,
    episode_id: str,
    data: dict[str, Any],
    storyboard: StoryboardIndex,
    lightweight: bool,
    path: Path,
    issues: list[dict[str, Any]],
) -> None:
    HighlightContractChecker(root, episode_id, data, storyboard, lightweight, path, issues).run()
