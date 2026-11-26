from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
from typing import Any, Protocol

if __package__:
    from .drama_lint_assets import check_asset_ref, check_state_ref
    from .drama_lint_confirmations import load_confirmation_records
    from .drama_lint_domain import (
        AUDIO_INPUT_ROLES,
        FRAME_REFERENCE_POSITIONS,
        H3_CAPABILITIES,
        H3_MODES,
        IMAGE_INPUT_SUFFIXES,
        REFERENCE_ROLES,
        STATE_REFERENCE_ROLES,
        VIDEO_INPUT_ROLES,
        check_declared_video_models,
        check_h3_duration,
        check_unique,
        check_video_model,
        episode_dirs,
        file_exists,
        file_sha256,
        is_lightweight_plan,
        issue,
        lightweight_constraints_valid,
        load_json,
        relative_file,
    )
    from .drama_lint_prompts import (
        check_director_draft_prompt,
        check_h3_final_prompt,
        check_h3_skill_conversion,
        check_prompt_preflight,
    )
    from .drama_lint_storyboards import load_storyboard_index, video_model_name
    from .drama_lint_video_confirmations import check_video_generation_confirmations
else:
    from drama_lint_assets import check_asset_ref, check_state_ref
    from drama_lint_confirmations import load_confirmation_records
    from drama_lint_domain import (
        AUDIO_INPUT_ROLES,
        FRAME_REFERENCE_POSITIONS,
        H3_CAPABILITIES,
        H3_MODES,
        IMAGE_INPUT_SUFFIXES,
        REFERENCE_ROLES,
        STATE_REFERENCE_ROLES,
        VIDEO_INPUT_ROLES,
        check_declared_video_models,
        check_h3_duration,
        check_unique,
        check_video_model,
        episode_dirs,
        file_exists,
        file_sha256,
        is_lightweight_plan,
        issue,
        lightweight_constraints_valid,
        load_json,
        relative_file,
    )
    from drama_lint_prompts import (
        check_director_draft_prompt,
        check_h3_final_prompt,
        check_h3_skill_conversion,
        check_prompt_preflight,
    )
    from drama_lint_storyboards import load_storyboard_index, video_model_name
    from drama_lint_video_confirmations import check_video_generation_confirmations


