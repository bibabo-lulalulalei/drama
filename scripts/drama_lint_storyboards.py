from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
import re
from typing import Any

if __package__:
    from .drama_lint_domain import (
        ProductionPlan,
        REFERENCE_ROLES,
        check_declared_video_models,
        check_h3_duration,
        check_unique,
        episode_dirs,
        file_exists,
        has_meaningful_value,
        issue,
        load_json,
        markdown_table_column_counts,
        marker_pattern,
        relative_file,
    )
    from .drama_lint_highlights import check_highlight_contracts
else:
    from drama_lint_domain import (
        ProductionPlan,
        REFERENCE_ROLES,
        check_declared_video_models,
        check_h3_duration,
        check_unique,
        episode_dirs,
        file_exists,
        has_meaningful_value,
        issue,
        load_json,
        markdown_table_column_counts,
        marker_pattern,
        relative_file,
    )
    from drama_lint_highlights import check_highlight_contracts


EPISODE_KEYFRAME_MIN = 3
EPISODE_KEYFRAME_MAX = 4
SEGMENT_KEYFRAME_MAX = 2


class DensityProfile(str, Enum):
    HIGH_DENSITY_SHORT = "high_density_short"
    DIALOGUE_EMOTIONAL = "dialogue_emotional"
    SUSPENSE_BUILD = "suspense_build"
    MICRO_FILM = "micro_film"
    CUSTOM = "custom"


class ShotMode(str, Enum):
    EDITED = "edited"
    TRUE_ONE_TAKE = "true_one_take"


class TailMode(str, Enum):
    CONTINUOUS_MOTION = "continuous_motion"
    CUTTABLE_COMPLETION = "cuttable_completion"
    STABLE_HOLD = "stable_hold"
    LOOP_CONTINUATION = "loop_continuation"


DENSITY_PROFILES = {profile.value for profile in DensityProfile}
SHOT_MODES = {mode.value for mode in ShotMode}
TAIL_MODES = {mode.value for mode in TailMode}


def _finite_positive_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0
    )


@dataclass(frozen=True)
class StoryboardStructure:
    shot_ids: set[str]
    segment_ids: set[str]
    shot_to_segment: dict[Any, Any]
    scene_ids: set[str]
    shot_durations: dict[str, Any]
    shot_positions: dict[str, int]

    @classmethod
    def build(cls, shots: list[Any], segments: list[Any], path: Path, issues: list[dict[str, Any]]) -> "StoryboardStructure":
        shot_ids = check_unique(shots, "shot_id", path, issues, "shots")
        segment_ids = check_unique(segments, "segment_id", path, issues, "segments")
        ordered_shot_ids = [item.get("shot_id") for item in shots if isinstance(item, dict) and isinstance(item.get("shot_id"), str)]
        shot_durations: dict[str, Any] = {}
        for item in shots:
            if not isinstance(item, dict) or not isinstance(item.get("shot_id"), str):
                continue
            shot_id = item["shot_id"]
            duration = item.get("duration_s")
            if not _finite_positive_number(duration):
                issues.append(issue("error", "shot_duration_invalid", f"{shot_id} duration_s 必须是有限正数，不能为布尔值、NaN、Infinity、0 或负数。", path))
            elif isinstance(duration, (int, float)):
                shot_durations[shot_id] = duration
        return cls(
            shot_ids=shot_ids,
            segment_ids=segment_ids,
            shot_to_segment={
                item.get("shot_id"): item.get("segment_id")
                for item in shots
                if isinstance(item, dict) and isinstance(item.get("shot_id"), str)
            },
            scene_ids={
                item.get("scene_id")
                for item in shots
                if isinstance(item, dict) and isinstance(item.get("scene_id"), str) and item.get("scene_id").strip()
            },
            shot_durations=shot_durations,
            shot_positions={shot_id: index for index, shot_id in enumerate(ordered_shot_ids)},
        )


@dataclass(frozen=True)
class ShotCountRequest:
    segment_id: Any
    duration_s: int
    shot_count: int
    shot_mode: Any
    density_profile: Any
    path: Path
    issues: list[dict[str, Any]]

    @property
    def label(self) -> str:
        return str(self.segment_id or "segment")

    def report(self, code: str, message: str) -> None:
        self.issues.append(issue("error", code, message, self.path))


class EditedShotPolicy:
    def validate(self, request: ShotCountRequest) -> None:
        if request.density_profile == DensityProfile.HIGH_DENSITY_SHORT.value and request.duration_s == 15 and request.shot_count < 8:
            request.report("segment_shot_count_invalid", f"{request.label} 为 high_density_short 的 15 秒剪辑型视频，至少需要 8 个有效镜头。")


class TrueOneTakePolicy:
    def validate(self, request: ShotCountRequest) -> None:
        if request.shot_count != 1:
            request.report("true_one_take_shot_count_invalid", f"{request.label} 标记为 true_one_take 时必须且只能包含 1 个镜头。")


SHOT_MODE_POLICIES = {
    ShotMode.EDITED.value: EditedShotPolicy(),
    ShotMode.TRUE_ONE_TAKE.value: TrueOneTakePolicy(),
}


