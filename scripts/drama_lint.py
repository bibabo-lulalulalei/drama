from __future__ import annotations

import argparse
import ast
import io
import json
import math
import re
import sys
import tokenize
from pathlib import Path
from typing import Any
from urllib.parse import unquote

if __package__:
    from .drama_lint_confirmations import (
        CONFIRMATION_MODES,
        CONFIRMATION_TRANSPORTS,
        check_confirmation_transport,
        has_confirmation,
        load_confirmation_records,
    )
    from .drama_lint_assets import (
        ASSET_PREFIX_BY_CATEGORY,
        ASSET_STATUS_VALUES,
        IMAGE_GENERATION_TOOLS,
        PROJECT_VISUAL_MODES,
        VISUAL_REFERENCE_DECISIONS,
        asset_version_key,
        blank_asset_index,
        check_asset_ref,
        check_assets,
        check_generation_prompt_file,
        check_stale_asset_version,
        check_state_ref,
        check_style_anchor_contract,
        remember_asset_files,
        remember_asset_version,
        remember_state_version,
        split_asset_version_ref,
        state_ref_keys,
        version_rank,
    )
    from .drama_lint_domain import (
        CURRENT_STAGE_ACTIVE_VALUES,
        EPISODE_STAGES,
        AUDIO_INPUT_ROLES,
        FRAME_REFERENCE_POSITIONS,
        H3_CAPABILITIES,
        IMAGE_INPUT_SUFFIXES,
        REFERENCE_ROLES,
        STATE_REFERENCE_ROLES,
        VIDEO_INPUT_ROLES,
        H3_MODEL,
        H3_MODES,
        H3_PROFILE,
        ISO_TIME_PATTERN,
        MERGEABLE_LIGHTWEIGHT_STAGES,
        SPEECH_IGNORED_PUNCTUATION,
        STAGES,
        STATUS_VALUES,
        check_declared_video_models,
        check_h3_duration,
        check_unique,
        check_video_model,
        combined_strings,
        episode_dirs,
        file_exists,
        file_sha256,
        has_meaningful_value,
        h3_duration_valid,
        is_lightweight_plan,
        issue,
        lightweight_constraints_valid,
        load_json,
        markdown_table_column_counts,
        marker_pattern,
        nonempty_strings,
        normalized_speech,
        parse_iso_time,
        plan_revision,
        relative_file,
        target_stage,
    )
    from .drama_lint_state import check_state
    from .drama_lint_storyboards import (
        EPISODE_KEYFRAME_MAX,
        EPISODE_KEYFRAME_MIN,
        SEGMENT_KEYFRAME_MAX,
        check_episode_keyframe_request_plan,
        check_keyframe_request_plan,
        check_reference_plan,
        check_segment_shot_count,
        check_storyboards,
        load_storyboard_index,
        video_model_name,
    )
    from .drama_lint_prompts import (
        CN_MEDIA_MARKER_PATTERN,
        H3_BASE_FIELDS,
        H3_MARKER_PATTERNS,
        H3_REF2VA_FIELDS,
        _check_draft_slot_markers,
        _read_prompt_text,
        check_director_draft_prompt,
        check_h3_final_prompt,
        check_h3_skill_conversion,
        check_prompt_preflight,
        extract_h3_marker_orders,
        extract_marker_orders,
        extract_subject_marker_orders,
    )
    from .drama_lint_video import (
        H3_TOOL_MODE_MAPPING,
        VIDEO_STATUS_VALUES,
        VIDEO_TOOL_MODES,
        check_h3_media_inputs,
        check_video,
        check_video_state_refs,
        check_voice_anchor_consistency,
        check_voice_audio_inputs,
        load_keyframe_ids,
        media_duration_s,
        ordered_inputs,
    )
    from .drama_lint_video_confirmations import check_video_generation_confirmations, generated_segment_indexes
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from drama_lint_confirmations import (
        CONFIRMATION_MODES,
        CONFIRMATION_TRANSPORTS,
        check_confirmation_transport,
        has_confirmation,
        load_confirmation_records,
    )
    from drama_lint_assets import (
        ASSET_PREFIX_BY_CATEGORY,
        ASSET_STATUS_VALUES,
        IMAGE_GENERATION_TOOLS,
        PROJECT_VISUAL_MODES,
        VISUAL_REFERENCE_DECISIONS,
        asset_version_key,
        blank_asset_index,
        check_asset_ref,
        check_assets,
        check_generation_prompt_file,
        check_stale_asset_version,
        check_state_ref,
        check_style_anchor_contract,
        remember_asset_files,
        remember_asset_version,
        remember_state_version,
        split_asset_version_ref,
        state_ref_keys,
        version_rank,
    )
    from drama_lint_domain import (
        CURRENT_STAGE_ACTIVE_VALUES,
        EPISODE_STAGES,
        AUDIO_INPUT_ROLES,
        FRAME_REFERENCE_POSITIONS,
        H3_CAPABILITIES,
        IMAGE_INPUT_SUFFIXES,
        REFERENCE_ROLES,
        STATE_REFERENCE_ROLES,
        VIDEO_INPUT_ROLES,
        H3_MODEL,
        H3_MODES,
        H3_PROFILE,
        ISO_TIME_PATTERN,
        MERGEABLE_LIGHTWEIGHT_STAGES,
        SPEECH_IGNORED_PUNCTUATION,
        STAGES,
        STATUS_VALUES,
        check_declared_video_models,
        check_h3_duration,
        check_unique,
        check_video_model,
        combined_strings,
        episode_dirs,
        file_exists,
        file_sha256,
        has_meaningful_value,
        h3_duration_valid,
        is_lightweight_plan,
        issue,
        lightweight_constraints_valid,
        load_json,
        markdown_table_column_counts,
        marker_pattern,
        nonempty_strings,
        normalized_speech,
        parse_iso_time,
        plan_revision,
        relative_file,
        target_stage,
    )
    from drama_lint_state import check_state
    from drama_lint_storyboards import (
        EPISODE_KEYFRAME_MAX,
        EPISODE_KEYFRAME_MIN,
        SEGMENT_KEYFRAME_MAX,
        check_episode_keyframe_request_plan,
        check_keyframe_request_plan,
        check_reference_plan,
        check_segment_shot_count,
        check_storyboards,
        load_storyboard_index,
        video_model_name,
    )
    from drama_lint_prompts import (
        CN_MEDIA_MARKER_PATTERN,
        H3_BASE_FIELDS,
        H3_MARKER_PATTERNS,
        H3_REF2VA_FIELDS,
        _check_draft_slot_markers,
        _read_prompt_text,
        check_director_draft_prompt,
        check_h3_final_prompt,
        check_h3_skill_conversion,
        check_prompt_preflight,
        extract_h3_marker_orders,
        extract_marker_orders,
        extract_subject_marker_orders,
    )
    from drama_lint_video import (
        H3_TOOL_MODE_MAPPING,
        VIDEO_STATUS_VALUES,
        VIDEO_TOOL_MODES,
        check_h3_media_inputs,
        check_video,
        check_video_state_refs,
        check_voice_anchor_consistency,
        check_voice_audio_inputs,
        load_keyframe_ids,
        media_duration_s,
        ordered_inputs,
    )
    from drama_lint_video_confirmations import check_video_generation_confirmations, generated_segment_indexes


FORBIDDEN_TOOL_TERMS = ("ffmpeg", "text_to_image")

CROWD_APPEARANCE_FIELDS = ("age_range", "build", "hair", "wardrobe", "palette", "distinctive_features")


def file_inside(root: Path, value: Any, directory: Path) -> bool:
    target = relative_file(root, value)
    if target is None or not target.is_file():
        return False
    try:
        target.relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def expected_duration_display(seconds: int | float) -> str:
    total = int(round(float(seconds)))
    if total <= 60:
        return f"{total}秒"
    minutes, rest = divmod(total, 60)
    return f"{minutes}分钟" if rest == 0 else f"{minutes}分{rest}秒"


def expected_total_duration_display(seconds: int | float) -> str:
    total = int(round(float(seconds)))
    natural = expected_duration_display(total)
    return natural if total <= 60 else f"{total}秒/{natural}"


def check_duration_pair(
    seconds: Any,
    display: Any,
    path: Path,
    label: str,
    issues: list[dict[str, Any]],
    *,
    total_display: bool = False,
) -> None:
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        issues.append(issue("error", "duration_invalid", f"{label} duration_s 必须是数字。", path))
        return
    if isinstance(display, str) and display.strip():
        expected = expected_total_duration_display(seconds) if total_display else expected_duration_display(seconds)
        if display != expected:
            issues.append(issue("error", "duration_display_invalid", f"{label} duration_display 应为 {expected}。", path))


def manifest_path(root: Path, episode_id: str, stage: str) -> Path | None:
    episode_root = root / "episodes" / episode_id
    paths = {
        "script": episode_root / f"01_剧本/script_contract_{episode_id}.json",
        "assets": episode_root / f"03_资产/asset_usage_{episode_id}.json",
        "storyboard": episode_root / f"02_分镜/storyboard_{episode_id}.json",
        "keyframes": episode_root / f"03_资产/keyframe_manifest_{episode_id}.json",
        "video": episode_root / f"04_视频片段/video_manifest_{episode_id}.json",
        "final": episode_root / f"05_成片/delivery_manifest_{episode_id}.json",
    }
    return paths.get(stage)


def check_episode_directories(root: Path, expected_episodes: dict[str, int | None], issues: list[dict[str, Any]]) -> None:
    if not expected_episodes:
        return
    expected = set(expected_episodes)
    actual = {episode_id for episode_id, _ in episode_dirs(root)}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    episodes_root = root / "episodes"
    if missing:
        issues.append(issue("error", "episode_directory_missing", f"计划内分集缺少目录：{missing}", episodes_root))
    if extra:
        issues.append(issue("error", "episode_directory_unplanned", f"存在计划外分集目录：{extra}", episodes_root))


def check_episode_manifest_ids(root: Path, stage: str, issues: list[dict[str, Any]], episode_filter: str | None = None) -> None:
    for episode_id, _ in episode_dirs(root, episode_filter):
        path = manifest_path(root, episode_id, stage)
        if path is None or not path.exists():
            continue
        data = load_json(path, issues, required=False)
        if isinstance(data, dict) and data.get("episode_id") != episode_id:
            issues.append(issue("error", "episode_id_mismatch", f"{stage} episode_id 必须等于目录 ID：{episode_id}", path))


