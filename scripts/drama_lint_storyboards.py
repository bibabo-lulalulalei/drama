from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
            shot_durations={
                item.get("shot_id"): item.get("duration_s")
                for item in shots
                if isinstance(item, dict) and isinstance(item.get("shot_id"), str) and isinstance(item.get("duration_s"), (int, float))
            },
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
    if isinstance(segment.get("duration_s"), (int, float)):
        declared = int(round(float(segment["duration_s"])))
        calculated = int(round(sum(float(structure.shot_durations[s]) for s in segment_shots if s in structure.shot_durations)))
        if calculated and declared != calculated:
            issues.append(issue("error", "segment_duration_mismatch", f"{segment_id} duration_s 必须等于其 shot_ids 时长之和。", path))
        check_segment_shot_count(segment_id, declared, len(segment_shots), segment.get("shot_mode"), segment.get("density_profile"), path, issues)
    tail_mode = segment.get("tail_mode")
    if tail_mode not in TAIL_MODES:
        issues.append(issue("error", "segment_tail_mode_invalid", f"{segment_id or index} tail_mode 无效。", path))
    if index < segment_count and tail_mode == TailMode.STABLE_HOLD.value and not has_meaningful_value(segment.get("tail_hold_reason")):
        issues.append(issue("error", "intermediate_stable_hold_reason_missing", f"{segment_id or index} 是中间片段，使用 stable_hold 时必须填写 tail_hold_reason。", path))
    check_reference_plan(segment, path, issues)


READING_TIME = r"\d{2}:\d{2}(?:\.\d+)?"
READING_NUMBER = r"0-9零〇一二三四五六七八九十百千万两"
READING_TITLE = re.compile(rf"^# 第[{READING_NUMBER}]+集：\S.* · 分镜阅读稿$")
READING_CHAPTER = re.compile(
    rf"^## 第[{READING_NUMBER}]+章：.+（本章时长：约\s*\d+(?:\.\d+)?\s*秒 / {READING_TIME} - {READING_TIME}）$"
)
READING_FRAGMENT = re.compile(
    rf"^### 片段[{READING_NUMBER}]+：.+（{READING_TIME} - {READING_TIME}，本段包含 (\d+) 个镜头）$"
)
READING_SHOT = re.compile(
    rf"^- \*\*镜头(\d+) \({READING_TIME}-{READING_TIME}\)\*\*：\[([^\]\n]+)\]\s*(.*)$"
)