def check_segment_shot_count(
    segment_id: Any,
    duration_s: int,
    shot_count: int,
    shot_mode: Any,
    density_profile: Any,
    path: Path,
    issues: list[dict[str, Any]],
) -> None:
    request = ShotCountRequest(segment_id, duration_s, shot_count, shot_mode, density_profile, path, issues)
    if density_profile not in DENSITY_PROFILES:
        request.report("segment_density_profile_invalid", f"{request.label} density_profile 无效。")
    policy = SHOT_MODE_POLICIES.get(shot_mode)
    if policy is None:
        request.report("segment_shot_mode_invalid", f"{request.label} shot_mode 必须为 edited 或 true_one_take。")
        return
    policy.validate(request)


def check_keyframe_request_plan(
    segment: dict[str, Any],
    path: Path,
    issues: list[dict[str, Any]],
    max_per_segment: int = SEGMENT_KEYFRAME_MAX,
) -> int:
    segment_id = str(segment.get("segment_id") or "segment")
    requests = segment.get("keyframe_requests")
    if requests is None:
        return 0
    if not isinstance(requests, list):
        issues.append(issue("error", "keyframe_requests_invalid", f"{segment_id} keyframe_requests 必须是数组；未选中本集高光时可省略或填空数组。", path))
        return 0
    count = len(requests)
    if count > max_per_segment:
        issues.append(issue("error", "keyframe_request_count_invalid", f"{segment_id} 单段 keyframe_requests 最多 {max_per_segment} 张；关键帧按集总量规划，不得把普通镜头都升级为 KF。", path))
    roles = segment.get("required_keyframe_roles")
    if count and isinstance(roles, list) and "highlight" not in roles:
        issues.append(issue("error", "keyframe_role_missing", f"{segment_id} 已规划 keyframe_requests 时，required_keyframe_roles 必须包含 highlight。", path))
    if not count and isinstance(roles, list) and "highlight" in roles:
        issues.append(issue("error", "keyframe_role_without_request", f"{segment_id} 标记了 highlight 但没有 keyframe_requests；未选中本集高光时不要登记关键帧职责。", path))
    return count


def check_episode_keyframe_request_plan(segments: list[Any], lightweight: bool, path: Path, issues: list[dict[str, Any]]) -> None:
    valid_segments = [segment for segment in segments if isinstance(segment, dict)]
    max_per_segment = EPISODE_KEYFRAME_MAX if len(valid_segments) == 1 else SEGMENT_KEYFRAME_MAX
    total = 0
    for segment in valid_segments:
        total += check_keyframe_request_plan(segment, path, issues, max_per_segment)
    if total == 0:
        if not lightweight:
            issues.append(issue("error", "episode_keyframe_requests_missing", f"完整模式每集必须按集规划 {EPISODE_KEYFRAME_MIN}-{EPISODE_KEYFRAME_MAX} 张剧情高光关键帧；不是每个 SEG 都需要，但全集不能为 0。", path))
        return
    if total < EPISODE_KEYFRAME_MIN or total > EPISODE_KEYFRAME_MAX:
        issues.append(issue("error", "episode_keyframe_request_count_invalid", f"本集 keyframe_requests 总数为 {total}，必须按集规划 {EPISODE_KEYFRAME_MIN}-{EPISODE_KEYFRAME_MAX} 张剧情高光关键帧；不是每个 SEG 都需要关键帧。", path))


def check_reference_plan(segment: dict[str, Any], path: Path, issues: list[dict[str, Any]]) -> None:
    refs = segment.get("reference_input_plan")
    if refs is None:
        issues.append(issue("error", "reference_input_plan_missing", "每个 SEG 必须填写 reference_input_plan。", path))
        return
    if not isinstance(refs, list):
        issues.append(issue("error", "reference_input_plan_invalid", "reference_input_plan 必须是数组。", path))
        return
    orders: list[int] = []
    for index, ref in enumerate(refs, start=1):
        if not isinstance(ref, dict):
            issues.append(issue("error", "reference_input_plan_invalid", f"第 {index} 条参考计划必须是对象。", path))
            continue
        order = ref.get("order")
        role = ref.get("role")
        if isinstance(order, int) and not isinstance(order, bool):
            orders.append(order)
            binding = str(ref.get("opening_binding", "") or "")
            if not re.search(marker_pattern("image", order), binding, flags=re.I):
                issues.append(issue("error", "opening_binding_marker_missing", f"第 {order} 张参考图缺少对应 <图片{order}>/<IMG{order}> 标记。", path))
        else:
            issues.append(issue("error", "reference_order_invalid", "参考图 order 必须是整数。", path))
        if role not in REFERENCE_ROLES:
            issues.append(issue("error", "reference_role_invalid", f"参考图职责无效：{role}", path))
        for field in ("planned_source", "opening_binding", "adopt", "exclude"):
            if not str(ref.get(field, "") or "").strip():
                issues.append(issue("error", "reference_input_plan_incomplete", f"参考图计划缺少 {field}。", path))
    if orders and sorted(orders) != list(range(1, len(orders) + 1)):
        issues.append(issue("error", "reference_order_not_contiguous", "参考图 order 必须从 1 连续递增。", path))