def check_episode_entry_manifests(root: Path, issues: list[dict[str, Any]], lightweight: bool = False) -> None:
    for episode_id, episode_root in episode_dirs(root):
        path = episode_root / f"episode_manifest_{episode_id}.json"
        data = load_json(path, issues, required=True)
        if not isinstance(data, dict):
            continue
        if data.get("episode_id") != episode_id:
            issues.append(issue("error", "episode_id_mismatch", f"episode_manifest episode_id 必须等于目录 ID：{episode_id}", path))
        stage_manifests = data.get("stage_manifests")
        if not isinstance(stage_manifests, dict):
            issues.append(issue("error", "stage_manifests_missing", "episode_manifest 必须使用顶层 stage_manifests。", path))
            continue
        if lightweight:
            expected = {
                "script": "",
                "storyboard": f"episodes/{episode_id}/02_分镜/分镜_完整分镜表_{episode_id}.md",
                "assets": "",
                "keyframes": "",
                "video": f"episodes/{episode_id}/04_视频片段/video_manifest_{episode_id}.json",
                "continuity": "",
                "delivery": f"episodes/{episode_id}/05_成片/delivery_manifest_{episode_id}.json",
            }
        else:
            expected = {
                "script": f"episodes/{episode_id}/01_剧本/script_contract_{episode_id}.json",
                "storyboard": f"episodes/{episode_id}/02_分镜/storyboard_{episode_id}.json",
                "assets": f"episodes/{episode_id}/03_资产/asset_usage_{episode_id}.json",
                "keyframes": f"episodes/{episode_id}/03_资产/keyframe_manifest_{episode_id}.json",
                "video": f"episodes/{episode_id}/04_视频片段/video_manifest_{episode_id}.json",
                "continuity": f"episodes/{episode_id}/04_视频片段/continuity_{episode_id}.json",
                "delivery": f"episodes/{episode_id}/05_成片/delivery_manifest_{episode_id}.json",
            }
        for stage, expected_path in expected.items():
            if stage_manifests.get(stage) != expected_path:
                issues.append(issue("error", "stage_manifest_path_invalid", f"episode_manifest.stage_manifests.{stage} 必须指向 {expected_path}。", path))




def check_operation_log_tools(root: Path, issues: list[dict[str, Any]]) -> None:
    path = root / "00_制作控制/操作日志.jsonl"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except (OSError, UnicodeError) as exc:
        issues.append(issue("error", "operation_log_unreadable", f"操作日志无法读取：{exc}", path))
        return
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        tool_name = str(data.get("tool") or "").strip().lower()
        if tool_name in FORBIDDEN_TOOL_TERMS:
            issues.append(issue("error", "forbidden_media_tool_used", f"操作日志第 {line_number} 行登记了禁用工具 {tool_name}；媒体处理必须使用 mediakit。", path))


def check_stage_artifacts(
    root: Path,
    stage: str,
    issues: list[dict[str, Any]],
    episode_filter: str | None = None,
    lightweight: bool = False,
) -> None:
    required = [root / "00_制作控制/drama_plan.json", root / "00_制作控制/制作状态.json"]
    state = load_json(root / "00_制作控制/制作状态.json", issues, required=False)
    script_status = state.get("phases", {}).get("script") if isinstance(state, dict) and isinstance(state.get("phases"), dict) else None
    script_should_exist = not lightweight or script_status == "confirmed"
    episode_states = state.get("episodes", {}) if isinstance(state, dict) and isinstance(state.get("episodes"), dict) else {}
    if stage == "planning":
        required += [
            root / "00_制作控制/project_manifest.json",
            root / "00_制作控制/source_manifest.json",
            root / "episodes",
        ]
    if stage == "script" and script_should_exist:
        required += [
            root / "00_制作控制/project_data_card.json",
            root / "01_剧本/project_script_manifest.json",
            root / "01_剧本/项目_事实与假设.md",
            root / "01_剧本/项目设定卡.md",
            root / "01_剧本/剧本_全局设定与分集总纲.md",
            root / "01_剧本/剧本_全剧完整剧本.md",
        ]
    if stage in {"assets", "storyboard", "keyframes", "video", "final"} and not lightweight:
        required.append(root / "00_制作控制/project_data_card.json")
    for episode_id, episode_root in episode_dirs(root):
        if episode_filter is not None and episode_id != episode_filter:
            continue
        if stage == "planning":
            required.append(episode_root / f"episode_manifest_{episode_id}.json")
        episode_script_status = (
            episode_states.get(episode_id, {}).get("stage_status", {}).get("script")
            if isinstance(episode_states.get(episode_id), dict)
            and isinstance(episode_states.get(episode_id, {}).get("stage_status"), dict)
            else None
        )
        require_episode_script = (
            not lightweight
            and (
                stage in {"assets", "storyboard", "keyframes", "video", "final"}
                or (
                    stage == "script"
                    and (
                        episode_filter == episode_id
                        or episode_script_status in {"in_progress", "awaiting_confirmation", "confirmed", "blocked"}
                    )
                )
            )
        )
        if require_episode_script:
            required += [
                episode_root / f"01_剧本/script_contract_{episode_id}.json",
                episode_root / f"01_剧本/剧本_分集梗概_{episode_id}.md",
                episode_root / f"01_剧本/剧本_分集人物状态_{episode_id}.md",
                episode_root / f"01_剧本/剧本_人物关系张力矩阵_{episode_id}.md",
                episode_root / f"01_剧本/剧本_分集主要场景_{episode_id}.md",
                episode_root / f"01_剧本/剧本_完整剧本_{episode_id}.md",
            ]
        if stage in {"assets", "storyboard", "keyframes", "video", "final"} and not lightweight:
            required += [root / "shared/03_资产/asset_registry.json", episode_root / f"03_资产/asset_usage_{episode_id}.json"]
        if stage in {"storyboard", "keyframes", "video", "final"} and lightweight:
            required.append(episode_root / f"02_分镜/分镜_完整分镜表_{episode_id}.md")
        elif stage in {"storyboard", "keyframes", "video", "final"}:
            required += [
                episode_root / f"02_分镜/storyboard_{episode_id}.json",
                episode_root / f"02_分镜/分镜_阅读稿_{episode_id}.md",
                episode_root / f"02_分镜/导演总控卡_{episode_id}.md",
                episode_root / f"02_分镜/分镜_完整分镜表_{episode_id}.md",
            ]
        if stage in {"keyframes", "video", "final"} and not lightweight:
            required += [episode_root / f"03_资产/keyframe_manifest_{episode_id}.json"]
        if stage in {"video", "final"}:
            required += [episode_root / f"04_视频片段/video_manifest_{episode_id}.json"]
        if stage == "final":
            required += [episode_root / f"05_成片/delivery_manifest_{episode_id}.json"]
    for path in required:
        if not path.exists():
            issues.append(issue("error", "required_artifact_missing", "缺少当前阶段所需产物。", path))
    if lightweight and stage in {"storyboard", "keyframes", "video", "final"}:
        for episode_id, episode_root in episode_dirs(root, episode_filter):
            storyboard_path = episode_root / f"02_分镜/分镜_完整分镜表_{episode_id}.md"
            if not storyboard_path.is_file():
                continue
            try:
                storyboard_text = storyboard_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                issues.append(issue("error", "storyboard_source_markdown_unreadable", f"十五列完整分镜表无法读取：{exc}", storyboard_path))
            else:
                if 15 not in markdown_table_column_counts(storyboard_text):
                    issues.append(issue("error", "storyboard_fifteen_columns_missing", "完整分镜表必须包含一个十五列表格。", storyboard_path))
    if stage == "script" and script_should_exist:
        combined_path = root / "01_剧本/剧本_全局设定与分集总纲.md"
        if combined_path.is_file():
            try:
                combined_text = combined_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                issues.append(issue("error", "combined_story_outline_unreadable", f"合并剧本文档无法读取：{exc}", combined_path))
            else:
                for heading in ("全局故事圣经", "分集推进总纲"):
                    if re.search(rf"^#{{1,6}}\s+{re.escape(heading)}\s*$", combined_text, flags=re.MULTILINE) is None:
                        issues.append(issue("error", "combined_story_outline_section_missing", f"合并剧本文档缺少“{heading}”章节。", combined_path))
        script_manifest_path = root / "01_剧本/project_script_manifest.json"
        script_manifest = load_json(script_manifest_path, issues, required=False)
        if isinstance(script_manifest, dict):
            expected = "01_剧本/剧本_全局设定与分集总纲.md"
            if script_manifest.get("global_story_and_episode_outline") != expected:
                issues.append(issue("error", "combined_story_outline_reference_invalid", f"project_script_manifest.global_story_and_episode_outline 必须指向 {expected}。", script_manifest_path))
        if not lightweight:
            for episode_id, episode_root in episode_dirs(root, episode_filter):
                episode_script_status = (
                    episode_states.get(episode_id, {}).get("stage_status", {}).get("script")
                    if isinstance(episode_states.get(episode_id), dict)
                    and isinstance(episode_states.get(episode_id, {}).get("stage_status"), dict)
                    else None
                )
                if stage == "script" and episode_filter is None and episode_script_status not in {"in_progress", "awaiting_confirmation", "confirmed", "blocked"}:
                    continue
                contract_path = episode_root / f"01_剧本/script_contract_{episode_id}.json"
                contract = load_json(contract_path, issues, required=False)
                if not isinstance(contract, dict):
                    continue
                highlight_ledger = contract.get("highlight_ledger")
                if not isinstance(highlight_ledger, list):
                    issues.append(issue("error", "highlight_ledger_invalid", "完整模式 script_contract.highlight_ledger 必须是数组。", contract_path))
                    continue
                primary_entries = [
                    item
                    for item in highlight_ledger
                    if isinstance(item, dict) and item.get("role") == "primary" and str(item.get("highlight_id") or "").strip()
                ]
                if not primary_entries:
                    issues.append(issue("error", "primary_highlight_missing", "完整模式每集 script_contract.highlight_ledger 必须至少包含一个有效的 primary 亮点。", contract_path))