def check_storyboard_reading(path: Path, issues: list[dict[str, Any]]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        issues.append(issue("error", "storyboard_reading_unreadable", f"分镜阅读稿无法读取：{exc}", path))
        return
    lines = text.splitlines()
    nonempty = [(index, line.strip()) for index, line in enumerate(lines) if line.strip()]

    def error(code: str, message: str) -> None:
        issues.append(issue("error", code, message, path))

    if not nonempty or READING_TITLE.fullmatch(nonempty[0][1]) is None:
        error("storyboard_reading_title_invalid", "分镜阅读稿首行必须采用“# 第X集：标题 · 分镜阅读稿”。")
    if len(nonempty) < 2 or re.match(r"^> 全片\s*\d+(?:\.\d+)?\s*秒[，,]", nonempty[1][1]) is None:
        error("storyboard_reading_summary_invalid", "标题后必须用一行引用写明全片秒数、画幅、画风及真实章节、片段和镜头总数。")
    if len(nonempty) < 3 or nonempty[2][1] != "## 本集故事提要":
        error("storyboard_reading_structure_invalid", "全片总览后必须紧接“## 本集故事提要”，不得替换为“本集镜头方案”或“逐段阅读”。")
    if any(re.match(r"^\s*\|.*\|\s*$", line) for line in lines):
        error("storyboard_reading_table_forbidden", "分镜阅读稿必须使用逐镜无序列表，不得使用 Markdown 表格；表格只保留在内部完整分镜表。")

    chapters: list[tuple[int, re.Match[str]]] = []
    fragments: list[tuple[int, re.Match[str]]] = []
    summary_headings = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        chapter = READING_CHAPTER.fullmatch(stripped)
        fragment = READING_FRAGMENT.fullmatch(stripped)
        if chapter is not None:
            chapters.append((index, chapter))
        if fragment is not None:
            fragments.append((index, fragment))
        if stripped == "## 本集故事提要":
            summary_headings += 1
        if re.match(r"^#{1,6}\s+", stripped) and not any((
            READING_TITLE.fullmatch(stripped),
            stripped == "## 本集故事提要",
            chapter,
            fragment,
        )):
            error("storyboard_reading_structure_invalid", f"阅读稿标题层级或名称不符合固定模板：{stripped}")
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
        declared_count = int(fragment.group(1))
        current_numbers: list[int] = []
        for line_index in range(fragment_index + 1, section_end):
            stripped = lines[line_index].strip()
            if not stripped.startswith("- "):
                continue
            shot = READING_SHOT.fullmatch(stripped)
            if shot is None:
                error("storyboard_reading_shot_invalid", f"第 {line_index + 1} 行必须采用固定逐镜条目格式：{stripped}")
                continue
            number = int(shot.group(1))
            current_numbers.append(number)
            shot_numbers.append(number)
            camera = [part.strip() for part in shot.group(2).split("｜")]
            if len(camera) != 4 or not all(camera):
                error("storyboard_reading_shot_invalid", f"镜头{number} 的方括号必须依次填写景别、视角、主运镜、机位/角度四项。")
            body = shot.group(3)
            missing = [label for label in ("声音：", "人声：", "切入：", "切出：") if label not in body]
            if missing:
                error("storyboard_reading_shot_invalid", f"镜头{number} 缺少必备字段：{'、'.join(missing)}")
        if len(current_numbers) != declared_count:
            error("storyboard_reading_shot_count_mismatch", f"片段标题声明 {declared_count} 个镜头，正文实际有 {len(current_numbers)} 个有效镜头条目。")
        if current_numbers != list(range(1, len(current_numbers) + 1)):
            error("storyboard_reading_shot_count_mismatch", "每个片段内的镜头编号必须从 1 开始连续递增。")

    if len(nonempty) >= 2:
        counts = re.search(r"共\s*(\d+)\s*章\s*(\d+)\s*个片段[、，,]\s*(\d+)\s*个镜头", nonempty[1][1])
        if counts is None:
            error("storyboard_reading_summary_invalid", "全片总览必须按“共 X 章 Y 个片段、Z 个镜头”写明数量。")
        else:
            actual = (len(chapters), len(fragments), len(shot_numbers))
            expected = tuple(int(value) for value in counts.groups())
            if actual != expected:
                error("storyboard_reading_count_mismatch", f"全片总览数量 {expected} 与正文实际数量 {actual} 不一致。")


def check_storyboards(root: Path, expected_durations: dict[str, int | None], plan: Any, issues: list[dict[str, Any]], episode_filter: str | None = None) -> None:
    lightweight = ProductionPlan(plan).lightweight_valid
    for episode_id, episode_root in episode_dirs(root, episode_filter):
        reading_path = episode_root / f"02_分镜/分镜_阅读稿_{episode_id}.md"
        if not lightweight and reading_path.is_file():
            check_storyboard_reading(reading_path, issues)
        path = episode_root / f"02_分镜/storyboard_{episode_id}.json"
        data = load_json(path, issues, required=False)
        if not isinstance(data, dict):
            continue
        if data.get("episode_id") != episode_id:
            issues.append(issue("error", "episode_id_mismatch", "storyboard episode_id 与目录不一致。", path))
        expected_duration = expected_durations.get(episode_id)
        if expected_duration is not None and isinstance(data.get("duration_s"), (int, float)) and not isinstance(data.get("duration_s"), bool) and int(round(float(data["duration_s"]))) != expected_duration:
            issues.append(issue("error", "storyboard_duration_mismatch", "user_locked 精确时长要求下，分镜实际总时长必须等于锁定的本集执行时长。", path))
        check_declared_video_models(data, path, "storyboard", issues)
        if not _check_storyboard_files(root, episode_id, data, path, issues):
            continue
        shots = data["shots"]
        segments = data["segments"]
        structure = StoryboardStructure.build(shots, segments, path, issues)
        if structure.shot_durations and isinstance(data.get("duration_s"), (int, float)):
            if int(round(float(data["duration_s"]))) != int(round(sum(float(v) for v in structure.shot_durations.values()))):
                issues.append(issue("error", "shot_duration_total_mismatch", "shots.duration_s 之和必须等于 storyboard.duration_s。", path))
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