@dataclass(frozen=True)
class AudienceExecutionContract:
    execution: Any
    plan: Any
    shot_ids: set[str]
    scene_ids: set[str]
    path: Path
    issues: list[dict[str, Any]]

    def report(self, code: str, message: str) -> None:
        self.issues.append(issue("error", code, message, self.path))

    def validate(self) -> None:
        if not isinstance(self.execution, dict):
            self.report("audience_execution_missing", "storyboard 必须登记从已确认 audience_plan 派生的 audience_execution。")
            return
        source_revision = self.execution.get("source_plan_revision")
        if not isinstance(source_revision, int) or isinstance(source_revision, bool) or source_revision < 1:
            self.report("audience_execution_revision_invalid", "audience_execution.source_plan_revision 必须是正整数。")
        elif isinstance(self.plan, dict) and isinstance(self.plan.get("revision"), int) and source_revision != self.plan.get("revision"):
            self.report("audience_execution_revision_mismatch", "audience_execution.source_plan_revision 必须等于当前已确认 drama_plan revision。")
        audience_plan = self.plan.get("audience_plan") if isinstance(self.plan, dict) and isinstance(self.plan.get("audience_plan"), dict) else {}
        for field in ("viewing_focus", "emotional_payoff", "platform_viewing_context", "expression_boundaries"):
            execution = self.execution.get(field)
            if not isinstance(execution, dict) or not str(execution.get("contract") or "").strip():
                self.report("audience_execution_field_missing", f"audience_execution.{field} 必须填写 contract。")
                continue
            expected_source = f"audience_plan.{field}"
            if execution.get("source_field") != expected_source:
                self.report("audience_execution_source_field_invalid", f"audience_execution.{field}.source_field 必须为 {expected_source}。")
            if execution.get("contract") != audience_plan.get(field):
                self.report("audience_execution_contract_mismatch", f"audience_execution.{field}.contract 必须逐字继承已确认 audience_plan.{field}。")
            refs = execution.get("scene_or_shot_ids")
            if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref.strip() for ref in refs):
                self.report("audience_execution_refs_missing", f"audience_execution.{field}.scene_or_shot_ids 必须列出落地场次或镜头。")
                continue
            unknown_refs = sorted(set(refs) - self.shot_ids - self.scene_ids)
            if unknown_refs:
                self.report("audience_execution_ref_invalid", f"audience_execution.{field} 引用了不存在的场次或镜头：{unknown_refs}")