def check_plan_durations(root: Path, plan: Any, issues: list[dict[str, Any]]) -> dict[str, int | None]:
    expected: dict[str, int | None] = {}
    if not isinstance(plan, dict):
        return expected
    path = root / "00_制作控制/drama_plan.json"
    model_plan = plan.get("model_plan")
    video_plan = model_plan.get("video") if isinstance(model_plan, dict) else None
    check_video_model(video_model_name(plan, {}, {}), path, "drama_plan.model_plan.video", issues)
    check_declared_video_models(video_plan, path, "drama_plan.model_plan.video", issues)
    if not isinstance(plan.get("revision"), int) or isinstance(plan.get("revision"), bool) or plan.get("revision") < 1:
        issues.append(issue("error", "plan_revision_invalid", "drama_plan.revision 必须是正整数。", path))
    objective = plan.get("objective")
    if not isinstance(objective, dict) or objective.get("target_stage") not in STAGES:
        issues.append(issue("error", "target_stage_invalid", "drama_plan.objective.target_stage 必须是有效阶段。", path))
    if not str(plan.get("selected_direction_id") or "").strip():
        issues.append(issue("error", "selected_direction_missing", "drama_plan 必须锁定 selected_direction_id。", path))
    creative_mechanism = plan.get("creative_mechanism")
    if not isinstance(creative_mechanism, dict):
        issues.append(issue("error", "creative_mechanism_missing", "drama_plan 必须填写 creative_mechanism。", path))
    else:
        selection_mode = creative_mechanism.get("selection_mode")
        if selection_mode not in {"divergent", "user_locked"}:
            issues.append(issue("error", "creative_mechanism_selection_mode_invalid", "creative_mechanism.selection_mode 必须为 divergent 或 user_locked。", path))
        candidates = creative_mechanism.get("candidates")
        candidate_primaries: list[str] = []
        expected_counts = {3} if selection_mode == "divergent" else {1, 2, 3}
        if not isinstance(candidates, list) or len(candidates) not in expected_counts:
            expected_text = "恰好 3 个" if selection_mode == "divergent" else "1-3 个"
            issues.append(issue("error", "creative_mechanism_candidates_invalid", f"当前 selection_mode 的 creative_mechanism.candidates 必须包含{expected_text}候选。", path))
        else:
            for index, candidate in enumerate(candidates, start=1):
                supporting = candidate.get("supporting") if isinstance(candidate, dict) else None
                if not isinstance(candidate, dict) or not has_meaningful_value(candidate.get("primary")):
                    issues.append(issue("error", "creative_mechanism_primary_missing", f"创意机制候选 {index} 必须填写主机制。", path))
                else:
                    candidate_primaries.append(str(candidate["primary"]).strip())
                if not isinstance(supporting, list) or not 1 <= len(supporting) <= 3:
                    issues.append(issue("error", "creative_mechanism_supporting_invalid", f"创意机制候选 {index} 必须包含 1-3 个同源辅助机制。", path))
        selected_primary = str(creative_mechanism.get("primary") or "").strip()
        if not selected_primary:
            issues.append(issue("error", "creative_mechanism_selected_missing", "creative_mechanism.primary 必须锁定唯一主机制。", path))
        elif candidate_primaries and selected_primary not in candidate_primaries:
            issues.append(issue("error", "creative_mechanism_selected_unknown", "creative_mechanism.primary 必须来自当前候选主机制之一。", path))
        selected_supporting = creative_mechanism.get("supporting")
        if not isinstance(selected_supporting, list) or not 1 <= len(selected_supporting) <= 3:
            issues.append(issue("error", "creative_mechanism_selected_supporting_invalid", "creative_mechanism.supporting 必须保留 1-3 个辅助机制。", path))
    rhythm_design = plan.get("rhythm_design")
    rhythm_fields = ("immutable_nodes", "node_loads", "primary_downbeat", "transition_choices", "duration_allocation", "intensity_sequence", "selected_wave")
    if not isinstance(rhythm_design, dict):
        issues.append(issue("error", "rhythm_design_missing", "drama_plan 必须填写六步推导后的 rhythm_design。", path))
    else:
        for field in rhythm_fields:
            if not has_meaningful_value(rhythm_design.get(field)):
                issues.append(issue("error", "rhythm_design_field_missing", f"rhythm_design.{field} 必须填写。", path))
        intensity = rhythm_design.get("intensity_sequence")
        if isinstance(intensity, list) and any(not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5 for value in intensity):
            issues.append(issue("error", "rhythm_intensity_invalid", "rhythm_design.intensity_sequence 只能包含 1-5 的整数。", path))
    strategy_contracts = {
        "audience_plan": (
            "target_audience",
            "core_pain_or_desire",
            "platform",
            "evidence_status",
            "viewing_focus",
            "emotional_payoff",
            "platform_viewing_context",
            "expression_boundaries",
        ),
        "type_strategy": ("format", "subject_route", "genre", "story_engine", "audience_promise", "narrative_structure", "main_path"),
        "highlight_strategy": ("primary_story_engine_id", "project_signature", "highlight_pillars", "distribution_policy", "rejected_cliches"),
        "style_contract": ("anchor_type", "anchor", "lighting", "color", "composition", "material", "camera_tendency", "sound_tendency", "excluded_mechanisms"),
    }
    for contract_name, required_fields in strategy_contracts.items():
        contract = plan.get(contract_name)
        if not isinstance(contract, dict):
            issues.append(issue("error", f"{contract_name}_missing", f"drama_plan 缺少 {contract_name}。", path))
            continue
        for field in required_fields:
            if not has_meaningful_value(contract.get(field)):
                issues.append(issue("error", f"{contract_name}_field_missing", f"{contract_name}.{field} 必须填写。", path))
        if contract_name == "audience_plan" and isinstance(contract, dict):
            source_values = contract.get("execution_sources")
            expected_sources = {
                "viewing_focus": "audience_plan.viewing_focus",
                "emotional_payoff": "audience_plan.emotional_payoff",
                "platform_viewing_context": "audience_plan.platform_viewing_context",
                "expression_boundaries": "audience_plan.expression_boundaries",
            }
            if source_values != expected_sources:
                issues.append(issue("error", "audience_plan_execution_sources_invalid", "audience_plan.execution_sources 必须逐项锁定四个 audience_execution 源字段。", path))
    scale = plan.get("scale_plan")
    if not isinstance(scale, dict):
        issues.append(issue("error", "scale_plan_missing", "drama_plan 缺少 scale_plan。", path))
        return expected
    count = scale.get("episode_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        issues.append(issue("error", "episode_count_invalid", "episode_count 必须是正整数。", path))
        return expected
    semantics = scale.get("duration_semantics")
    expected = {f"ep_{index}": None for index in range(1, count + 1)}
    locked_execution = is_lightweight_plan(plan) or semantics == "user_locked"
    if locked_execution:
        durations = scale.get("episode_durations_s")
        displays = scale.get("episode_duration_displays")
        total = scale.get("total_duration_s")
        total_display = scale.get("total_duration_display")
        if not isinstance(durations, list) or len(durations) != count:
            issues.append(issue("error", "episode_durations_invalid", "episode_durations_s 数量必须等于 episode_count。", path))
            return expected
        if isinstance(displays, list) and len(displays) != count:
            issues.append(issue("error", "episode_duration_displays_invalid", "episode_duration_displays 数量必须等于 episode_count。", path))
        numeric: list[int] = []
        for index, seconds in enumerate(durations, start=1):
            if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
                issues.append(issue("error", "episode_duration_invalid", f"第 {index} 集时长必须是数字。", path))
                continue
            value = int(round(float(seconds)))
            numeric.append(value)
            expected[f"ep_{index}"] = value
            display = displays[index - 1] if isinstance(displays, list) and index - 1 < len(displays) else None
            check_duration_pair(value, display, path, f"ep_{index}", issues)
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            if numeric and int(round(float(total))) != sum(numeric):
                issues.append(issue("error", "total_duration_mismatch", "total_duration_s 必须等于各集 episode_durations_s 之和。", path))
            check_duration_pair(total, total_display, path, "total", issues, total_display=True)
        else:
            issues.append(issue("error", "total_duration_invalid", "total_duration_s 必须是数字。", path))
    else:
        if semantics != "planning_estimate":
            issues.append(issue("error", "duration_semantics_invalid", "完整模式的代理规划时长必须标记 duration_semantics=planning_estimate；只有用户明确锁定精确时长时才使用 user_locked。", path))
        ranges = scale.get("estimated_episode_duration_ranges_s")
        displays = scale.get("estimated_episode_duration_displays")
        if not isinstance(ranges, list) or len(ranges) != count:
            issues.append(issue("error", "estimated_episode_duration_ranges_invalid", "estimated_episode_duration_ranges_s 数量必须等于 episode_count，且每项包含 min_s/max_s。", path))
        else:
            for index, duration_range in enumerate(ranges, start=1):
                if not isinstance(duration_range, dict):
                    issues.append(issue("error", "estimated_episode_duration_range_invalid", f"第 {index} 集预估时长区间必须是包含 min_s/max_s 的对象。", path))
                    continue
                minimum = duration_range.get("min_s")
                maximum = duration_range.get("max_s")
                if any(not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0 for value in (minimum, maximum)):
                    issues.append(issue("error", "estimated_episode_duration_range_invalid", f"第 {index} 集预估时长区间的 min_s/max_s 必须是正数。", path))
                elif minimum > maximum:
                    issues.append(issue("error", "estimated_episode_duration_range_order_invalid", f"第 {index} 集预估时长区间的 min_s 不得大于 max_s。", path))
        if not isinstance(displays, list) or len(displays) != count or any(not isinstance(value, str) or not value.strip() for value in displays):
            issues.append(issue("error", "estimated_episode_duration_displays_invalid", "estimated_episode_duration_displays 必须逐集提供明确标注为预估参考的非空显示文本。", path))
        total_range = scale.get("estimated_total_duration_range_s")
        if not isinstance(total_range, dict):
            issues.append(issue("error", "estimated_total_duration_range_invalid", "estimated_total_duration_range_s 必须是包含正数 min_s/max_s 的对象。", path))
        else:
            minimum = total_range.get("min_s")
            maximum = total_range.get("max_s")
            if any(not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0 for value in (minimum, maximum)):
                issues.append(issue("error", "estimated_total_duration_range_invalid", "estimated_total_duration_range_s 的 min_s/max_s 必须是正数。", path))
            elif minimum > maximum:
                issues.append(issue("error", "estimated_total_duration_range_order_invalid", "estimated_total_duration_range_s 的 min_s 不得大于 max_s。", path))
        total_display = scale.get("estimated_total_duration_display")
        if not isinstance(total_display, str) or not total_display.strip():
            issues.append(issue("error", "estimated_total_duration_display_invalid", "estimated_total_duration_display 必须提供明确标注为预估参考的非空显示文本。", path))
    delivery = plan.get("delivery_settings")
    if isinstance(delivery, dict):
        subtitle_enabled = delivery.get("subtitle_enabled")
        if not isinstance(subtitle_enabled, bool):
            issues.append(issue("error", "subtitle_enabled_invalid", "delivery_settings.subtitle_enabled 必须是布尔值；默认 false，用户明确要求字幕时为 true。", path))
        if subtitle_enabled is False and delivery.get("subtitle_policy") != "disabled":
            issues.append(issue("error", "subtitle_disabled_policy_missing", "字幕关闭时 subtitle_policy 必须为 disabled。", path))
        expected_deliverables = ["subtitle_master"] if subtitle_enabled is True else ["clean_master"]
        if delivery.get("final_deliverables") != expected_deliverables:
            issues.append(issue("error", "final_deliverables_invalid", f"final_deliverables 必须只包含单一最终视频版本：{expected_deliverables}。", path))
    return expected


def crowd_context() -> dict[str, Any]:
    return {"states": {}, "initial_states": {}, "character_ids": {}, "source_paths": {}, "segments": {}}


def check_request_snapshot(root: Path, segment: dict[str, Any], path: Path, issues: list[dict[str, Any]]) -> None:
    crowds = segment.get("crowds")
    required = any(isinstance(crowd, dict) and crowd.get("continuity_scope") == "recurring" for crowd in crowds) if isinstance(crowds, list) else False
    snapshot_value = segment.get("request_snapshot_file")
    if not snapshot_value:
        if required:
            issues.append(issue("error", "crowd_request_snapshot_missing", "复现群众必须登记 request_snapshot_file，指向真实 CLI dry-run JSON 或正式 task_file 的输入槽位与字节哈希。", path))
        return
    snapshot_path = relative_file(root, snapshot_value)
    if snapshot_path is None:
        issues.append(issue("error", "request_snapshot_path_invalid", "request_snapshot_file 必须是项目内相对路径。", path))
        return
    snapshot = load_json(snapshot_path, issues, required=True)
    slots = snapshot.get("slots") if isinstance(snapshot, dict) else None
    if not isinstance(slots, list):
        issues.append(issue("error", "request_snapshot_slots_invalid", "CLI 请求快照必须保存原始 slots 数组。", snapshot_path))
        return
    images = segment.get("reference_inputs") if isinstance(segment.get("reference_inputs"), list) else []
    expected_slots = {f"ref_image_{item['order'] - 1}" for item in images if isinstance(item, dict) and isinstance(item.get("order"), int) and not isinstance(item["order"], bool) and item["order"] > 0}
    image_slots = [item for item in slots if isinstance(item, dict) and (item.get("kind") == "image" or str(item.get("slot") or "").startswith("ref_image_"))]
    actual_slots = [item.get("slot") for item in image_slots]
    if len(actual_slots) != len(expected_slots) or set(str(value) for value in actual_slots) != expected_slots:
        issues.append(issue("error", "request_snapshot_image_slots_mismatch", "CLI 请求快照图片槽位必须与 reference_inputs[].order 一一对应，不得漏图、重槽或额外传图。", snapshot_path))
    for item in images:
        if not isinstance(item, dict) or not isinstance(item.get("order"), int) or isinstance(item["order"], bool):
            continue
        slot_name = f"ref_image_{item['order'] - 1}"
        matches = [slot for slot in image_slots if slot.get("slot") == slot_name]
        if len(matches) != 1:
            continue
        slot = matches[0]
        actual_path = relative_file(root, item.get("file"))
        uploaded = slot.get("ref")
        uploaded_path = Path(uploaded) if isinstance(uploaded, str) else None
        if slot.get("kind") != "image" or slot.get("identity") != "local_bytes" or uploaded_path is None or not uploaded_path.is_absolute() or actual_path is None or uploaded_path.resolve() != actual_path:
            issues.append(issue("error", "request_snapshot_image_file_mismatch", f"{slot_name} 必须记录该 order 对应真实文件的 image/local_bytes 回执。", snapshot_path))
            continue
        try:
            actual_hash = file_sha256(actual_path)
        except OSError as exc:
            issues.append(issue("error", "request_snapshot_image_unreadable", f"{slot_name} 无法读取图片核验 CLI 字节哈希：{exc}", snapshot_path))
        else:
            if slot.get("sha256") != actual_hash:
                issues.append(issue("error", "request_snapshot_image_hash_mismatch", f"{slot_name} CLI 回执 SHA-256 与当前输入图片字节不一致。", snapshot_path))


def check_crowd_reference(
    root: Path,
    crowd: dict[str, Any],
    segment: dict[str, Any],
    path: Path,
    asset_index: dict[str, Any],
    context: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    crowd_id = str(crowd.get("crowd_id") or "")
    reference = crowd.get("reference_source_id")
    if not isinstance(reference, str) or not reference.strip():
        if crowd.get("continuity_scope") == "recurring":
            issues.append(issue("error", "crowd_reference_missing", f"{crowd_id} 复现群众必须绑定真实 reference_source_id。", path))
        return
    inputs = segment.get("reference_inputs")
    matches = [item for item in inputs if isinstance(item, dict) and item.get("source_id") == reference and item.get("role") == "crowd_reference"] if isinstance(inputs, list) else []
    if not matches:
        issues.append(issue("error", "crowd_reference_not_passed", f"{crowd_id} 的 {reference} 必须登记为本 SEG 的真实 crowd_reference 图片输入。", path))
        return
    for item in matches:
        value = item.get("file")
        actual_path = relative_file(root, value)
        if actual_path is None or not actual_path.is_file() or actual_path.suffix.lower() not in IMAGE_INPUT_SUFFIXES:
            issues.append(issue("error", "crowd_reference_file_invalid", f"{crowd_id} 的群众参考必须是项目内真实图片文件。", path))
            continue
        previous_path = context["source_paths"].setdefault(reference, actual_path)
        if previous_path != actual_path:
            issues.append(issue("error", "crowd_reference_file_changed", f"{reference} 在不同 SEG 中必须指向同一已登记文件；替换图片须创建新来源或资产版本。", path))
        if reference.startswith("SRC"):
            source_path = root / "00_制作控制/source_manifest.json"
            if "sources" not in context:
                manifest = load_json(source_path, issues, required=True)
                context["sources"] = manifest.get("sources", []) if isinstance(manifest, dict) else []
            sources = context["sources"]
            registered = [source for source in sources if isinstance(source, dict) and source.get("source_id") == reference] if isinstance(sources, list) else []
            if len(registered) != 1:
                issues.append(issue("error", "crowd_source_registration_invalid", f"{reference} 必须在 source_manifest 中有唯一来源记录。", path))
                continue
            source = registered[0]
            if source.get("media_type") != "image" or relative_file(root, source.get("stored_path")) != actual_path:
                issues.append(issue("error", "crowd_source_file_mismatch", f"{reference} 的群众输入必须与来源登记的图片 stored_path 一致。", path))
            expected_hash = str(source.get("sha256") or "")
            try:
                actual_hash = file_sha256(actual_path)
            except OSError as exc:
                issues.append(issue("error", "crowd_source_hash_unreadable", f"{reference} 无法读取并核验来源哈希：{exc}", path))
            else:
                if expected_hash != actual_hash:
                    issues.append(issue("error", "crowd_source_hash_mismatch", f"{reference} 的群众参考文件 SHA-256 与来源登记不一致。", path))
        else:
            if not reference.startswith("CRD"):
                issues.append(issue("error", "crowd_reference_source_invalid", f"{crowd_id} 的群众参考必须来自已批准 CRD 资产版本或已登记 SRC 图片来源。", path))
            if reference in asset_index["known_state_refs"]:
                check_state_ref(reference, asset_index, path, issues, crowd_id)
            else:
                check_asset_ref(reference, asset_index, path, issues, crowd_id)
            registered_files = asset_index.get("files_by_ref", {}).get(reference, set())
            if not any(relative_file(root, registered_file) == actual_path for registered_file in registered_files):
                issues.append(issue("error", "crowd_asset_file_mismatch", f"{reference} 的群众参考文件必须属于该 approved 资产版本。", path))


def check_crowd_list(
    root: Path,
    crowds: Any,
    path: Path,
    issues: list[dict[str, Any]],
    context: dict[str, Any],
    *,
    complete: bool = True,
    segment: dict[str, Any] | None = None,
    asset_index: dict[str, Any] | None = None,
    draft_text: str | None = None,
) -> set[str]:
    if not isinstance(crowds, list):
        issues.append(issue("error", "crowds_invalid", "crowds 必须是数组；没有群众时明确写 []。", path))
        return set()
    ids: set[str] = set()
    for crowd in crowds:
        if not isinstance(crowd, dict):
            issues.append(issue("error", "crowd_invalid", "crowds 每项必须是群众执行对象。", path))
            continue
        crowd_id = crowd.get("crowd_id")
        if not isinstance(crowd_id, str) or re.fullmatch(r"CRD\d{3,}", crowd_id) is None:
            issues.append(issue("error", "crowd_id_invalid", "crowd_id 必须为 CRD001 等稳定群体 ID。", path))
            continue
        if crowd_id in ids:
            issues.append(issue("error", "crowd_id_duplicate", f"同一快照 crowd_id 重复：{crowd_id}", path))
        ids.add(crowd_id)
        required = ["state_id", "count_or_density"]
        if complete:
            required.extend(("screen_position", "action", "allowed_changes"))
        for field in required:
            if not isinstance(crowd.get(field), str) or not crowd[field].strip():
                issues.append(issue("error", "crowd_field_missing", f"{crowd_id}.{field} 必须是非空文字。", path))
        if not isinstance(crowd.get("continuity_scope"), str) or crowd["continuity_scope"] not in {"shot", "recurring"}:
            issues.append(issue("error", "crowd_continuity_scope_invalid", f"{crowd_id}.continuity_scope 必须为 shot 或 recurring。", path))
        if not isinstance(crowd.get("visibility"), str) or crowd["visibility"] not in {"indistinct", "identifiable"}:
            issues.append(issue("error", "crowd_visibility_invalid", f"{crowd_id}.visibility 必须为 indistinct 或 identifiable。", path))
        if complete and not isinstance(crowd.get("reference_source_id"), str):
            issues.append(issue("error", "crowd_reference_field_missing", f"{crowd_id}.reference_source_id 必须为字符串；单镜无独立参考时可以为空。", path))
        appearance = crowd.get("appearance")
        appearance_values: list[str] = []
        for field in CROWD_APPEARANCE_FIELDS:
            value = appearance.get(field) if isinstance(appearance, dict) else None
            if not isinstance(value, str) or not value.strip():
                issues.append(issue("error", "crowd_appearance_field_missing", f"{crowd_id}.appearance.{field} 必须是非空文字。", path))
            else:
                appearance_values.append(value)
        members = crowd.get("members")
        if not isinstance(members, list) or (crowd.get("visibility") == "identifiable" and not members):
            issues.append(issue("error", "crowd_members_invalid", f"{crowd_id}.members 必须是数组，可辨认群众必须逐人登记。", path))
            members = []
        member_ids: set[str] = set()
        member_snapshot: list[tuple[str, str]] = []
        for member in members:
            if not isinstance(member, dict):
                issues.append(issue("error", "crowd_member_invalid", f"{crowd_id}.members 每项必须是对象。", path))
                continue
            member_id = member.get("member_id")
            if not isinstance(member_id, str) or re.fullmatch(re.escape(crowd_id) + r"-M\d+", member_id) is None:
                issues.append(issue("error", "crowd_member_id_invalid", f"{crowd_id} 成员必须使用本群体的稳定 member_id，例如 {crowd_id}-M01。", path))
                continue
            if member_id in member_ids:
                issues.append(issue("error", "crowd_member_id_duplicate", f"群众成员 ID 重复：{member_id}", path))
            member_ids.add(member_id)
            for field in ("appearance", "screen_position"):
                if not isinstance(member.get(field), str) or not member[field].strip():
                    issues.append(issue("error", "crowd_member_field_missing", f"{member_id}.{field} 必须是非空文字。", path))
            member_appearance = member.get("appearance")
            if isinstance(member_appearance, str):
                appearance_values.append(member_appearance)
                member_snapshot.append((member_id, member_appearance))
            character_id = member.get("character_id")
            if character_id is not None:
                if not isinstance(character_id, str) or re.fullmatch(r"CHR\d{3,}", character_id) is None:
                    issues.append(issue("error", "crowd_member_character_id_invalid", f"{member_id}.character_id 必须是 CHRxxx。", path))
                elif context["character_ids"].setdefault(member_id, character_id) != character_id:
                    issues.append(issue("error", "crowd_member_character_mapping_changed", f"{member_id} 已升级的 character_id 映射不得无因替换。", path))
        state_id = crowd.get("state_id")
        if isinstance(state_id, str) and state_id.strip():
            initial_state = context["initial_states"].setdefault(crowd_id, state_id)
            if state_id != initial_state and (not isinstance(crowd.get("change_reason"), str) or not crowd["change_reason"].strip()):
                issues.append(issue("error", "crowd_state_change_reason_missing", f"{crowd_id} 新 state_id={state_id} 必须填写 change_reason。", path))
            snapshot = (crowd.get("count_or_density"), tuple(appearance.get(field) for field in CROWD_APPEARANCE_FIELDS) if isinstance(appearance, dict) else (), tuple(sorted(member_snapshot)))
            previous = context["states"].setdefault((crowd_id, state_id), snapshot)
            if previous != snapshot:
                issues.append(issue("error", "crowd_state_snapshot_changed", f"{crowd_id}+{state_id} 的人数、群体外观或成员外观发生漂移；剧情变化必须建立新状态并说明原因。", path))
        if segment is not None:
            segment_key = (str(path), str(segment.get("segment_id") or ""))
            previous_segments = context["segments"].setdefault(crowd_id, set())
            previous_segments.add(segment_key)
            if len(previous_segments) > 1 and crowd.get("continuity_scope") != "recurring":
                issues.append(issue("error", "crowd_recurring_scope_required", f"{crowd_id} 跨 SEG 复现必须声明 recurring 并传入群众参考。", path))
            check_crowd_reference(root, crowd, segment, path, asset_index or blank_asset_index(), context, issues)
        if draft_text is not None:
            for value in appearance_values:
                if value not in draft_text:
                    issues.append(issue("error", "crowd_appearance_not_in_draft", f"导演编译底稿缺少 {crowd_id} 的中文外观或成员锚点：{value}", path))
    return ids


def check_crowd_storyboard(root: Path, data: dict[str, Any], path: Path, issues: list[dict[str, Any]], context: dict[str, Any]) -> None:
    segments = data.get("segments") if isinstance(data.get("segments"), list) else []
    by_segment: dict[str, dict[str, dict[str, Any]]] = {}
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        crowds = segment.get("crowds", [])
        check_crowd_list(root, crowds, path, issues, context)
        by_segment[str(segment.get("segment_id") or "")] = {crowd["crowd_id"]: crowd for crowd in crowds if isinstance(crowd, dict) and isinstance(crowd.get("crowd_id"), str)} if isinstance(crowds, list) else {}
    bindings: dict[tuple[str, str], int] = {}
    crowd_shot_counts: dict[str, int] = {}
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        crowd_ids = shot.get("crowd_ids", [])
        if not isinstance(crowd_ids, list) or not all(isinstance(value, str) for value in crowd_ids):
            issues.append(issue("error", "shot_crowd_ids_invalid", "shots[].crowd_ids 必须是群众 ID 数组。", path))
            continue
        segment_id = str(shot.get("segment_id") or "")
        if len(set(crowd_ids)) != len(crowd_ids):
            issues.append(issue("error", "shot_crowd_ids_duplicate", "同一镜头的 crowd_ids 不得重复。", path))
        for crowd_id in crowd_ids:
            crowd = by_segment.get(segment_id, {}).get(crowd_id)
            if crowd is None:
                issues.append(issue("error", "shot_crowd_unknown", f"{shot.get('shot_id')} 的 {crowd_id} 未在对应 SEG 群众快照中声明。", path))
                continue
            key = (segment_id, crowd_id)
            bindings[key] = bindings.get(key, 0) + 1
            crowd_shot_counts[crowd_id] = crowd_shot_counts.get(crowd_id, 0) + 1
    for segment_id, crowds in by_segment.items():
        for crowd_id in crowds:
            if (segment_id, crowd_id) not in bindings:
                issues.append(issue("error", "crowd_shot_binding_missing", f"{segment_id} 的 {crowd_id} 必须通过 shots[].crowd_ids 绑定真实镜头。", path))
            if crowd_shot_counts.get(crowd_id, 0) > 1 and crowds[crowd_id].get("continuity_scope") != "recurring":
                issues.append(issue("error", "crowd_recurring_scope_required", f"{crowd_id} 跨镜头或 SEG 复现必须声明 recurring。", path))


def check_project_crowds(
    root: Path,
    plan: Any,
    asset_index: dict[str, Any],
    issues: list[dict[str, Any]],
    episode_filter: str | None = None,
    *,
    storyboard: bool = False,
    video: bool = False,
) -> None:
    context = crowd_context()
    lightweight = is_lightweight_plan(plan) and lightweight_constraints_valid(plan)
    if not lightweight:
        card_path = root / "00_制作控制/project_data_card.json"
        card = load_json(card_path, issues, required=False)
        if isinstance(card, dict):
            check_crowd_list(root, card.get("crowds"), card_path, issues, context, complete=False)
    if not storyboard and not video:
        return
    state = load_json(root / "00_制作控制/制作状态.json", issues, required=False)
    episode_states = state.get("episodes") if isinstance(state, dict) else None
    for episode_id, episode_root in episode_dirs(root, episode_filter):
        episode_state = episode_states.get(episode_id) if isinstance(episode_states, dict) else None
        statuses = episode_state.get("stage_status") if isinstance(episode_state, dict) else None
        if storyboard and not lightweight and (not isinstance(statuses, dict) or statuses.get("storyboard") not in {"pending", "invalidated"}):
            storyboard_path = episode_root / f"02_分镜/storyboard_{episode_id}.json"
            storyboard_data = load_json(storyboard_path, issues, required=False)
            if isinstance(storyboard_data, dict):
                check_crowd_storyboard(root, storyboard_data, storyboard_path, issues, context)
        if not video or (isinstance(statuses, dict) and statuses.get("video") in {"pending", "invalidated"}):
            continue
        path = episode_root / f"04_视频片段/video_manifest_{episode_id}.json"
        manifest = load_json(path, issues, required=False)
        segments = manifest.get("segments") if isinstance(manifest, dict) else None
        for segment in segments if isinstance(segments, list) else []:
            if not isinstance(segment, dict):
                continue
            draft_path = relative_file(root, segment.get("director_draft_file"))
            draft_text = None
            if draft_path is not None and draft_path.is_file():
                draft_text = _read_prompt_text(draft_path, issues)
            elif isinstance(segment.get("crowds"), list) and segment["crowds"]:
                issues.append(issue("error", "crowd_director_draft_missing", "含群众的视频必须提供真实导演编译底稿，核验全部中文外观和成员锚点。", path))
            check_crowd_list(root, segment.get("crowds"), path, issues, context, segment=segment, asset_index=asset_index, draft_text=draft_text)
            check_request_snapshot(root, segment, path, issues)


def check_keyframes(
    root: Path,
    asset_index: dict[str, Any],
    issues: list[dict[str, Any]],
    episode_filter: str | None = None,
) -> None:
    for episode_id, episode_root in episode_dirs(root, episode_filter):
        path = episode_root / f"03_资产/keyframe_manifest_{episode_id}.json"
        data = load_json(path, issues, required=False)
        if not isinstance(data, dict):
            continue
        if data.get("episode_id") != episode_id:
            issues.append(issue("error", "episode_id_mismatch", "keyframe_manifest episode_id 与目录不一致。", path))
        index = load_storyboard_index(root, episode_id, issues)
        keyframes = data.get("keyframes")
        if not isinstance(keyframes, list):
            issues.append(issue("error", "keyframes_invalid", "keyframes 必须是数组。", path))
            continue
        check_unique(keyframes, "keyframe_id", path, issues, "keyframes")
        planned_keyframes = {
            segment_id: len(requests)
            for segment_id, requests in index.get("keyframe_requests", {}).items()
            if isinstance(segment_id, str) and isinstance(requests, list)
        }
        actual_keyframes: dict[str, int] = {}
        seen_highlight_indexes: set[tuple[str, int]] = set()
        for item in keyframes:
            if not isinstance(item, dict):
                continue
            keyframe_id = item.get("keyframe_id")
            segment_id = item.get("segment_id")
            shot_id = item.get("shot_id")
            if isinstance(segment_id, str) and index["segments"] and segment_id not in index["segments"]:
                issues.append(issue("error", "keyframe_unknown_segment", f"关键帧引用了不存在的 segment_id：{segment_id}", path))
            if isinstance(shot_id, str) and index["shots"] and shot_id not in index["shots"]:
                issues.append(issue("error", "keyframe_unknown_shot", f"关键帧引用了不存在的 shot_id：{shot_id}", path))
            status = str(item.get("status") or "").strip()
            if isinstance(segment_id, str) and status not in {"rejected", "superseded"}:
                actual_keyframes[segment_id] = actual_keyframes.get(segment_id, 0) + 1
            if item.get("role") != "highlight":
                issues.append(issue("error", "keyframe_role_invalid", f"{keyframe_id or '关键帧'} role 必须为 highlight。", path))
            highlight_index = item.get("highlight_index")
            if not isinstance(highlight_index, int) or isinstance(highlight_index, bool) or highlight_index < 1:
                issues.append(issue("error", "keyframe_highlight_index_invalid", f"{keyframe_id or '关键帧'} highlight_index 必须是从 1 开始的正整数。", path))
            elif isinstance(segment_id, str):
                key = (segment_id, highlight_index)
                if key in seen_highlight_indexes:
                    issues.append(issue("error", "keyframe_highlight_index_duplicate", f"{segment_id} 的 highlight_index={highlight_index} 重复。", path))
                seen_highlight_indexes.add(key)
            for used_segment in item.get("used_by_segments") or []:
                if index["segments"] and used_segment not in index["segments"]:
                    issues.append(issue("error", "keyframe_unknown_used_segment", f"used_by_segments 引用了不存在的 segment_id：{used_segment}", path))
            file_value = item.get("file")
            if file_value and not file_exists(root, file_value):
                issues.append(issue("error", "keyframe_file_missing", f"关键帧文件不存在：{file_value}", path))
            if isinstance(file_value, str) and not re.search(r"关键帧_KF\d+_SEG\d+_highlight-\d+_v\d+_ep_[1-9]\d*\.[A-Za-z0-9]+$", file_value):
                issues.append(issue("error", "keyframe_file_name_invalid", f"{keyframe_id or '关键帧'} 文件名必须使用 highlight-N 高光序号。", path))
            if item.get("tool") != "image_edit":
                issues.append(issue("error", "keyframe_tool_not_image_edit", f"{keyframe_id or '关键帧'} 必须使用 image_edit I2I 生成，不得使用 image_gen 或纯文生图。", path))
            asset_refs = item.get("asset_refs")
            if asset_refs is not None:
                if not isinstance(asset_refs, list):
                    issues.append(issue("error", "asset_refs_invalid", f"{keyframe_id or '关键帧'} asset_refs 必须是数组。", path))
                else:
                    for ref in asset_refs:
                        check_asset_ref(ref, asset_index, path, issues, str(keyframe_id or "关键帧"))
            state_refs = item.get("state_refs")
            if state_refs is not None:
                if not isinstance(state_refs, list):
                    issues.append(issue("error", "state_refs_invalid", f"{keyframe_id or '关键帧'} state_refs 必须是数组。", path))
                else:
                    for ref in state_refs:
                        check_state_ref(ref, asset_index, path, issues, str(keyframe_id or "关键帧"))
            style_terms = combined_strings(item, field="style_prompt_terms")
            check_style_anchor_contract(
                root,
                path,
                str(keyframe_id or "关键帧"),
                item.get("tool"),
                item.get("prompt_path"),
                combined_strings(item, field="style_anchor_reference_ids"),
                style_terms,
                combined_strings(item, field="style_adopt"),
                combined_strings(item, field="style_exclude"),
                issues,
            )
            check_generation_prompt_file(root, path, str(keyframe_id or "关键帧"), item.get("tool"), item.get("prompt_path"), issues)
        for segment_id, actual_count in actual_keyframes.items():
            if planned_keyframes.get(segment_id, 0) == 0 and actual_count:
                issues.append(issue("error", "keyframe_unplanned_segment", f"{segment_id} 实际生成了 {actual_count} 张有效关键帧，但 storyboard.keyframe_requests 未规划该段关键帧。", path))
        planned_total = sum(planned_keyframes.values())
        actual_total = sum(actual_keyframes.values())
        if planned_total and actual_total != planned_total:
            issues.append(issue("error", "episode_keyframe_count_mismatch", f"本集实际有效关键帧数量 {actual_total} 必须等于 storyboard.keyframe_requests 规划总数 {planned_total}。", path))
        for segment_id, planned_count in planned_keyframes.items():
            actual_count = actual_keyframes.get(segment_id, 0)
            if actual_count != planned_count:
                issues.append(issue("error", "keyframe_count_mismatch", f"{segment_id} 实际有效关键帧数量 {actual_count} 必须等于 storyboard.keyframe_requests 规划数量 {planned_count}。", path))

def accepted_video_segments(root: Path, episode_id: str, issues: list[dict[str, Any]]) -> set[str]:
    path = root / f"episodes/{episode_id}/04_视频片段/video_manifest_{episode_id}.json"
    data = load_json(path, issues, required=False)
    segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segments, list):
        return set()
    return {
        item.get("segment_id")
        for item in segments
        if isinstance(item, dict) and isinstance(item.get("segment_id"), str) and item.get("status") == "accepted"
    }


def accepted_video_segment_order(
    root: Path,
    episode_id: str,
    issues: list[dict[str, Any]],
    allow_candidate: bool = False,
) -> list[str]:
    path = root / f"episodes/{episode_id}/04_视频片段/video_manifest_{episode_id}.json"
    data = load_json(path, issues, required=False)
    segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segments, list):
        return []
    return [
        item["segment_id"]
        for item in segments
        if isinstance(item, dict)
        and isinstance(item.get("segment_id"), str)
        and item.get("status") in ({"candidate", "accepted"} if allow_candidate else {"accepted"})
    ]