class VideoStatus(str, Enum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class VideoToolMode(str, Enum):
    TEXT_TO_VIDEO = "text_to_video"
    MEDIA_TO_VIDEO = "media_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    VIDEO_EDIT = "video_edit"


VIDEO_STATUS_VALUES = {status.value for status in VideoStatus}
VIDEO_TOOL_MODES = {mode.value for mode in VideoToolMode}
H3_TOOL_MODE_MAPPING = {
    VideoToolMode.TEXT_TO_VIDEO.value: {"T2VA"},
    VideoToolMode.IMAGE_TO_VIDEO.value: {"I2VA", "FL2VA", "L2VA", "Ref2VA"},
    VideoToolMode.MEDIA_TO_VIDEO.value: {"Ref2VA"},
    VideoToolMode.VIDEO_EDIT.value: {"Ref2VA"},
}


def video_reference_inputs(segment: dict[str, Any], path: Path, issues: list[dict[str, Any]]) -> list[Any]:
    actual = segment.get("reference_inputs")
    if "planned_reference_inputs" in segment:
        issues.append(issue("error", "video_planned_tail_not_allowed", f"{segment.get('segment_id') or 'segment'} 不得使用 planned_reference_inputs；continuous 确认前必须登记真实 tail reference_inputs。", path))
    if isinstance(actual, list) and any(isinstance(item, dict) and "previous_tail_of" in item for item in actual):
        issues.append(issue("error", "video_planned_tail_in_actual_inputs", f"{segment.get('segment_id') or 'segment'} 的 reference_inputs 不得动态引用未来 tail；必须改用已存在文件的 source_type=frame 和真实 source_id。", path))
    return actual if actual is not None else []


def ordered_inputs(root: Path, items: Any, allowed_roles: set[str], kind: str, path: Path, issues: list[dict[str, Any]]) -> tuple[list[int], set[str]]:
    if items is None:
        return [], set()
    if not isinstance(items, list):
        issues.append(issue("error", f"{kind}_inputs_invalid", f"{kind}_inputs 必须是数组。", path))
        return [], set()
    orders: list[int] = []
    roles: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            issues.append(issue("error", f"{kind}_input_invalid", f"{kind}_inputs 每项必须是对象。", path))
            continue
        order = item.get("order")
        if isinstance(order, int) and not isinstance(order, bool):
            orders.append(order)
        else:
            issues.append(issue("error", f"{kind}_input_order_invalid", f"{kind}_inputs.order 必须是整数。", path))
        role = item.get("role")
        if role in allowed_roles:
            roles.add(role)
        elif allowed_roles:
            issues.append(issue("error", f"{kind}_input_role_invalid", f"{kind}_inputs.role 无效：{role}", path))
        required_fields = ("source_id", "file", "adopt", "exclude") if kind == "reference" else ("resource_id", "file", "adopt", "exclude")
        for field in required_fields:
            if not str(item.get(field) or "").strip():
                issues.append(issue("error", f"{kind}_input_field_missing", f"{kind}_inputs.{field} 必须填写。", path))
        file_value = item.get("file")
        if file_value and not file_exists(root, file_value):
            issues.append(issue("error", f"{kind}_input_file_missing", f"输入文件不存在或不是项目相对路径：{file_value}", path))
        if kind == "reference" and isinstance(file_value, str) and Path(file_value).suffix.lower() not in IMAGE_INPUT_SUFFIXES:
            issues.append(issue("error", "reference_input_file_suffix_invalid", f"reference_inputs.file 必须是图片文件：{file_value}", path))
    if orders and sorted(orders) != list(range(1, len(orders) + 1)):
        issues.append(issue("error", f"{kind}_input_order_not_contiguous", f"{kind}_inputs.order 必须从 1 连续递增。", path))
    return orders, roles


def load_keyframe_ids(root: Path, episode_id: str, issues: list[dict[str, Any]]) -> set[str]:
    path = root / f"episodes/{episode_id}/03_资产/keyframe_manifest_{episode_id}.json"
    data = load_json(path, issues, required=False)
    keyframes = data.get("keyframes") if isinstance(data, dict) else None
    if not isinstance(keyframes, list):
        return set()
    return {item.get("keyframe_id") for item in keyframes if isinstance(item, dict) and isinstance(item.get("keyframe_id"), str)}


def media_duration_s(item: dict[str, Any]) -> float | None:
    for field in ("duration_s", "uploaded_duration_s", "input_duration_s", "trimmed_duration_s", "source_duration_s"):
        value = item.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def check_h3_media_inputs(segment: dict[str, Any], path: Path, issues: list[dict[str, Any]]) -> None:
    mode = segment.get("h3_mode")
    if not isinstance(mode, str):
        return
    mode = mode.strip()
    limits = H3_CAPABILITIES["mode_ref_limits"].get(mode)
    if limits is None:
        return
    label = str(segment.get("segment_id") or "segment")
    actual_images = segment.get("reference_inputs")
    groups = {
        "image": actual_images,
        "video": segment.get("video_inputs"),
        "audio": segment.get("audio_inputs"),
    }
    counts = {kind: len(items) if isinstance(items, list) else 0 for kind, items in groups.items()}
    for kind, plural in (("image", "images"), ("video", "videos"), ("audio", "audios")):
        cap = limits[plural + "_max"]
        if counts[kind] > cap:
            issues.append(issue("error", f"h3_{kind}_input_count_over_limit", f"{label} 的 H3 {mode} 最多接受 {cap} 个 {kind} 参考。", path))
    if mode == "FL2VA" and counts["image"] != 2:
        issues.append(issue("error", "h3_first_last_frame_count_invalid", f"{label} FL2VA 必须恰好传入 2 张图片。", path))
    if mode in {"I2VA", "L2VA"} and counts["image"] != 1:
        issues.append(issue("error", "h3_frame_input_count_invalid", f"{label} {mode} 必须恰好传入 1 张实际首帧或尾帧；普通参考使用 Ref2VA。", path))
    image_inputs = groups["image"] if isinstance(groups["image"], list) else []
    if mode in {"I2VA", "FL2VA", "L2VA"}:
        expected_positions = ["first", "last"] if mode == "FL2VA" else ["last" if mode == "L2VA" else "first"]
        for position, item in enumerate(image_inputs):
            if not isinstance(item, dict):
                continue
            expected = expected_positions[position] if position < len(expected_positions) else None
            role = item.get("role")
            if expected is None or item.get("frame_position") != expected or FRAME_REFERENCE_POSITIONS.get(str(role)) != expected or item.get("order") != position + 1 or item.get("source_type") == "keyframe":
                issues.append(issue("error", "h3_frame_reference_invalid", f"{label} {mode} 第 {position + 1} 张必须是明确登记的实际 {expected or '有效'} frame；身份、场景、高光和群众图不能用作帧模式输入。", path))
    else:
        for item in image_inputs:
            if isinstance(item, dict) and (item.get("frame_position") is not None or str(item.get("role")) in FRAME_REFERENCE_POSITIONS):
                issues.append(issue("error", "h3_frame_reference_mode_mismatch", f"{label} 的实际首尾帧职责只能用于对应帧模式；Ref2VA 普通参考不得登记 frame_position。", path))
    if mode == "Ref2VA" and not any(counts.values()):
        issues.append(issue("error", "h3_reference_input_missing", f"{label} Ref2VA 必须有真实参考输入。", path))
    if limits.get("audio_requires_visual_input") and counts["audio"] and not (counts["image"] or counts["video"]):
        issues.append(issue("error", "h3_audio_requires_visual_input", f"{label} 的 H3 音频参考必须同时有图片或视频输入。", path))
    total_cap = limits.get("total_files_max")
    if total_cap is not None and sum(counts.values()) > total_cap:
        issues.append(issue("error", "h3_total_input_count_over_limit", f"{label} 的 H3 参考文件总数不得超过 {total_cap}。", path))
    for kind in ("video", "audio"):
        per_clip = limits.get(kind + "_per_clip_s")
        total_limit = limits.get(kind + "_total_s")
        if per_clip is None or total_limit is None:
            continue
        total = 0.0
        items = groups[kind] if isinstance(groups[kind], list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            duration = media_duration_s(item)
            if duration is None:
                issues.append(issue("error", f"h3_{kind}_input_duration_missing", f"{label} 的每个 {kind} 参考必须登记实际时长，才能核验 H3 参考上限。", path))
                continue
            if not math.isfinite(duration) or not per_clip[0] <= duration <= per_clip[1]:
                issues.append(issue("error", f"h3_{kind}_input_duration_invalid", f"{label} 每个 {kind} 参考必须为 {per_clip[0]}-{per_clip[1]} 秒。", path))
            if math.isfinite(duration):
                total += duration
        if total > total_limit:
            issues.append(issue("error", f"{kind}_inputs_duration_over_limit", f"{label} 上传 {kind} 参考总时长 {total:g} 秒，H3 上限为 {total_limit} 秒。", path))


def check_video_state_refs(segment: dict[str, Any], image_roles: set[str], asset_index: dict[str, Any], path: Path, issues: list[dict[str, Any]]) -> None:
    if not (image_roles & STATE_REFERENCE_ROLES):
        return
    references = segment.get("reference_inputs")
    state_role_references = [
        item for item in references if isinstance(item, dict) and item.get("role") in STATE_REFERENCE_ROLES
    ] if isinstance(references, list) else []
    base_asset_refs = {
        item.get("source_id") for item in state_role_references
        if item.get("source_type") == "asset"
        and isinstance(item.get("source_id"), str)
        and item.get("source_id") in asset_index["known_version_refs"]
    }
    if state_role_references and len(base_asset_refs) == len(state_role_references):
        return
    state_refs = segment.get("state_refs")
    if not isinstance(state_refs, list) or not state_refs:
        issues.append(issue("error", "video_state_refs_missing", f"{segment.get('segment_id') or 'segment'} 传入独立角色/道具状态资产时必须登记 approved state_refs；直接以 approved 基准资产锁定当前状态时按资产版本核验。", path))
        return
    for ref in state_refs:
        check_state_ref(ref, asset_index, path, issues, str(segment.get("segment_id") or "视频片段"))


def check_voice_audio_inputs(segment: dict[str, Any], audio_roles: set[str], path: Path, issues: list[dict[str, Any]]) -> None:
    speech_lines = segment.get("speech_lines")
    if not isinstance(speech_lines, list) or not speech_lines:
        return
    segment_label = str(segment.get("segment_id") or "segment")
    audio_input_supported = segment.get("audio_input_supported") is True
    has_voice_audio_reference = "voice_audio_reference" in audio_roles
    voice_inputs = segment.get("voice_inputs")

    if not audio_input_supported and not has_voice_audio_reference:
        if isinstance(voice_inputs, list) and voice_inputs:
            issues.append(issue("error", "voice_inputs_without_audio_reference", f"{segment_label} 未传 VOICE 音频时不得登记 voice_inputs；请改用 speech_lines.voice_anchor 作为文字音色锚点。", path))
        for index, line in enumerate(speech_lines, start=1):
            if not isinstance(line, dict):
                continue
            if not str(line.get("voice_anchor") or "").strip():
                issues.append(issue("error", "speech_line_voice_anchor_missing", f"{segment_label} speech_lines 第 {index} 条未传 VOICE 音频时必须填写固定 voice_anchor。", path))
        return

    if audio_input_supported and not has_voice_audio_reference:
        issues.append(issue("error", "voice_audio_input_missing", f"{segment_label} 支持音频输入且有 speech_lines 时必须上传 approved VOICE 音频。", path))
    if has_voice_audio_reference and not audio_input_supported:
        issues.append(issue("error", "voice_audio_support_flag_missing", f"{segment_label} 已传 voice_audio_reference 时 audio_input_supported 必须为 true。", path))
    if not isinstance(voice_inputs, list) or not voice_inputs:
        issues.append(issue("error", "voice_inputs_missing", f"{segment_label} 有 speech_lines 时必须登记 voice_inputs。", path))
        return
    voice_ids = {
        item.get("voice_id")
        for item in voice_inputs
        if isinstance(item, dict) and isinstance(item.get("voice_id"), str) and item.get("voice_id").strip()
    }
    resource_ids = {
        item.get("resource_id")
        for item in voice_inputs
        if isinstance(item, dict) and isinstance(item.get("resource_id"), str) and item.get("resource_id").strip()
    }
    if not voice_ids or not resource_ids:
        issues.append(issue("error", "voice_inputs_incomplete", f"{segment_label} voice_inputs 必须填写 voice_id 和 resource_id。", path))
    for index, line in enumerate(speech_lines, start=1):
        if not isinstance(line, dict):
            continue
        voice_id = line.get("voice_id")
        if isinstance(voice_id, str) and voice_id.strip() and voice_id not in voice_ids:
            issues.append(issue("error", "speech_line_voice_input_missing", f"{segment_label} speech_lines 第 {index} 条 voice_id 未在 voice_inputs 中登记：{voice_id}", path))


def check_voice_anchor_consistency(segment: dict[str, Any], seen: dict[str, str], path: Path, issues: list[dict[str, Any]]) -> None:
    speech_lines = segment.get("speech_lines")
    if not isinstance(speech_lines, list):
        return
    segment_label = str(segment.get("segment_id") or "segment")
    for index, line in enumerate(speech_lines, start=1):
        if not isinstance(line, dict):
            continue
        voice_id = str(line.get("voice_id") or "").strip()
        if not voice_id:
            continue
        voice_anchor = str(line.get("voice_anchor") or "").strip()
        if not voice_anchor:
            issues.append(issue("error", "speech_line_voice_anchor_missing", f"{segment_label} speech_lines 第 {index} 条有 voice_id 但缺少固定 voice_anchor。", path))
            continue
        previous = seen.get(voice_id)
        if previous is None:
            seen[voice_id] = voice_anchor
        elif previous != voice_anchor:
            issues.append(issue("error", "speech_line_voice_anchor_inconsistent", f"{segment_label} speech_lines 第 {index} 条 voice_id={voice_id} 的 voice_anchor 必须与同一人物前文完全一致。", path))


class VideoRouteStrategy(Protocol):
    def validate(self, context: "VideoSegmentContext") -> None:
        ...


@dataclass
class VideoSegmentContext:
    root: Path
    plan: Any
    data: dict[str, Any]
    index: dict[str, Any]
    keyframe_ids: set[str]
    asset_index: dict[str, Any]
    lightweight: bool
    path: Path
    issues: list[dict[str, Any]]
    segment: dict[str, Any]
    image_orders: list[int]
    image_roles: set[str]
    video_orders: list[int]
    video_roles: set[str]
    audio_orders: list[int]
    audio_roles: set[str]
    require_accepted: bool

    @property
    def segment_id(self) -> Any:
        return self.segment.get("segment_id")

    @property
    def tool_mode(self) -> Any:
        return self.segment.get("tool_mode")

    @property
    def required_roles(self) -> Any:
        return self.segment.get("required_reference_roles")

    @property
    def planned_roles(self) -> set[str]:
        return self.index["required_reference_roles"].get(self.segment_id, set()) if isinstance(self.segment_id, str) else set()

    @property
    def declared_roles(self) -> set[str]:
        return set(self.required_roles) if isinstance(self.required_roles, list) else set()

    def report(self, code: str, message: str, path: Path | None = None) -> None:
        self.issues.append(issue("error", code, message, path or self.path))

    def check_storyboard_roles(self) -> None:
        planned_roles = self.planned_roles
        if planned_roles and not planned_roles.issubset(self.declared_roles):
            missing = sorted(planned_roles - self.declared_roles)
            self.report("storyboard_required_role_not_inherited", f"{self.segment_id} 未继承 storyboard.required_reference_roles：{missing}")
        if planned_roles and not planned_roles.issubset(self.image_roles):
            missing = sorted(planned_roles - self.image_roles)
            self.report("storyboard_required_role_not_passed", f"{self.segment_id} 的 storyboard.required_reference_roles 未真实传入：{missing}")


class TextToVideoStrategy:
    def validate(self, context: VideoSegmentContext) -> None:
        if context.image_orders or context.video_orders or context.audio_orders or context.segment.get("voice_inputs"):
            context.report("text_to_video_input_invalid", "text_to_video 只能用于没有图片、视频、音频或 voice_inputs 的片段。")


class MediaToVideoStrategy:
    def validate(self, context: VideoSegmentContext) -> None:
        check_voice_audio_inputs(context.segment, context.audio_roles, context.path, context.issues)
        check_video_state_refs(context.segment, context.image_roles, context.asset_index, context.path, context.issues)
        if not context.video_orders and not context.audio_orders:
            context.report("media_to_video_media_missing", "media_to_video 必须至少登记一个真实视频或音频输入。")
        required_roles = context.required_roles
        if context.image_orders or context.planned_roles:
            if not isinstance(required_roles, list) or not required_roles:
                context.report("required_reference_roles_missing", "media_to_video 使用图片或分镜声明图片职责时必须填写 required_reference_roles。")
            elif any(role not in REFERENCE_ROLES for role in required_roles):
                context.report("required_reference_role_invalid", "required_reference_roles 含无效职责。")
            elif not set(required_roles).issubset(context.image_roles):
                missing = sorted(set(required_roles) - context.image_roles)
                context.report("required_reference_role_not_passed", f"required_reference_roles 未真实传入：{missing}")
        elif required_roles not in (None, []):
            context.report("required_reference_roles_unexpected", "media_to_video 没有图片输入时 required_reference_roles 应为空或省略。")
        context.check_storyboard_roles()


class ImageToVideoStrategy:
    def validate(self, context: VideoSegmentContext) -> None:
        check_video_state_refs(context.segment, context.image_roles, context.asset_index, context.path, context.issues)
        if not context.image_orders:
            context.report("image_to_video_reference_missing", "image_to_video 必须登记实际传入参考图。")
        if context.video_orders or context.audio_orders or context.segment.get("voice_inputs"):
            context.report("image_to_video_input_invalid", "image_to_video 不支持上传视频、音频或 voice_inputs；本路由只能传参考图。")
        required_roles = context.required_roles
        if not isinstance(required_roles, list) or not required_roles:
            context.report("required_reference_roles_missing", "image_to_video 必须声明 required_reference_roles。")
        elif any(role not in REFERENCE_ROLES for role in required_roles):
            context.report("required_reference_role_invalid", "required_reference_roles 含无效职责。")
        elif not set(required_roles).issubset(context.image_roles):
            missing = sorted(set(required_roles) - context.image_roles)
            context.report("required_reference_role_not_passed", f"required_reference_roles 未真实传入：{missing}")
        context.check_storyboard_roles()


class VideoEditStrategy:
    def validate(self, context: VideoSegmentContext) -> None:
        if context.image_orders or context.audio_orders or context.segment.get("voice_inputs"):
            context.report("video_edit_input_invalid", "video_edit 只登记源视频，不登记图片、音频或 voice_inputs。")
        if context.video_roles != {"source_video_for_edit"} or len(context.video_orders) != 1:
            context.report("video_edit_source_invalid", "video_edit 必须且只能登记一个 source_video_for_edit 源视频。")


VIDEO_ROUTE_STRATEGIES: dict[str, VideoRouteStrategy] = {
    VideoToolMode.TEXT_TO_VIDEO.value: TextToVideoStrategy(),
    VideoToolMode.MEDIA_TO_VIDEO.value: MediaToVideoStrategy(),
    VideoToolMode.IMAGE_TO_VIDEO.value: ImageToVideoStrategy(),
    VideoToolMode.VIDEO_EDIT.value: VideoEditStrategy(),
}


class SegmentPromptPipeline:
    def __init__(self, context: VideoSegmentContext) -> None:
        self.context = context

    def run(self) -> None:
        context = self.context
        segment = context.segment
        segment_id = context.segment_id
        path = context.path
        issues = context.issues
        prompt_file = segment.get("compiled_prompt_file")
        prompt_path = relative_file(context.root, prompt_file)
        if context.lightweight:
            raw_shot_ids = segment.get("shot_ids")
            expected_shot_ids = raw_shot_ids if isinstance(raw_shot_ids, list) else []
        else:
            expected_shot_ids = context.index["segment_shots"].get(segment_id, []) if isinstance(segment_id, str) else []
        h3_mode = str(segment.get("h3_mode") or "").strip()
        if h3_mode not in H3_MODES:
            context.report("h3_mode_invalid", f"{segment_id or 'segment'} 必须登记有效 h3_mode：T2VA/I2VA/FL2VA/L2VA/Ref2VA。")
        elif context.tool_mode in H3_TOOL_MODE_MAPPING and h3_mode not in H3_TOOL_MODE_MAPPING[context.tool_mode]:
            allowed = sorted(H3_TOOL_MODE_MAPPING[context.tool_mode])
            context.report("h3_mode_tool_mismatch", f"{segment_id or 'segment'} h3_mode={h3_mode} 与 tool_mode={context.tool_mode} 不兼容，允许值：{allowed}。")
        check_h3_media_inputs(segment, path, issues)
        draft_path = relative_file(context.root, segment.get("director_draft_file"))
        check_prompt_preflight(segment, expected_shot_ids, path, issues)
        if draft_path is None:
            context.report("director_draft_missing", f"{segment_id or 'segment'} 必须登记项目相对路径 director_draft_file（中文五段式导演编译底稿）。")
        else:
            check_director_draft_prompt(
                draft_path,
                context.image_orders,
                context.video_orders,
                context.audio_orders,
                segment.get("speech_lines"),
                segment.get("subtitle_enabled") is True,
                issues,
            )
        if prompt_path is not None:
            check_h3_final_prompt(
                prompt_path,
                h3_mode,
                context.image_orders,
                context.video_orders,
                context.audio_orders,
                segment.get("speech_lines"),
                segment.get("subtitle_enabled") is True,
                issues,
            )
            prompt_sha256 = str(segment.get("prompt_sha256") or "").strip()
            if prompt_sha256:
                try:
                    actual_sha256 = file_sha256(prompt_path)
                except OSError as exc:
                    issues.append(issue("error", "prompt_sha256_unreadable", f"无法读取 Prompt 计算 sha256：{exc}", prompt_path))
                else:
                    if actual_sha256 != prompt_sha256:
                        issues.append(issue("error", "prompt_sha256_mismatch", f"{segment_id} prompt_sha256 与实际 Prompt 文件不一致。", prompt_path))
        elif prompt_file:
            context.report("prompt_path_invalid", "compiled_prompt_file 必须是项目相对路径。")
        generated_segment = bool(str(segment.get("output_file") or "").strip()) or segment.get("status") in {"candidate", "accepted"}
        if prompt_file or generated_segment or segment.get("generation_confirmation_id"):
            check_h3_skill_conversion(context.root, segment, draft_path, prompt_path, path, issues)
        if generated_segment and (prompt_path is None or not prompt_path.is_file()):
            context.report("generated_segment_prompt_missing", f"{segment_id} 已生成或进入候选/验收状态，必须登记真实存在的 compiled_prompt_file。")
        if generated_segment and not str(segment.get("prompt_sha256") or "").strip():
            context.report("generated_segment_prompt_sha256_missing", f"{segment_id} 已生成或进入候选/验收状态，必须登记实际提交 Prompt 文件的 prompt_sha256。")
        self.check_status(prompt_path, generated_segment)

    def check_status(self, prompt_path: Path | None, generated_segment: bool) -> None:
        context = self.context
        segment = context.segment
        segment_id = context.segment_id
        status = segment.get("status")
        if status not in {None, *VIDEO_STATUS_VALUES}:
            context.report("video_status_invalid", f"视频片段状态无效：{status}")
        elif context.require_accepted and status != VideoStatus.ACCEPTED.value:
            context.report("video_segment_not_accepted", f"{segment_id or '视频片段'} 必须在进入成片阶段前登记 status=accepted。")
        elif not context.require_accepted and generated_segment and status not in {"candidate", "accepted"}:
            context.report("video_segment_not_ready_for_confirmation", f"{segment_id or '视频片段'} 在发起拼接确认前必须登记 status=candidate 或 accepted。")
        if status == VideoStatus.CANDIDATE.value and not file_exists(context.root, segment.get("output_file")):
            context.report("video_segment_output_missing", f"{segment_id} 已进入候选状态，但 output_file 不存在。")
        if status == VideoStatus.ACCEPTED.value:
            if not file_exists(context.root, segment.get("output_file")):
                context.report("accepted_segment_output_missing", f"{segment_id} 已 accepted，但 output_file 不存在。")
            if prompt_path is None or not prompt_path.is_file():
                context.report("accepted_segment_prompt_missing", f"{segment_id} 已 accepted，但 compiled_prompt_file 不存在。")


def check_video_duration_declaration(
    data: dict[str, Any],
    segments: list[Any],
    path: Path,
    issues: list[dict[str, Any]],
) -> None:
    declared_duration = data.get("duration_s")
    valid_segment_durations = [
        float(segment["duration_s"])
        for segment in segments
        if isinstance(segment, dict)
        and isinstance(segment.get("duration_s"), (int, float))
        and not isinstance(segment.get("duration_s"), bool)
        and math.isfinite(float(segment["duration_s"]))
    ]
    if not isinstance(declared_duration, (int, float)) or isinstance(declared_duration, bool) or not math.isfinite(float(declared_duration)) or float(declared_duration) <= 0:
        issues.append(issue("error", "video_duration_invalid", "video_manifest.duration_s 必须是有限正数。", path))
    elif valid_segment_durations and abs(float(declared_duration) - sum(valid_segment_durations)) > 1e-6:
        issues.append(issue("error", "video_duration_mismatch", "video_manifest.duration_s 必须用原始数值精确等于 segments.duration_s 之和，不能四舍五入闭合。", path))


class VideoChecker:
    def __init__(
        self,
        root: Path,
        asset_index: dict[str, Any],
        plan: Any,
        issues: list[dict[str, Any]],
        episode_filter: str | None,
        require_accepted: bool,
    ) -> None:
        self.root = root
        self.asset_index = asset_index
        self.plan = plan
        self.issues = issues
        self.episode_filter = episode_filter
        self.require_accepted = require_accepted
        self.lightweight = is_lightweight_plan(plan) and lightweight_constraints_valid(plan)
        self.seen_voice_anchors: dict[str, str] = {}

    def run(self) -> None:
        for episode_id, episode_root in episode_dirs(self.root, self.episode_filter):
            self.check_episode(episode_id, episode_root)

    def check_episode(self, episode_id: str, episode_root: Path) -> None:
        path = episode_root / f"04_视频片段/video_manifest_{episode_id}.json"
        data = load_json(path, self.issues, required=False)
        if not isinstance(data, dict):
            return
        if data.get("episode_id") != episode_id:
            self.issues.append(issue("error", "episode_id_mismatch", "video_manifest episode_id 与目录不一致。", path))
        check_declared_video_models(data, path, "video_manifest", self.issues)
        index = load_storyboard_index(self.root, episode_id, self.issues)
        keyframe_ids = load_keyframe_ids(self.root, episode_id, self.issues)
        segments = data.get("segments")
        if not isinstance(segments, list):
            self.issues.append(issue("error", "video_segments_invalid", "video_manifest.segments 必须是数组。", path))
            return
        if self.lightweight and len(segments) != 1:
            self.issues.append(issue("error", "lightweight_video_count_invalid", "轻量模式必须只生成一个最终视频；多个独立视频必须拆为独立任务。", path))
        check_video_generation_confirmations(data, segments, path, self.issues, self.lightweight)
        if self.lightweight and isinstance(data.get("generation_confirmations"), list) and data["generation_confirmations"]:
            planning_records = [
                record
                for record in load_confirmation_records(self.root, self.issues, required=True)
                if record.get("stage") == "planning"
                and record.get("confirmation_purpose") == "video_generation"
                and record.get("interaction_ask_result") == "generate"
            ]
            latest_planning = max(planning_records, key=lambda record: record.get("revision", 0), default={})
            first_generation = data["generation_confirmations"][0]
            if not isinstance(first_generation, dict) or first_generation.get("interaction_ask_call_id") != latest_planning.get("interaction_ask_call_id"):
                self.issues.append(issue("error", "lightweight_confirmation_call_mismatch", "轻量模式 planning 与首次视频生成记录必须复用同一个 interaction.ask 调用 ID。", path))
        video_segment_ids = check_unique(segments, "segment_id", path, self.issues, "video segments")
        if index["segments"]:
            missing_segments = sorted(index["segments"] - video_segment_ids)
            extra_segments = sorted(video_segment_ids - index["segments"])
            if missing_segments:
                level = "error" if self.require_accepted else "warning"
                self.issues.append(issue(level, "video_segment_missing", f"video_manifest 尚未覆盖 storyboard segment：{missing_segments}；视频阶段允许逐段建立真实执行记录，进入成片前必须补齐。", path))
            if extra_segments:
                self.issues.append(issue("error", "video_segment_unplanned", f"video_manifest 含 storyboard 中不存在的 segment：{extra_segments}", path))
        check_video_duration_declaration(data, segments, path, self.issues)
        self.seen_voice_anchors = {}
        for segment in segments:
            if not isinstance(segment, dict):
                self.issues.append(issue("error", "video_segment_invalid", "segments 每项必须是对象。", path))
                continue
            self.check_segment(segment, data, index, keyframe_ids, path)

    def check_segment(
        self,
        segment: dict[str, Any],
        data: dict[str, Any],
        index: dict[str, Any],
        keyframe_ids: set[str],
        path: Path,
    ) -> None:
        segment_id = segment.get("segment_id")
        if isinstance(segment_id, str) and index["segments"] and segment_id not in index["segments"]:
            self.issues.append(issue("error", "video_unknown_segment", f"视频引用了分镜中不存在的 segment_id：{segment_id}", path))
        storyboard_duration = index["segment_durations"].get(segment_id)
        if storyboard_duration is not None and isinstance(segment.get("duration_s"), (int, float)) and not isinstance(segment.get("duration_s"), bool) and math.isfinite(float(segment["duration_s"])) and math.isfinite(float(storyboard_duration)):
            if abs(float(segment["duration_s"]) - float(storyboard_duration)) > 1e-6:
                self.issues.append(issue("error", "video_segment_duration_mismatch", f"{segment_id} 时长必须与分镜片段时长按原始数值精确一致。", path))
        image_orders, image_roles = ordered_inputs(self.root, video_reference_inputs(segment, path, self.issues), REFERENCE_ROLES, "reference", path, self.issues)
        video_orders, video_roles = ordered_inputs(self.root, segment.get("video_inputs"), VIDEO_INPUT_ROLES, "video", path, self.issues)
        audio_orders, audio_roles = ordered_inputs(self.root, segment.get("audio_inputs"), AUDIO_INPUT_ROLES, "audio", path, self.issues)
        model_name = video_model_name(self.plan, data, segment)
        check_video_model(model_name, path, str(segment_id or "segment"), self.issues)
        check_declared_video_models(segment, path, str(segment_id or "segment"), self.issues)
        check_h3_duration(segment.get("duration_s"), path, str(segment_id or "segment"), self.issues)
        context = VideoSegmentContext(
            root=self.root,
            plan=self.plan,
            data=data,
            index=index,
            keyframe_ids=keyframe_ids,
            asset_index=self.asset_index,
            lightweight=self.lightweight,
            path=path,
            issues=self.issues,
            segment=segment,
            image_orders=image_orders,
            image_roles=image_roles,
            video_orders=video_orders,
            video_roles=video_roles,
            audio_orders=audio_orders,
            audio_roles=audio_roles,
            require_accepted=self.require_accepted,
        )
        tool_mode = segment.get("tool_mode")
        strategy = VIDEO_ROUTE_STRATEGIES.get(tool_mode)
        if strategy is None:
            self.issues.append(issue("error", "video_tool_mode_invalid", f"{segment_id or 'segment'} tool_mode 无效：{tool_mode}", path))
        else:
            check_voice_anchor_consistency(segment, self.seen_voice_anchors, path, self.issues)
            strategy.validate(context)
        self.check_reference_sources(context)
        SegmentPromptPipeline(context).run()

    def check_reference_sources(self, context: VideoSegmentContext) -> None:
        segment = context.segment
        segment_id = context.segment_id
        for input_item in segment.get("reference_inputs") or []:
            if not isinstance(input_item, dict):
                continue
            source_type = input_item.get("source_type")
            source_id = input_item.get("source_id")
            role = input_item.get("role")
            if role in {"previous_tail_as_start_frame", "previous_tail_reference"} and source_type != "frame":
                context.report("previous_tail_source_type_invalid", f"{segment_id} 上一段尾帧必须以 source_type=frame 真实传入。")
            if source_type == "asset":
                base_asset_state_reference = role in STATE_REFERENCE_ROLES and isinstance(source_id, str) and source_id in context.asset_index["known_version_refs"]
                if (role in STATE_REFERENCE_ROLES and not base_asset_state_reference) or (role == "crowd_reference" and isinstance(source_id, str) and source_id in context.asset_index["known_state_refs"]):
                    check_state_ref(source_id, context.asset_index, context.path, context.issues, f"{segment_id or '视频片段'} reference_inputs")
                else:
                    check_asset_ref(source_id, context.asset_index, context.path, context.issues, f"{segment_id or '视频片段'} reference_inputs")
            if source_type == "keyframe" and isinstance(source_id, str) and context.keyframe_ids and source_id not in context.keyframe_ids:
                context.report("video_reference_unknown_keyframe", f"{segment_id} 引用了不存在的关键帧：{source_id}")


def check_video(
    root: Path,
    asset_index: dict[str, Any],
    plan: Any,
    issues: list[dict[str, Any]],
    episode_filter: str | None = None,
    require_accepted: bool = True,
) -> None:
    VideoChecker(root, asset_index, plan, issues, episode_filter, require_accepted).run()