def load_storyboard_index(root: Path, episode_id: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
    path = root / f"episodes/{episode_id}/02_分镜/storyboard_{episode_id}.json"
    data = load_json(path, issues, required=False)
    if not isinstance(data, dict):
        return {
            "segments": set(),
            "shots": set(),
            "shot_durations": {},
            "segment_shots": {},
            "segment_durations": {},
            "required_reference_roles": {},
            "required_keyframe_roles": {},
            "keyframe_requests": {},
        }
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []
    segments = data.get("segments") if isinstance(data.get("segments"), list) else []
    return {
        "segments": {item.get("segment_id") for item in segments if isinstance(item, dict) and isinstance(item.get("segment_id"), str)},
        "shots": {item.get("shot_id") for item in shots if isinstance(item, dict) and isinstance(item.get("shot_id"), str)},
        "shot_durations": {
            item.get("shot_id"): item.get("duration_s")
            for item in shots
            if isinstance(item, dict) and isinstance(item.get("shot_id"), str) and isinstance(item.get("duration_s"), (int, float))
        },
        "segment_shots": {
            item.get("segment_id"): item.get("shot_ids")
            for item in segments
            if isinstance(item, dict) and isinstance(item.get("segment_id"), str) and isinstance(item.get("shot_ids"), list)
        },
        "segment_durations": {
            item.get("segment_id"): item.get("duration_s")
            for item in segments
            if isinstance(item, dict) and isinstance(item.get("segment_id"), str) and isinstance(item.get("duration_s"), (int, float))
        },
        "required_reference_roles": {
            item.get("segment_id"): {role for role in item.get("required_reference_roles") if isinstance(role, str)}
            for item in segments
            if isinstance(item, dict) and isinstance(item.get("segment_id"), str) and isinstance(item.get("required_reference_roles"), list)
        },
        "required_keyframe_roles": {
            item.get("segment_id"): {role for role in item.get("required_keyframe_roles") if isinstance(role, str)}
            for item in segments
            if isinstance(item, dict) and isinstance(item.get("segment_id"), str) and isinstance(item.get("required_keyframe_roles"), list)
        },
        "keyframe_requests": {
            item.get("segment_id"): item.get("keyframe_requests")
            for item in segments
            if isinstance(item, dict) and isinstance(item.get("segment_id"), str) and isinstance(item.get("keyframe_requests"), list)
        },
    }


def video_model_name(plan: Any, storyboard: dict[str, Any], segment: dict[str, Any]) -> str:
    for value in (
        segment.get("video_model"),
        segment.get("model"),
        storyboard.get("video_model"),
        storyboard.get("model"),
    ):
        if isinstance(value, str) and value.strip():
            return value
    model_plan = plan.get("model_plan") if isinstance(plan, dict) else None
    video_plan = model_plan.get("video") if isinstance(model_plan, dict) else None
    if isinstance(video_plan, dict):
        for field in ("model", "model_name", "selected_model"):
            value = video_plan.get(field)
            if isinstance(value, str) and value.strip():
                return value
    if isinstance(video_plan, str):
        return video_plan
    return ""


def _check_storyboard_files(root: Path, episode_id: str, data: dict[str, Any], path: Path, issues: list[dict[str, Any]]) -> bool:
    expected_director_card = f"episodes/{episode_id}/02_分镜/导演总控卡_{episode_id}.md"
    if data.get("director_control_card") != expected_director_card:
        issues.append(issue("error", "director_control_card_invalid", f"storyboard.director_control_card 必须指向 {expected_director_card}。", path))
    elif not file_exists(root, expected_director_card):
        issues.append(issue("error", "director_control_card_missing", "分镜阶段必须存在唯一导演总控卡。", path))
    expected_source_markdown = f"episodes/{episode_id}/02_分镜/分镜_完整分镜表_{episode_id}.md"
    source_markdown = relative_file(root, data.get("source_markdown"))
    if data.get("source_markdown") != expected_source_markdown:
        issues.append(issue("error", "storyboard_source_markdown_invalid", f"storyboard.source_markdown 必须指向 {expected_source_markdown}。", path))
    elif source_markdown is None or not source_markdown.is_file():
        issues.append(issue("error", "storyboard_source_markdown_missing", "十五列完整分镜表文件不存在。", path))
    else:
        try:
            table_text = source_markdown.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            issues.append(issue("error", "storyboard_source_markdown_unreadable", f"十五列完整分镜表无法读取：{exc}", source_markdown))
        else:
            if 15 not in markdown_table_column_counts(table_text):
                issues.append(issue("error", "storyboard_fifteen_columns_missing", "完整分镜表必须包含一个十五列表格。", source_markdown))
    shots = data.get("shots")
    segments = data.get("segments")
    if not isinstance(shots, list) or not isinstance(segments, list):
        issues.append(issue("error", "storyboard_shape_invalid", "storyboard 必须包含 shots 和 segments 数组。", path))
        return False
    return True


def _check_segment_structure(
    segment: dict[str, Any],
    index: int,
    segment_count: int,
    structure: StoryboardStructure,
    covered: list[str],
    path: Path,
    issues: list[dict[str, Any]],
) -> None:
    segment_id = segment.get("segment_id")
    check_declared_video_models(segment, path, str(segment_id or index), issues)
    check_h3_duration(segment.get("duration_s"), path, str(segment_id or index), issues)
    segment_shots = segment.get("shot_ids")
    if not isinstance(segment_shots, list):
        issues.append(issue("error", "segment_shot_ids_invalid", f"{segment_id or index} 缺少 shot_ids 数组。", path))
        return
    for shot_id in segment_shots:
        if shot_id not in structure.shot_ids:
            issues.append(issue("error", "segment_unknown_shot", f"{segment_id} 引用了不存在的 shot_id：{shot_id}", path))
        elif structure.shot_to_segment.get(shot_id) not in {None, segment_id}:
            issues.append(issue("error", "shot_segment_mismatch", f"{shot_id} 的 segment_id 与 segments[].shot_ids 不一致。", path))
    covered.extend(str(item) for item in segment_shots)
    if _finite_positive_number(segment.get("duration_s")):
        declared_value = float(segment["duration_s"])
        declared = int(declared_value) if declared_value.is_integer() else 0
        calculated = sum(float(structure.shot_durations[s]) for s in segment_shots if s in structure.shot_durations)
        if calculated and abs(declared_value - calculated) > 1e-6:
            issues.append(issue("error", "segment_duration_mismatch", f"{segment_id} duration_s 必须等于其 shot_ids 时长之和；小数自然切点完成表演吸收后，最终 SHOT 时长必须闭合到整数 SEG。", path))
        check_segment_shot_count(segment_id, declared, len(segment_shots), segment.get("shot_mode"), segment.get("density_profile"), path, issues)
        if declared_value < 15 and not has_meaningful_value(segment.get("duration_exception_reason")):
            issues.append(issue("error", "segment_duration_exception_reason_missing", f"{segment_id} 低于默认 15 秒，必须用 duration_exception_reason 记录尾段、自然切点或其他真实原因；不得用短段规避默认节奏。", path))
    tail_mode = segment.get("tail_mode")
    if tail_mode not in TAIL_MODES:
        issues.append(issue("error", "segment_tail_mode_invalid", f"{segment_id or index} tail_mode 无效。", path))
    if index < segment_count and tail_mode == TailMode.STABLE_HOLD.value and not has_meaningful_value(segment.get("tail_hold_reason")):
        issues.append(issue("error", "intermediate_stable_hold_reason_missing", f"{segment_id or index} 是中间片段，使用 stable_hold 时必须填写 tail_hold_reason。", path))
    check_reference_plan(segment, path, issues)


DIRECTOR_DELETION_LABEL = re.compile(r"镜头职责与删除(?:损失|测试)")
DIRECTOR_SEGMENT_ID = re.compile(r"\bSEG\d{3}\b")
DIRECTOR_SHOT_REF = re.compile(r"SHOT(\d{3})((?:/\d{3})*)")


def _markdown_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _covered_deletion_shots(text: str) -> set[int]:
    covered: set[int] = set()
    for clause in re.split(r"[；;\n]+", text):
        if "删" not in clause:
            continue
        for match in DIRECTOR_SHOT_REF.finditer(clause):
            covered.add(int(match.group(1)))
            covered.update(int(value) for value in re.findall(r"/(\d{3})", match.group(2)))
    return covered


def check_director_deletion_review(path: Path, segments: list[Any], issues: list[dict[str, Any]]) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        issues.append(issue("error", "director_deletion_review_unreadable", f"导演总控卡无法读取：{exc}", path))
        return

    review_texts: dict[str, list[str]] = {}
    line_index = 0
    while line_index < len(lines):
        stripped = lines[line_index].strip()
        header = _markdown_cells(stripped) if stripped.startswith("|") else []
        deletion_columns = [index for index, cell in enumerate(header) if DIRECTOR_DELETION_LABEL.fullmatch(cell)]
        if not deletion_columns:
            line_index += 1
            continue
        deletion_column = deletion_columns[0]
        row_index = line_index + 1
        while row_index < len(lines) and lines[row_index].strip().startswith("|"):
            cells = _markdown_cells(lines[row_index])
            if cells and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
                row_index += 1
                continue
            if len(cells) > deletion_column:
                segment_match = DIRECTOR_SEGMENT_ID.search(cells[0])
                if segment_match is not None:
                    segment_id = segment_match.group(0)
                    review_texts.setdefault(segment_id, []).append(cells[deletion_column])
            row_index += 1
        line_index = row_index

    current_segment: str | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^#{1,6}\s+", stripped):
            segment_match = DIRECTOR_SEGMENT_ID.search(stripped)
            current_segment = segment_match.group(0) if segment_match is not None else None
        label = DIRECTOR_DELETION_LABEL.search(stripped)
        if current_segment is None or label is None:
            continue
        parts = [stripped[label.start():]]
        for following in lines[index + 1:]:
            following = following.strip()
            if re.match(r"^#{1,6}\s+", following) or following.startswith("|"):
                break
            if DIRECTOR_SHOT_REF.search(following) and "删" in following:
                parts.append(following)
            elif following.startswith("- "):
                break
        review_texts.setdefault(current_segment, []).append("\n".join(parts))

    for segment in segments:
        if not isinstance(segment, dict):
            continue
        segment_id = str(segment.get("segment_id") or "segment")
        shot_ids = segment.get("shot_ids")
        if not isinstance(shot_ids, list):
            continue
        texts = review_texts.get(segment_id, [])
        if not texts:
            issues.append(issue("error", "director_segment_deletion_review_missing", f"{segment_id} 必须在导演总控卡的“镜头职责与删除损失”中逐镜记录删除测试，不能用整段或全集概括代替。", path))
            continue
        covered = _covered_deletion_shots("\n".join(texts))
        expected: dict[int, str] = {}
        for shot_id in shot_ids:
            match = re.search(r"SHOT(\d{3})$", str(shot_id))
            if match is not None:
                expected[int(match.group(1))] = str(shot_id)
        missing = [shot_id for number, shot_id in expected.items() if number not in covered]
        if missing:
            issues.append(issue("error", "director_shot_deletion_review_missing", f"{segment_id} 以下镜头缺少带具体删除损失的逐镜记录：{missing}", path))


READING_TIME = r"\d{2}:\d{2}(?:\.\d+)?"
READING_NUMBER = r"0-9零〇一二三四五六七八九十百千万两"
READING_TITLE = re.compile(rf"^# 第[{READING_NUMBER}]+集：\S.* · 分镜阅读稿$")
REFERENCE_READING_TITLE = re.compile(rf"^## 第[{READING_NUMBER}]+集：\S.*$")
READING_CHAPTER = re.compile(
    rf"^## 第[{READING_NUMBER}]+章：.+（本章时长：约\s*\d+(?:\.\d+)?\s*秒 / {READING_TIME} - {READING_TIME}）$"
)
REFERENCE_READING_CHAPTER = re.compile(
    rf"^### 第[{READING_NUMBER}]+章：.+（本章时长：约\s*\d+(?:\.\d+)?\s*秒 / {READING_TIME} - {READING_TIME}）$"
)
READING_FRAGMENT = re.compile(
    rf"^### 片段[{READING_NUMBER}]+：.+（(?P<start>{READING_TIME}) - (?P<end>{READING_TIME})，本段包含 (?P<count>\d+) 个镜头）$"
)
REFERENCE_READING_FRAGMENT = re.compile(
    rf"^#### 片段[{READING_NUMBER}]+：(?P<start>{READING_TIME}) - (?P<end>{READING_TIME})（[^（）\n]+，本段包含 (?P<count>\d+) 个分镜）$"
)
READING_SHOT = re.compile(
    rf"^- \*\*镜头(?P<number>\d+) \((?P<start>{READING_TIME})-(?P<end>{READING_TIME})\)\*\*：\[(?P<camera>[^\]\n]+)\]\s*(?P<body>.*)$"
)
READING_INTERNAL_CUT = re.compile(r"(?:硬切|切换|切)至|(?:镜头|画面)(?:硬切|切换|切)到|(?:硬切|切换)到")


def _reading_seconds(value: str) -> float:
    minutes, seconds = value.split(":", 1)
    return int(minutes) * 60 + float(seconds)


def _reading_time_matches(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= 1e-6


def check_storyboard_reading(path: Path, issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        issues.append(issue("error", "storyboard_reading_unreadable", f"分镜阅读稿无法读取：{exc}", path))
        return None
    lines = text.splitlines()
    nonempty = [(index, line.strip()) for index, line in enumerate(lines) if line.strip()]
    issue_start = len(issues)
    review: dict[str, Any] = {"path": path, "duration_s": None, "fragments": []}

    def error(code: str, message: str) -> None:
        issues.append(issue("error", code, message, path))

    reference_style = bool(nonempty and REFERENCE_READING_TITLE.fullmatch(nonempty[0][1]))
    title_pattern = REFERENCE_READING_TITLE if reference_style else READING_TITLE
    chapter_pattern = REFERENCE_READING_CHAPTER if reference_style else READING_CHAPTER
    fragment_pattern = REFERENCE_READING_FRAGMENT if reference_style else READING_FRAGMENT
    summary_heading = "### 本集故事提要" if reference_style else "## 本集故事提要"

    if not nonempty or title_pattern.fullmatch(nonempty[0][1]) is None:
        expected_title = "“## 第X集：标题”" if reference_style else "“# 第X集：标题 · 分镜阅读稿”或参考版“## 第X集：标题”"
        error("storyboard_reading_title_invalid", f"分镜阅读稿首行必须采用{expected_title}。")
    if not reference_style:
        if len(nonempty) < 2 or re.match(r"^> 全片\s*\d+(?:\.\d+)?\s*秒[，,]", nonempty[1][1]) is None:
            error("storyboard_reading_summary_invalid", "旧严格模板的标题后必须用一行引用写明全片秒数、画幅、画风及真实章节、片段和镜头总数。")
        if len(nonempty) < 3 or nonempty[2][1] != summary_heading:
            error("storyboard_reading_structure_invalid", "旧严格模板的全片总览后必须紧接“## 本集故事提要”。")
    if any(re.match(r"^\s*\|.*\|\s*$", line) for line in lines):
        error("storyboard_reading_table_forbidden", "分镜阅读稿必须使用逐镜无序列表，不得使用 Markdown 表格；表格只保留在内部完整分镜表。")

    chapters: list[tuple[int, re.Match[str]]] = []
    fragments: list[tuple[int, re.Match[str]]] = []
    summary_headings = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        chapter = chapter_pattern.fullmatch(stripped)
        fragment = fragment_pattern.fullmatch(stripped)
        if chapter is not None:
            chapters.append((index, chapter))
        if fragment is not None:
            fragments.append((index, fragment))
        if stripped == summary_heading:
            summary_headings += 1
        if re.match(r"^#{1,6}\s+", stripped) and not any((
            title_pattern.fullmatch(stripped),
            stripped == summary_heading,
            chapter,
            fragment,
        )):
            error("storyboard_reading_structure_invalid", f"阅读稿标题层级或名称不符合当前模板：{stripped}")
    if summary_headings != 1 or not chapters:
        error("storyboard_reading_structure_invalid", "阅读稿必须且只能有一个“本集故事提要”，并至少包含一个规范章节。")

    chapter_starts = [index for index, _ in chapters]
    fragment_starts = [index for index, _ in fragments]
    section_starts = sorted(chapter_starts + fragment_starts + [len(lines)])
    for position, (chapter_index, _) in enumerate(chapters):
        chapter_end = chapter_starts[position + 1] if position + 1 < len(chapters) else len(lines)
        next_content = next((lines[index].strip() for index in range(chapter_index + 1, chapter_end) if lines[index].strip()), "")
        if not next_content.startswith("> 本章叙事功能："):
            error("storyboard_reading_chapter_function_missing", "每个章节标题后必须紧接“> 本章叙事功能：…”。")
        if not any(chapter_index < fragment_index < chapter_end for fragment_index, _ in fragments):
            error("storyboard_reading_fragment_missing", "每个章节必须至少包含一个规范片段。")

    shot_numbers: list[int] = []
    for fragment_index, fragment in fragments:
        section_end = next(index for index in section_starts if index > fragment_index)
        declared_count = int(fragment.group("count"))
        current_numbers: list[int] = []
        fragment_review: dict[str, Any] = {
            "start_s": _reading_seconds(fragment.group("start")),
            "end_s": _reading_seconds(fragment.group("end")),
            "declared_count": declared_count,
            "shots": [],
        }
        review["fragments"].append(fragment_review)
        for line_index in range(fragment_index + 1, section_end):
            stripped = lines[line_index].strip()
            if not stripped.startswith("- "):
                continue
            shot = READING_SHOT.fullmatch(stripped)
            if shot is None:
                error("storyboard_reading_shot_invalid", f"第 {line_index + 1} 行必须采用固定逐镜条目格式：{stripped}")
                continue
            number = int(shot.group("number"))
            current_numbers.append(number)
            shot_numbers.append(number)
            fragment_review["shots"].append({
                "number": number,
                "start_s": _reading_seconds(shot.group("start")),
                "end_s": _reading_seconds(shot.group("end")),
            })
            camera = [part.strip() for part in shot.group("camera").split("｜")]
            if len(camera) != 4 or not all(camera):
                error("storyboard_reading_shot_invalid", f"镜头{number} 的方括号必须依次填写景别、视角、主运镜、机位/角度四项。")
            body = shot.group("body")
            missing = [label for label in ("声音：", "人声：", "切入：", "切出：") if label not in body]
            if missing:
                error("storyboard_reading_shot_invalid", f"镜头{number} 缺少必备字段：{'、'.join(missing)}")
            visual = body.split("声音：", 1)[0]
            action = visual.split("画面：", 1)[1] if "画面：" in visual else visual
            internal_cut = next(
                (
                    match for match in READING_INTERNAL_CUT.finditer(action)
                    if action[:match.start()].strip(" \t；;。！？!?，,")
                ),
                None,
            )
            if internal_cut is not None:
                error("storyboard_reading_internal_cut", f"镜头{number} 在已建立的画面动作后又明确写“{internal_cut.group(0)}”，必须另建 SHOT；正常切入、连续运镜或焦点转移不属于此错误。")
        if len(current_numbers) != declared_count:
            error("storyboard_reading_shot_count_mismatch", f"片段标题声明 {declared_count} 个镜头，正文实际有 {len(current_numbers)} 个有效镜头条目。")
        if current_numbers != list(range(1, len(current_numbers) + 1)):
            error("storyboard_reading_shot_count_mismatch", "每个片段内的镜头编号必须从 1 开始连续递增。")

    if not reference_style and len(nonempty) >= 2:
        duration = re.match(r"^> 全片\s*(\d+(?:\.\d+)?)\s*秒[，,]", nonempty[1][1])
        if duration is not None:
            review["duration_s"] = float(duration.group(1))
        counts = re.search(r"共\s*(\d+)\s*章\s*(\d+)\s*个片段[、，,]\s*(\d+)\s*个镜头", nonempty[1][1])
        if counts is None:
            error("storyboard_reading_summary_invalid", "全片总览必须按“共 X 章 Y 个片段、Z 个镜头”写明数量。")
        else:
            actual = (len(chapters), len(fragments), len(shot_numbers))
            expected = tuple(int(value) for value in counts.groups())
            if actual != expected:
                error("storyboard_reading_count_mismatch", f"全片总览数量 {expected} 与正文实际数量 {actual} 不一致。")
    elif reference_style and fragments:
        review["duration_s"] = _reading_seconds(fragments[-1][1].group("end"))
    review["alignment_ready"] = all(
        item["code"] == "storyboard_reading_internal_cut"
        for item in issues[issue_start:]
    )
    return review


def check_storyboard_reading_alignment(
    review: dict[str, Any] | None,
    data: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    if review is None or not review.get("alignment_ready"):
        return
    path = review["path"]
    shots = data.get("shots")
    segments = data.get("segments")
    if not isinstance(shots, list) or not isinstance(segments, list):
        return

    def valid_duration(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    shot_by_id = {
        shot.get("shot_id"): shot for shot in shots
        if isinstance(shot, dict) and isinstance(shot.get("shot_id"), str)
    }
    timing_ready = all(
        isinstance(segment, dict)
        and valid_duration(segment.get("duration_s"))
        and isinstance(segment.get("shot_ids"), list)
        and all(isinstance(shot_id, str) for shot_id in segment["shot_ids"])
        and len(segment["shot_ids"]) == len(set(segment["shot_ids"]))
        and all(
            shot_id in shot_by_id and valid_duration(shot_by_id[shot_id].get("duration_s"))
            for shot_id in segment["shot_ids"]
        )
        for segment in segments
    )
    if not timing_ready:
        return

    def error(code: str, message: str) -> None:
        issues.append(issue("error", code, message, path))

    storyboard_duration = data.get("duration_s")
    if review["duration_s"] is not None and valid_duration(storyboard_duration) \
            and not _reading_time_matches(review["duration_s"], float(storyboard_duration)):
        error("storyboard_reading_duration_mismatch", "阅读稿总时长（旧模板总览或参考版末段结束时间）必须与 storyboard.duration_s 一致。")
    fragments = review["fragments"]
    if len(fragments) != len(segments):
        error("storyboard_reading_segment_count_mismatch", f"阅读稿有 {len(fragments)} 个片段，storyboard 有 {len(segments)} 个 SEG；二者必须按顺序一一对应。")
    segment_start = 0.0
    for index, segment in enumerate(segments):
        segment_id = segment.get("segment_id") or f"第{index + 1}段"
        segment_end = segment_start + float(segment["duration_s"])
        if index >= len(fragments):
            segment_start = segment_end
            continue
        fragment = fragments[index]
        if not _reading_time_matches(fragment["start_s"], segment_start) \
                or not _reading_time_matches(fragment["end_s"], segment_end):
            error("storyboard_reading_segment_time_mismatch", f"阅读稿第 {index + 1} 个片段的绝对起止时间必须与 {segment_id} 在分镜时间轴中的起止时间一致。")
        shot_ids = segment["shot_ids"]
        reading_shots = fragment["shots"]
        if len(reading_shots) != len(shot_ids) or fragment["declared_count"] != len(shot_ids):
            error("storyboard_reading_segment_shot_mismatch", f"阅读稿第 {index + 1} 个片段声明及实际镜头数必须与 {segment_id}.shot_ids 一致。")
            segment_start = segment_end
            continue
        cursor = segment_start
        for shot_id, reading_shot in zip(shot_ids, reading_shots):
            expected_end = cursor + float(shot_by_id[shot_id]["duration_s"])
            if not _reading_time_matches(reading_shot["start_s"], cursor) \
                    or not _reading_time_matches(reading_shot["end_s"], expected_end):
                error("storyboard_reading_shot_time_mismatch", f"阅读稿第 {index + 1} 个片段的镜头{reading_shot['number']} 与 {shot_id} 的顺序、起止时间或逐镜时长不一致。")
            cursor = expected_end
        segment_start = segment_end


def check_storyboards(root: Path, expected_durations: dict[str, int | None], plan: Any, issues: list[dict[str, Any]], episode_filter: str | None = None) -> None:
    lightweight = ProductionPlan(plan).lightweight_valid
    for episode_id, episode_root in episode_dirs(root, episode_filter):
        reading_path = episode_root / f"02_分镜/分镜_阅读稿_{episode_id}.md"
        reading_review = check_storyboard_reading(reading_path, issues) \
            if not lightweight and reading_path.is_file() else None
        path = episode_root / f"02_分镜/storyboard_{episode_id}.json"
        data = load_json(path, issues, required=False)
        if not isinstance(data, dict):
            continue
        if data.get("episode_id") != episode_id:
            issues.append(issue("error", "episode_id_mismatch", "storyboard episode_id 与目录不一致。", path))
        expected_duration = expected_durations.get(episode_id)
        if not _finite_positive_number(data.get("duration_s")):
            issues.append(issue("error", "storyboard_duration_invalid", "storyboard.duration_s 必须是有限正数。", path))
        if expected_duration is not None and _finite_positive_number(data.get("duration_s")) and abs(float(data["duration_s"]) - expected_duration) > 1e-6:
            issues.append(issue("error", "storyboard_duration_mismatch", "参考版准确秒数或 user_locked 精确时长要求下，分镜实际总时长必须等于已确认的本集执行时长。", path))
        check_declared_video_models(data, path, "storyboard", issues)
        if not _check_storyboard_files(root, episode_id, data, path, issues):
            continue
        check_storyboard_reading_alignment(reading_review, data, issues)
        shots = data["shots"]
        segments = data["segments"]
        structure = StoryboardStructure.build(shots, segments, path, issues)
        director_path = relative_file(root, data.get("director_control_card"))
        if not lightweight and director_path is not None and director_path.is_file():
            check_director_deletion_review(director_path, segments, issues)
        if structure.shot_durations and _finite_positive_number(data.get("duration_s")):
            if abs(float(data["duration_s"]) - sum(float(v) for v in structure.shot_durations.values())) > 1e-6:
                issues.append(issue("error", "shot_duration_total_mismatch", "shots.duration_s 之和必须等于 storyboard.duration_s；自然吸收后的最终逐镜时长不得只靠四舍五入闭合。", path))
        covered: list[str] = []
        for index, segment in enumerate(segments, start=1):
            if not isinstance(segment, dict):
                continue
            _check_segment_structure(segment, index, len(segments), structure, covered, path, issues)
        check_episode_keyframe_request_plan(segments, lightweight, path, issues)
        missing = structure.shot_ids - set(covered)
        duplicated = {shot_id for shot_id in covered if covered.count(shot_id) > 1}
        if missing:
            issues.append(issue("error", "shots_not_covered", f"以下镜头未被任何 segment 覆盖：{sorted(missing)}", path))
        if duplicated:
            issues.append(issue("error", "shots_covered_multiple_times", f"以下镜头被多个 segment 重复覆盖：{sorted(duplicated)}", path))
        unknown_segment_refs = {seg for seg in structure.shot_to_segment.values() if isinstance(seg, str) and seg not in structure.segment_ids}
        if unknown_segment_refs:
            issues.append(issue("error", "shot_unknown_segment", f"shots 中引用了不存在的 segment_id：{sorted(unknown_segment_refs)}", path))
        AudienceExecutionContract(data.get("audience_execution"), plan, structure.shot_ids, structure.scene_ids, path, issues).validate()
        check_highlight_contracts(root, episode_id, data, structure, lightweight, path, issues)