def delivery_segment_refs(data: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    direct_fields = ("source_segments", "segment_ids", "used_segments", "video_segments", "accepted_segments")
    for field in direct_fields:
        value = data.get(field)
        if isinstance(value, list):
            refs.update(item for item in value if isinstance(item, str))
            for item in value:
                if isinstance(item, dict) and isinstance(item.get("segment_id"), str):
                    refs.add(item["segment_id"])
    for field in ("segments", "segment_outputs", "outputs"):
        value = data.get(field)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and isinstance(item.get("segment_id"), str):
                    refs.add(item["segment_id"])
    return refs


def output_values(data: dict[str, Any]) -> list[str] | None:
    outputs = data.get("outputs")
    if not isinstance(outputs, list):
        return None
    values: list[str] = []
    for item in outputs:
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, dict) and isinstance(item.get("file"), str):
            values.append(item["file"])
        else:
            return None
    return values


def report_is_blocked(root: Path, entry: Any) -> bool:
    if isinstance(entry, dict):
        return entry.get("status") == "blocked" or entry.get("result") == "blocked"
    target = relative_file(root, entry)
    if target is None or not target.is_file() or target.suffix.lower() != ".json":
        return False
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and (data.get("status") == "blocked" or data.get("result") == "blocked")


def check_report_entries(root: Path, entries: Any, expected_count: int, path: Path, issues: list[dict[str, Any]]) -> None:
    if not isinstance(entries, list):
        issues.append(issue("error", "basic_qc_reports_invalid", "basic_qc_reports 必须是数组。", path))
        return
    if len(entries) != expected_count:
        issues.append(issue("error", "basic_qc_reports_count_invalid", f"basic_qc_reports 数量应为 {expected_count}。", path))
    for entry in entries:
        if isinstance(entry, str):
            if not file_exists(root, entry):
                issues.append(issue("error", "basic_qc_report_missing", f"基础质检报告不存在：{entry}", path))
        elif isinstance(entry, dict):
            report_file = entry.get("file")
            if report_file and not file_exists(root, report_file):
                issues.append(issue("error", "basic_qc_report_missing", f"基础质检报告不存在：{report_file}", path))
        else:
            issues.append(issue("error", "basic_qc_report_invalid", "basic_qc_reports 每项必须是路径或对象。", path))
        if report_is_blocked(root, entry):
            issues.append(issue("error", "basic_qc_report_blocked", "基础媒体可用性检查结果为 blocked，不得交付。", path))


def check_continuity_for_delivery(root: Path, episode_id: str, accepted_order: list[str], issues: list[dict[str, Any]]) -> None:
    path = root / f"episodes/{episode_id}/04_视频片段/continuity_{episode_id}.json"
    data = load_json(path, issues, required=bool(accepted_order))
    if not isinstance(data, dict):
        return
    if data.get("episode_id") != episode_id:
        issues.append(issue("error", "episode_id_mismatch", "continuity episode_id 与目录不一致。", path))
    frames = data.get("frames")
    if not isinstance(frames, list):
        issues.append(issue("error", "continuity_frames_invalid", "continuity.frames 必须是数组。", path))
        frames = []
    roles_by_segment: dict[str, set[str]] = {}
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        segment_id = frame.get("segment_id")
        role = frame.get("role")
        if isinstance(segment_id, str) and isinstance(role, str):
            roles_by_segment.setdefault(segment_id, set()).add(role)
        file_value = frame.get("file")
        if file_value and not file_exists(root, file_value):
            issues.append(issue("error", "continuity_frame_file_missing", f"连续性抽帧文件不存在：{file_value}", path))
        if isinstance(file_value, str) and Path(file_value).suffix.lower() not in IMAGE_INPUT_SUFFIXES:
            issues.append(issue("error", "continuity_frame_suffix_invalid", f"连续性抽帧必须是图片文件：{file_value}", path))
    for segment_id in accepted_order:
        roles = roles_by_segment.get(segment_id, set())
        missing = sorted({"start", "scene", "tail"} - roles)
        if missing:
            issues.append(issue("warning", "continuity_frame_roles_missing", f"{segment_id} accepted 后建议 continuity.frames 覆盖 start|scene|tail，当前缺少：{missing}；该缺口只作内部连续性备注，不阻断已生成视频交付。", path))
    seams = data.get("seams")
    if not isinstance(seams, list):
        issues.append(issue("error", "continuity_seams_invalid", "continuity.seams 必须是数组。", path))
        seams = []
    seams_by_pair = {
        (item.get("from_segment"), item.get("to_segment")): item
        for item in seams
        if isinstance(item, dict)
    }
    for left, right in zip(accepted_order, accepted_order[1:]):
        seam = seams_by_pair.get((left, right))
        if not isinstance(seam, dict):
            issues.append(issue("warning", "continuity_seam_missing", f"缺少 {left} -> {right} 的 seam 记录；该缺口只作内部连续性备注，不阻断已生成视频交付。", path))
            continue
        if seam.get("status") != "verified":
            issues.append(issue("warning", "continuity_seam_not_verified", f"{left} -> {right} seam 建议为 verified；未验证只作内部连续性备注，不触发自动重生。", path))
        if not isinstance(seam.get("selected_cut"), dict) or not seam.get("selected_cut"):
            issues.append(issue("warning", "continuity_seam_cut_missing", f"{left} -> {right} seam 建议登记 selected_cut；缺口只作内部连续性备注。", path))
        for field in ("outgoing_window_frames", "incoming_window_frames"):
            value = seam.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 12:
                issues.append(issue("warning", "continuity_seam_window_invalid", f"{left} -> {right} {field} 建议不少于 12；不足时记录 best available，不阻断已生成视频交付。", path))


def check_delivery(
    root: Path,
    expected_durations: dict[str, int | None],
    issues: list[dict[str, Any]],
    episode_filter: str | None = None,
    lightweight: bool = False,
) -> None:
    for episode_id, episode_root in episode_dirs(root, episode_filter):
        path = episode_root / f"05_成片/delivery_manifest_{episode_id}.json"
        data = load_json(path, issues, required=False)
        if not isinstance(data, dict):
            continue
        if data.get("episode_id") != episode_id:
            issues.append(issue("error", "episode_id_mismatch", "delivery_manifest episode_id 与目录不一致。", path))
        assembly_confirmation = data.get("assembly_confirmation")
        if lightweight:
            if assembly_confirmation not in (None, {}):
                issues.append(issue("error", "lightweight_assembly_confirmation_invalid", "轻量模式单条视频不得创建拼接确认。", path))
            assembly_confirmation = {}
        elif not isinstance(assembly_confirmation, dict):
            issues.append(issue("error", "assembly_confirmation_missing", "delivery_manifest 必须登记进入成片拼接的 interaction.ask 确认。", path))
            assembly_confirmation = {}
        if not lightweight and assembly_confirmation.get("confirmation_purpose") != "final_assembly":
            issues.append(issue("error", "assembly_confirmation_purpose_invalid", "assembly_confirmation.confirmation_purpose 必须为 final_assembly。", path))
        if not lightweight and not str(assembly_confirmation.get("interaction_ask_call_id") or "").strip():
            issues.append(issue("error", "assembly_confirmation_call_id_missing", "assembly_confirmation 必须记录 interaction_ask_call_id。", path))
        if not lightweight and assembly_confirmation.get("interaction_ask_result") != "proceed_assembly":
            issues.append(issue("error", "assembly_confirmation_result_invalid", "assembly_confirmation.interaction_ask_result 必须为 proceed_assembly。", path))
        if not lightweight and not str(assembly_confirmation.get("user_message") or "").strip():
            issues.append(issue("error", "assembly_confirmation_user_message_missing", "assembly_confirmation.user_message 不能为空。", path))
        if not lightweight and parse_iso_time(assembly_confirmation.get("confirmed_at")) is None:
            issues.append(issue("error", "assembly_confirmation_time_invalid", "assembly_confirmation.confirmed_at 必须是带时区 ISO-8601 时间。", path))
        confirmation_records = load_confirmation_records(root, issues, required=True)
        matching_video_confirmations = [
            record
            for record in confirmation_records
            if record.get("stage") == "video"
            and record.get("episode_id") == episode_id
            and record.get("confirmation_purpose") == "video_acceptance_and_final_assembly"
            and record.get("interaction_ask_call_id") == assembly_confirmation.get("interaction_ask_call_id")
            and record.get("interaction_ask_result") == "proceed_assembly"
        ]
        if not lightweight and not matching_video_confirmations:
            issues.append(issue("error", "assembly_confirmation_video_record_missing", "assembly_confirmation 必须与同集 stage=video 用户确认记录使用同一 interaction.ask 调用 ID 和 proceed_assembly 结果。", path))
        subtitle_enabled = data.get("subtitle_enabled")
        if not isinstance(subtitle_enabled, bool):
            issues.append(issue("error", "subtitle_enabled_invalid", "subtitle_enabled 必须是布尔值；默认 false，用户明确要求字幕时为 true。", path))
        if data.get("status") not in {"deliverable", "candidate"}:
            issues.append(issue("error", "delivery_status_not_deliverable", "delivery_manifest.status 必须为 deliverable 或 candidate；blocked 不得交付。", path))
        duration = data.get("duration_s")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            check_duration_pair(duration, data.get("duration_display"), path, "delivery", issues)
            expected_duration = expected_durations.get(episode_id)
            if expected_duration is not None and int(round(float(duration))) != expected_duration:
                issues.append(issue("error", "delivery_duration_mismatch", "user_locked 或轻量精确时长要求下，成片实际总时长必须等于锁定的本集执行时长。", path))
        else:
            issues.append(issue("error", "delivery_duration_invalid", "delivery_manifest.duration_s 必须是数字。", path))
        if not file_inside(root, data.get("clean_master"), episode_root):
            issues.append(issue("error", "clean_master_missing", "clean_master 必须指向当前分集目录下真实媒体文件。", path))
        if subtitle_enabled is True and not file_inside(root, data.get("subtitle_master"), episode_root):
            issues.append(issue("error", "subtitle_master_missing", "字幕开启时 subtitle_master 必须指向当前分集目录下真实媒体文件。", path))
        if subtitle_enabled is False:
            for field in ("subtitle_master", "asr_source", "subtitle_final", "subtitle_source", "subtitle_burn_params", "asr_alignment_report"):
                if str(data.get(field) or "").strip():
                    issues.append(issue("error", "subtitle_disabled_field_not_empty", f"字幕关闭时 {field} 必须留空。", path))
        outputs = output_values(data)
        if outputs is None:
            issues.append(issue("error", "outputs_invalid", "outputs 必须是路径数组，或每项包含 file。", path))
        elif subtitle_enabled is False and outputs != [data.get("clean_master")]:
            issues.append(issue("error", "outputs_mismatch", "outputs 必须与用户可见正式交付文件精确一致：字幕关闭时只交付 [clean_master]。", path))
        elif subtitle_enabled is True and outputs != [data.get("subtitle_master")]:
            issues.append(issue("error", "outputs_mismatch", "outputs 必须与用户可见正式交付文件精确一致：字幕开启时只交付 [subtitle_master]。", path))
        reports = data.get("basic_qc_reports")
        if reports not in (None, []):
            if isinstance(reports, list):
                check_report_entries(root, reports, len(reports), path, issues)
            else:
                issues.append(issue("error", "basic_qc_reports_invalid", "basic_qc_reports 必须是数组。", path))
        if subtitle_enabled is True:
            asr_alignment_report = data.get("asr_alignment_report")
            if str(asr_alignment_report or "").strip() and (not file_inside(root, asr_alignment_report, episode_root) or report_is_blocked(root, asr_alignment_report)):
                issues.append(issue("error", "asr_alignment_report_invalid", "asr_alignment_report 如存在，必须指向当前分集目录下未 blocked 的内部追溯文件。", path))
            subtitle_source = data.get("subtitle_source")
            if not file_inside(root, subtitle_source, episode_root):
                issues.append(issue("error", "subtitle_source_missing", "字幕开启时必须存在当前分集目录下的 subtitle_source。", path))
            elif isinstance(subtitle_source, str) and not re.search(r"字幕_时间轴_v\d+_ep_[1-9]\d*\.srt$", subtitle_source):
                issues.append(issue("error", "subtitle_source_name_invalid", "subtitle_source 应指向 字幕_时间轴_vNN_ep_N.srt。", path))
            subtitle_final = data.get("subtitle_final")
            if not file_inside(root, subtitle_final, episode_root):
                issues.append(issue("error", "subtitle_final_missing", "字幕开启时必须存在当前分集目录下的 subtitle_final。", path))
            elif isinstance(subtitle_final, str) and not re.search(r"字幕_最终版_v\d+_ep_[1-9]\d*\.json$", subtitle_final):
                issues.append(issue("error", "subtitle_final_name_invalid", "subtitle_final 应指向 字幕_最终版_vNN_ep_N.json。", path))
        accepted_order = accepted_video_segment_order(root, episode_id, issues, allow_candidate=lightweight)
        accepted = set(accepted_order)
        if not lightweight and assembly_confirmation.get("segment_ids") != accepted_order:
            issues.append(issue("error", "assembly_confirmation_segments_mismatch", "assembly_confirmation.segment_ids 必须按顺序精确等于当前成片采用的 accepted SEG。", path))
        for segment_id in sorted(delivery_segment_refs(data)):
            if segment_id not in accepted:
                issues.append(issue("error", "delivery_non_accepted_segment", f"delivery 使用了不符合当前模式状态要求的视频片段：{segment_id}", path))
        if not lightweight:
            check_continuity_for_delivery(root, episode_id, accepted_order, issues)


def dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for item in issues:
        key = (item.get("level"), item.get("code"), item.get("message"), item.get("path"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def check_local_capability_profile(root: Path, issues: list[dict[str, Any]]) -> None:
    path = root / "tools/h3.json"
    profile = load_json(path, issues, required=True)
    capabilities = profile.get("capabilities") if isinstance(profile, dict) else None
    if not isinstance(profile, dict) or profile.get("model") != "H3" or not isinstance(capabilities, dict):
        issues.append(issue("error", "h3_capability_profile_invalid", "本地视频能力档必须声明唯一 H3 模型及 capabilities 对象。", path))
        return
    if capabilities.get("min_duration_s") != 4 or isinstance(capabilities.get("min_duration_s"), bool) or capabilities.get("max_duration_s") != 15 or isinstance(capabilities.get("max_duration_s"), bool) or capabilities.get("duration_integer_only") is not True:
        issues.append(issue("error", "h3_capability_duration_invalid", "当前 H3 部署能力必须保持 4-15 整数秒，不能通过改能力档扩展模型能力。", path))
    modes = capabilities.get("modes")
    required_modes = {"T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"}
    if not isinstance(modes, list) or any(not isinstance(mode, str) for mode in modes) or set(modes) != required_modes or len(modes) != len(required_modes):
        issues.append(issue("error", "h3_capability_modes_invalid", "H3 能力档必须完整且唯一列出五种真实模式。", path))
    limits = capabilities.get("mode_ref_limits")
    maxima = {"T2VA": (0, 0, 0), "I2VA": (2, 0, 0), "FL2VA": (2, 0, 0), "L2VA": (2, 0, 0), "Ref2VA": (9, 3, 3)}
    for mode, expected in maxima.items():
        value = limits.get(mode) if isinstance(limits, dict) else None
        if not isinstance(value, dict):
            issues.append(issue("error", "h3_capability_mode_limits_missing", f"缺少 {mode} 的模式参考上限。", path))
            continue
        for field, maximum in zip(("images_max", "videos_max", "audios_max"), expected):
            count = value.get(field)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0 or count > maximum or (maximum > 0 and count == 0):
                issues.append(issue("error", "h3_capability_reference_limit_invalid", f"{mode}.{field} 必须是实际支持范围内的整数，上限 {maximum}。", path))
        if mode == "Ref2VA":
            if value.get("audio_requires_visual_input") is not True or value.get("total_files_max") != 12 or isinstance(value.get("total_files_max"), bool):
                issues.append(issue("error", "h3_capability_multimodal_limits_invalid", "Ref2VA 必须限制总参考文件为 12，且音频需要视觉输入。", path))
            for kind in ("video", "audio"):
                if value.get(kind + "_per_clip_s") != [2, 15] or value.get(kind + "_total_s") != 15:
                    issues.append(issue("error", "h3_capability_media_duration_invalid", f"Ref2VA {kind} 参考必须为每条 2-15 秒、累计不超过 15 秒。", path))
    ratios = profile.get("target_delivery_aspect_ratios")
    if not isinstance(ratios, list) or not ratios or any(not isinstance(value, str) or re.fullmatch(r"[1-9]\d*:[1-9]\d*", value) is None for value in ratios) or len(set(str(value) for value in ratios)) != len(ratios):
        issues.append(issue("error", "h3_target_delivery_ratios_invalid", "目标交付比例必须独立于 provider 请求能力登记为合法、无重复的比例列表。", path))
    if "deployment" in profile:
        issues.append(issue("error", "h3_provider_config_forbidden", "H3 模型能力档不得保存 provider、部署、网关或凭证配置。", path))


def check_manifest_examples(text: str, path: Path, issues: list[dict[str, Any]]) -> None:
    for match in re.finditer(r"```json\s*\n(.*?)\n```", text, flags=re.S):
        if '"generation_confirmations"' not in match.group(1):
            continue
        try:
            example = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            issues.append(issue("error", "skill_video_example_json_invalid", f"视频 manifest JSON 示例不能解析：{exc}", path))
            continue
        if not isinstance(example, dict) or not isinstance(example.get("segments"), list):
            continue
        example_issues: list[dict[str, Any]] = []
        check_video_generation_confirmations(example, example["segments"], path, example_issues)
        for segment in example["segments"]:
            if not isinstance(segment, dict):
                continue
            check_h3_duration(segment.get("duration_s"), path, "视频 manifest 示例", example_issues)
            check_h3_media_inputs(segment, path, example_issues)
            check_video_model(segment.get("model"), path, "视频 manifest 示例", example_issues)
            for kind, field in (("reference", "reference_inputs"), ("video", "video_inputs"), ("audio", "audio_inputs")):
                for item in segment.get(field, []) if isinstance(segment.get(field), list) else []:
                    if not isinstance(item, dict):
                        continue
                    for required in (("source_id", "file", "adopt", "exclude") if kind == "reference" else ("resource_id", "file", "adopt", "exclude")):
                        if not isinstance(item.get(required), str) or not item[required].strip():
                            example_issues.append(issue("error", f"{kind}_input_field_missing", f"{field} 示例缺少 {required}。", path))
        line_number = text.count("\n", 0, match.start()) + 1
        for example_issue in example_issues:
            issues.append(issue("error", "skill_example_" + example_issue["code"], f"第 {line_number} 行起的视频示例：{example_issue['message']}", path))


def check_skill_package(root: Path, issues: list[dict[str, Any]]) -> None:
    check_local_capability_profile(root, issues)
    for relative in ("tools/video.py", "tools/image.py", "tools/tts.py", "tools/media.py", "tools/video_run.py", "tools/video_run.example.json", "tools/workflow_series.py", "tools/workflow_video.py", "tools/lib/env.py", "tools/lib/media_facts.py", "tools/lib/json_state.py", "tools/lib/video_providers.py", "scripts/drama_rollback.py", "references/local-runtime.md", "references/crowds.md", "references/video-provider.md", "references/video-providers/autodl.md"):
        if not (root / relative).is_file():
            issues.append(issue("error", "local_runtime_file_missing", f"本地工作流缺少实际入口或依赖：{relative}", root / relative))
    python_paths = sorted([
        *root.glob("scripts/*.py"),
        *root.glob("tools/**/*.py"),
        *root.glob("tests/**/*.py"),
    ])
    for python_path in python_paths:
        try:
            source = python_path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source, filename=str(python_path))
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type == tokenize.COMMENT:
                    issues.append(issue(
                        "error", "local_python_comment_forbidden",
                        f"Python 脚本不得包含代码注释：第 {token.start[0]} 行。", python_path))
                    break
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and ast.get_docstring(node, clean=False) is not None:
                    issues.append(issue(
                        "error", "local_python_docstring_forbidden",
                        f"Python 脚本不得包含文档字符串：第 {node.lineno} 行。", python_path))
        except (OSError, UnicodeError, SyntaxError, tokenize.TokenError) as exc:
            issues.append(issue("error", "local_python_invalid", f"本地 Python 入口无法读取或解析：{exc}", python_path))
    skill_path = root / "SKILL.md"
    try:
        text = skill_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        issues.append(issue("error", "skill_file_missing", "Skill 根目录缺少 SKILL.md。", skill_path))
        return
    except (OSError, UnicodeError) as exc:
        issues.append(issue("error", "skill_file_unreadable", f"SKILL.md 无法读取：{exc}", skill_path))
        return

    frontmatter = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if frontmatter is None:
        issues.append(issue("error", "skill_frontmatter_missing", "SKILL.md 缺少合法的 YAML frontmatter。", skill_path))
        return
    fields: dict[str, str] = {}
    for line in frontmatter.group(1).splitlines():
        match = re.fullmatch(r"([a-z_]+):\s*(.*)", line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
    name = fields.get("name", "")
    description = fields.get("description", "")
    if not 2 <= len(name) <= 64 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        issues.append(issue("error", "skill_name_invalid", "Skill name 必须是 2-64 位小写字母、数字或单连字符。", skill_path))
    if name != root.name:
        issues.append(issue("error", "skill_name_path_mismatch", "Skill name 必须与目录名一致。", skill_path))
    if not description or description[:1] in {'"', "'"} or description[-1:] in {'"', "'"}:
        issues.append(issue("error", "skill_description_invalid", "Skill description 必须是非空、未加引号的单行标量。", skill_path))
    if ": " in description or "<" in description or ">" in description or "TODO" in description:
        issues.append(issue("error", "skill_description_forbidden_text", "Skill description 含禁止的格式或占位内容。", skill_path))
    if not text[frontmatter.end():].strip():
        issues.append(issue("error", "skill_body_empty", "SKILL.md 正文不能为空。", skill_path))

    referenced_paths = set(re.findall(r"`((?:references|scripts)/[^`\s]+?\.(?:md|py))`", text))
    for relative in sorted(referenced_paths):

        if re.search(r"<[^<>]+>", relative):
            continue
        target = root / relative
        if not target.is_file():
            issues.append(issue("error", "skill_reference_missing", f"SKILL.md 引用的本地文件不存在：{relative}", skill_path))

    markdown_paths = [
        path
        for path in sorted(root.glob("references/**/*.md"))
        if "references/cli" not in path.as_posix()
    ] + [skill_path]
    for markdown_path in markdown_paths:
        try:
            markdown_text = markdown_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            issues.append(issue("error", "markdown_file_unreadable", f"Markdown 文件无法读取：{exc}", markdown_path))
            continue
        check_manifest_examples(markdown_text, markdown_path, issues)
        for match in re.finditer(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)", markdown_text):
            raw_target = match.group(1).strip()
            if not raw_target or raw_target.startswith(("#", "http://", "https://", "mailto:", "app://", "codex://")):
                continue
            if " " in raw_target and not (raw_target.startswith("<") and raw_target.endswith(">")):
                raw_target = raw_target.split()[0]
            raw_target = raw_target.strip("<>")
            path_part = raw_target.split("#", 1)[0].split("?", 1)[0]
            if not path_part:
                continue
            target = markdown_path.parent / unquote(path_part)
            if not target.exists():
                issues.append(issue("error", "markdown_link_missing", f"Markdown 相对链接不存在：{raw_target}", markdown_path))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Focused drama workflow validator.")
    parser.add_argument("skill_root", nargs="?", default=".")
    parser.add_argument("--project-root")
    parser.add_argument("--stage", choices=("skill", *STAGES, "all"), default="skill")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    project_root = Path(args.project_root).resolve() if args.project_root else Path(args.skill_root).resolve()
    issues: list[dict[str, Any]] = []

    if args.stage == "skill":
        check_skill_package(project_root, issues)
        issues = dedupe_issues(issues)
        error_count = sum(1 for item in issues if item["level"] == "error")
        payload = {
            "summary": {
                "error_count": error_count,
                "warning_count": sum(1 for item in issues if item["level"] == "warning"),
                "scope": args.stage,
            },
            "release_ready": error_count == 0,
            "issues": issues,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if error_count else 0

    plan = load_json(project_root / "00_制作控制/drama_plan.json", issues, required=False)
    expected_episodes = check_plan_durations(project_root, plan, issues)
    lightweight = is_lightweight_plan(plan) and lightweight_constraints_valid(plan)
    check_episode_directories(project_root, expected_episodes, issues)
    check_episode_entry_manifests(project_root, issues, lightweight)
    check_state(project_root, plan, issues)
    check_operation_log_tools(project_root, issues)

    state = load_json(project_root / "00_制作控制/制作状态.json", issues, required=False)
    active_episode = state.get("current_episode") if isinstance(state, dict) else None
    stages_to_check = STAGES if args.stage == "all" else (args.stage,)
    for stage in stages_to_check:
        episode_filter = active_episode if args.stage != "all" and stage in EPISODE_STAGES else None
        check_stage_artifacts(project_root, stage, issues, episode_filter, lightweight)
        if stage in EPISODE_STAGES:
            check_episode_manifest_ids(project_root, stage, issues, episode_filter)
    episode_filter = active_episode if args.stage != "all" and args.stage in EPISODE_STAGES else None
    asset_index = blank_asset_index()
    if args.stage in {"assets", "storyboard", "keyframes", "video", "final", "all"}:
        asset_index = check_assets(project_root, issues, episode_filter)
    if args.stage in {"script", "assets", "storyboard", "keyframes", "video", "final", "all"}:
        check_project_crowds(project_root, plan, asset_index, issues, episode_filter, storyboard=args.stage in {"storyboard", "keyframes", "video", "final", "all"}, video=args.stage in {"video", "final", "all"})
    if args.stage in {"storyboard", "keyframes", "video", "final", "all"}:
        check_storyboards(project_root, expected_episodes, plan, issues, episode_filter)
    if args.stage in {"keyframes", "video", "final", "all"}:
        check_keyframes(project_root, asset_index, issues, episode_filter)
    if args.stage in {"video", "final", "all"}:
        check_video(
            project_root,
            asset_index,
            plan,
            issues,
            episode_filter,
            require_accepted=args.stage in {"final", "all"} and not lightweight,
        )
    if args.stage in {"final", "all"}:
        check_delivery(project_root, expected_episodes, issues, episode_filter, lightweight)

    issues = dedupe_issues(issues)
    error_count = sum(1 for item in issues if item["level"] == "error")
    payload = {
        "summary": {
            "error_count": error_count,
            "warning_count": sum(1 for item in issues if item["level"] == "warning"),
            "scope": args.stage,
        },
        "release_ready": error_count == 0,
        "issues": issues,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if error_count else 0


if __name__ == "__main__":
    sys.exit(main())
