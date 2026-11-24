from __future__ import annotations

from enum import Enum
from pathlib import Path
import re
from typing import Any

if __package__:
    from .drama_lint_domain import (
        file_sha256,
        issue,
        marker_pattern,
        normalized_speech,
        parse_iso_time,
    )
else:
    from drama_lint_domain import (
        file_sha256,
        issue,
        marker_pattern,
        normalized_speech,
        parse_iso_time,
    )


class H3PromptMode(str, Enum):
    T2VA = "T2VA"
    I2VA = "I2VA"
    FL2VA = "FL2VA"
    L2VA = "L2VA"
    REF2VA = "Ref2VA"


H3_BASE_FIELDS = (
    "integrated_multimodal_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)
H3_REF2VA_FIELDS = (
    "subject_definitions:",
    "summary:",
    "retention_analysis:",
    "detailed_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)
H3_OPENING_INSTRUCTIONS = {
    H3PromptMode.I2VA.value: (
        "For the target video",
        "I2VA 成稿首行必须是 For the target video 首帧对齐指令。",
    ),
    H3PromptMode.FL2VA.value: (
        "How the reference pictures align",
        "FL2VA 成稿首行必须是 How the reference pictures align 画面对齐指令。",
    ),
    H3PromptMode.L2VA.value: (
        "How the reference pictures align",
        "L2VA 成稿首行必须是 How the reference pictures align 画面对齐指令。",
    ),
}
CN_MEDIA_MARKER_PATTERN = re.compile(r"<\s*(?:图片|视频|音频|主体)\s*\d+")
H3_MARKER_PATTERNS = {
    "image": r"<\s*Picture\s*(\d+)\s*>",
    "video": r"<\s*Video\s*(\d+)\s*>",
    "audio": r"<\s*Audio\s*(\d+)\s*>",
}


def extract_marker_orders(text: str, kind: str) -> list[int]:
    if kind == "image":
        pattern = r"<(?:图片\s*(\d+)(?:\s*-\s*第\s*\d+\s*格)?|IMG\s*(\d+)(?:\s*-\s*Cell\s*\d+)?|Picture\s*(\d+))\s*>"
        orders: list[int] = []
        for groups in re.findall(pattern, text, flags=re.I):
            orders.append(int(next(order for order in groups if order)))
        return orders
    patterns = {
        "video": r"<(?:视频|VID|Video)\s*(\d+)\s*>",
        "audio": r"<(?:音频|AUD|Audio)\s*(\d+)\s*>",
    }
    return [int(match) for match in re.findall(patterns[kind], text, flags=re.I)]


def extract_h3_marker_orders(text: str, kind: str) -> list[int]:
    return [int(match) for match in re.findall(H3_MARKER_PATTERNS[kind], text, flags=re.I)]


def extract_subject_marker_orders(text: str) -> set[int]:
    orders: set[int] = set()
    pattern = r"<(?:主体\s*(\d+)|SUBJ\s*(\d+))\s*>"
    for cn_order, en_order in re.findall(pattern, text, flags=re.I):
        orders.add(int(cn_order or en_order))
    return orders


def _read_prompt_text(prompt_path: Path, issues: list[dict[str, Any]]) -> str | None:
    if not prompt_path.is_file():
        issues.append(issue("error", "prompt_missing", "Prompt 文件不存在。", prompt_path))
        return None
    try:
        return prompt_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        issues.append(issue("error", "prompt_unreadable", f"Prompt 无法读取：{exc}", prompt_path))
        return None


def _check_draft_slot_markers(
    text: str,
    image_orders: list[int],
    video_orders: list[int],
    audio_orders: list[int],
    prompt_path: Path,
    issues: list[dict[str, Any]],
) -> None:
    expected_by_kind = {"image": sorted(image_orders), "video": sorted(video_orders), "audio": sorted(audio_orders)}
    for kind, expected in expected_by_kind.items():
        actual = sorted(set(extract_marker_orders(text, kind)))
        label = {"image": "图片", "video": "视频", "audio": "音频"}[kind]
        if actual != expected:
            issues.append(issue("error", f"prompt_{kind}_markers_mismatch", f"Prompt 中{label}标记 {actual} 必须与实际输入 order {expected} 一致。", prompt_path))
        for order in expected:
            if re.search(marker_pattern(kind, order), text, flags=re.I) is None:
                issues.append(issue("error", f"prompt_{kind}_marker_missing", f"Prompt 缺少第 {order} 个{label}标记。", prompt_path))


STRUCTURED_DRAFT_HEADINGS = (
    "integrated_multimodal_description",
    "overall_soundscape",
    "non_diegetic_music",
    "dialogue_refs",
)


def _structured_draft(text: str) -> tuple[bool, list[str]] | None:
    headings = list(re.finditer(r"(?m)^##[ \t]+([a-z_]+)[ \t]*$", text))
    if not headings:
        return None
    names = tuple(match.group(1) for match in headings)
    valid = bool(text[:headings[0].start()].strip()) and names == STRUCTURED_DRAFT_HEADINGS
    dialogue = re.search(
        r"(?ms)^##[ \t]+dialogue_refs[ \t]*\r?\n(.*?)(?=^##[ \t]+|\Z)",
        text,
    )
    spoken_texts: list[str] = []
    if dialogue is not None:
        lines = dialogue.group(1).splitlines()
        for header_index, line in enumerate(lines):
            if not line.strip().startswith("|"):
                continue
            headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if "spoken_text" not in headers:
                continue
            spoken_index = headers.index("spoken_text")
            for row in lines[header_index + 1:]:
                if not row.strip().startswith("|"):
                    break
                cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
                if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
                    continue
                if len(cells) > spoken_index and cells[spoken_index]:
                    spoken_texts.append(cells[spoken_index])
            break
    return valid, spoken_texts


def check_director_draft_prompt(
    draft_path: Path,
    image_orders: list[int],
    video_orders: list[int],
    audio_orders: list[int],
    speech_lines: Any,
    subtitle_enabled: bool,
    issues: list[dict[str, Any]],
) -> None:

    text = _read_prompt_text(draft_path, issues)
    if text is None:
        return
    structured = _structured_draft(text)
    if structured is None:
        paragraph_count = len([block for block in re.split(r"\n\s*\n", text.strip()) if block.strip()])
        if paragraph_count != 5:
            issues.append(issue("error", "prompt_five_sections_invalid", f"导演编译底稿必须恰好包含 5 个按空行分隔的信息段，当前为 {paragraph_count} 段。", draft_path))
    elif not structured[0]:
        issues.append(issue("error", "prompt_five_sections_invalid", "结构化导演编译底稿必须保留非空前置段，并按 integrated_multimodal_description、overall_soundscape、non_diegetic_music、dialogue_refs 的顺序恰好使用四个二级标题。", draft_path))
    if CN_MEDIA_MARKER_PATTERN.search(text) and any(
            re.search(pattern, text, flags=re.I) for pattern in H3_MARKER_PATTERNS.values()):
        issues.append(issue("error", "prompt_marker_language_mixed", "导演编译底稿使用中文多媒体标记，不要混入 H3 的 <Picture N>/<Video N>/<Audio N> 标记。", draft_path))
    _check_draft_slot_markers(text, image_orders, video_orders, audio_orders, draft_path, issues)
    cn = re.search(r"<(?:图片\s*\d+(?:\s*-\s*第\s*\d+\s*格)?|视频\s*\d+|音频\s*\d+|主体\s*\d+)\s*>", text)
    en = re.search(r"<(?:IMG\s*\d+(?:\s*-\s*Cell\s*\d+)?|VID\s*\d+|AUD\s*\d+|SUBJ\s*\d+)\s*>", text, flags=re.I)
    if cn and en:
        issues.append(issue("error", "prompt_marker_language_mixed", "同一 Prompt 不要混用中文和英文多媒体标记。", draft_path))
    for order in sorted(extract_subject_marker_orders(text)):
        cn_labeled = rf"<\s*主体\s*{order}\s*>\s*[（(][^（）()\n]+[）)]"
        en_labeled = rf"<\s*SUBJ\s*{order}\s*>\s*[（(][^（）()\n]+[）)]"
        if not re.search(cn_labeled, text) and not re.search(en_labeled, text, flags=re.I):
            issues.append(issue("error", "prompt_subject_marker_label_missing", f"Prompt 使用 <主体{order}>/<SUBJ{order}> 时，必须至少一次写成 <主体{order}>(名称) 或 <SUBJ{order}>(name) 绑定主体身份。", draft_path))
    if ("【" in text or "】" in text) and not subtitle_enabled:
        issues.append(issue("error", "prompt_subtitle_bracket_invalid", "未启用字幕时，导演编译底稿不允许出现【】字幕源标识。", draft_path))
    expected_speech: set[str] = set()
    expected_order: list[str] = []
    if isinstance(speech_lines, list):
        for index, line in enumerate(speech_lines, start=1):
            if not isinstance(line, dict):
                issues.append(issue("error", "speech_line_invalid", f"speech_lines 第 {index} 条必须是对象。", draft_path))
                continue
            spoken = str(line.get("spoken_text") or "").strip()
            if not spoken:
                issues.append(issue("error", "speech_line_spoken_text_missing", f"speech_lines 第 {index} 条缺少 spoken_text。", draft_path))
                continue
            expected_speech.add(spoken)
            expected_order.append(spoken)
            if structured is None and f"{{{spoken}}}" not in text:
                issues.append(issue("error", "prompt_speech_line_missing", f"导演编译底稿缺少当前 SEG 台词：{{{spoken}}}", draft_path))
    if structured is not None:
        actual_speech = structured[1]
        for spoken in expected_order:
            if spoken not in actual_speech:
                issues.append(issue("error", "prompt_speech_line_missing", f"导演编译底稿 dialogue_refs 缺少当前 SEG 台词：{spoken}", draft_path))
        extras = sorted(set(actual_speech) - expected_speech)
        if extras:
            issues.append(issue("error", "prompt_speech_line_extra", f"dialogue_refs.spoken_text 只能包含当前 SEG 台词，发现额外内容：{extras[:5]}", draft_path))
        return
    prompt_braces = {match.strip() for match in re.findall(r"\{([^{}\n]+)\}", text) if match.strip()}
    if expected_speech:
        extras = sorted(prompt_braces - expected_speech)
        if extras:
            issues.append(issue("error", "prompt_speech_line_extra", f"底稿中 {{}} 只能包裹当前 SEG 的 spoken_text，发现额外内容：{extras[:5]}", draft_path))
    elif prompt_braces:
        issues.append(issue("error", "prompt_speech_line_unplanned", "底稿中出现花括号台词标记，但当前 SEG 未登记 speech_lines。", draft_path))


def check_h3_final_prompt(
    prompt_path: Path,
    h3_mode: str,
    image_orders: list[int],
    video_orders: list[int],
    audio_orders: list[int],
    speech_lines: Any,
    subtitle_enabled: bool,
    issues: list[dict[str, Any]],
) -> None:

    text = _read_prompt_text(prompt_path, issues)
    if text is None:
        return
    required_fields = H3_REF2VA_FIELDS if h3_mode == H3PromptMode.REF2VA.value else H3_BASE_FIELDS
    for field in required_fields:
        if field not in text:
            issues.append(issue("error", "h3_prompt_field_missing", f"H3 成稿缺少固定字段 {field}（h3_mode={h3_mode or '未登记'}）。", prompt_path))
    opening_instruction = H3_OPENING_INSTRUCTIONS.get(h3_mode)
    if opening_instruction is not None and opening_instruction[0] not in text:
        issues.append(issue("error", "h3_prompt_instruction_missing", opening_instruction[1], prompt_path))
    if CN_MEDIA_MARKER_PATTERN.search(text):
        issues.append(issue("error", "h3_prompt_chinese_marker", "H3 成稿必须使用 <Picture N>/<Video N>/<Audio N> 标记，不得出现中文 <图片N>/<视频N>/<音频N>/<主体N> 标记。", prompt_path))
    expected_by_kind = {"image": sorted(image_orders), "video": sorted(video_orders), "audio": sorted(audio_orders)}
    for kind, expected in expected_by_kind.items():
        actual = sorted(set(extract_h3_marker_orders(text, kind)))
        label = {"image": "Picture", "video": "Video", "audio": "Audio"}[kind]
        if actual != expected:
            issues.append(issue("error", f"prompt_{kind}_markers_mismatch", f"H3 成稿中 {label} 标记 {actual} 必须与实际输入 order {expected} 一致。", prompt_path))
    if ("【" in text or "】" in text) and not subtitle_enabled:
        issues.append(issue("error", "prompt_subtitle_bracket_invalid", "未启用字幕时，H3 成稿不允许出现【】字幕源标识。", prompt_path))
    expected_speech: list[str] = []
    if isinstance(speech_lines, list):
        for index, line in enumerate(speech_lines, start=1):
            if not isinstance(line, dict):
                issues.append(issue("error", "speech_line_invalid", f"speech_lines 第 {index} 条必须是对象。", prompt_path))
                continue
            spoken = str(line.get("spoken_text") or "").strip()
            if not spoken:
                issues.append(issue("error", "speech_line_spoken_text_missing", f"speech_lines 第 {index} 条缺少 spoken_text。", prompt_path))
                continue
            expected_speech.append(spoken)
    d_blocks = re.findall(r"<\s*d\s*>(.*?)<\s*/\s*d\s*>", text, flags=re.S | re.I)
    opening_tags = re.findall(r"<\s*d\s*>", text, flags=re.I)
    closing_tags = re.findall(r"<\s*/\s*d\s*>", text, flags=re.I)
    if len(opening_tags) != len(d_blocks) or len(closing_tags) != len(d_blocks):
        issues.append(issue("error", "h3_prompt_dialog_tags_invalid", "H3 台词 <d></d> 必须完整配对，不能嵌套。", prompt_path))
    if expected_speech:
        if len(d_blocks) != len(expected_speech):
            issues.append(issue("error", "h3_prompt_dialog_block_count", f"H3 成稿 <d></d> 台词块数量 {len(d_blocks)} 必须等于 speech_lines 条数 {len(expected_speech)}（每条台词一个块）。", prompt_path))
        for index, (spoken, block) in enumerate(zip(expected_speech, d_blocks), start=1):
            language_tag = re.match(r"\s*\[[^\]\r\n]+\]\s*", block)
            if language_tag is None:
                issues.append(issue("error", "h3_prompt_dialog_language_missing", f"第 {index} 个 <d> 块必须以 [语言] 标签开头。", prompt_path))
                actual = block
            else:
                actual = block[language_tag.end():]
            actual = re.sub(r"<\s*/?\s*(?:scenetrans|cutoff)\s*>", "", actual, flags=re.I)
            if normalized_speech(actual) != normalized_speech(spoken):
                issues.append(issue("error", "prompt_speech_line_missing", f"第 {index} 个 <d> 块必须一对一对应第 {index} 条 speech_lines；只允许合同规定的标点、引号与空白差异：{spoken}", prompt_path))
    elif d_blocks:
        issues.append(issue("error", "prompt_speech_line_unplanned", "H3 成稿出现 <d></d> 台词块，但当前 SEG 未登记 speech_lines。", prompt_path))


def check_prompt_preflight(segment: dict[str, Any], expected_shot_ids: list[str], path: Path, issues: list[dict[str, Any]]) -> None:
    label = str(segment.get("segment_id") or "segment")
    preflight = segment.get("prompt_preflight")
    if not isinstance(preflight, dict):
        issues.append(issue("error", "prompt_preflight_missing", f"{label} 必须登记一次集中 Prompt 预检和一次最终客观校验。", path))
        return
    if preflight.get("review_count") != 1:
        issues.append(issue("error", "prompt_preflight_review_count_invalid", f"{label} prompt_preflight.review_count 必须为 1。", path))
    revision_count = preflight.get("revision_count")
    if revision_count not in {0, 1}:
        issues.append(issue("error", "prompt_preflight_revision_count_invalid", f"{label} Prompt 集中修订最多 1 次。", path))
    if preflight.get("final_validation_count") != 1:
        issues.append(issue("error", "prompt_final_validation_count_invalid", f"{label} prompt_preflight.final_validation_count 必须为 1。", path))
    if preflight.get("five_sections_in_order") is not True:
        issues.append(issue("error", "prompt_five_sections_not_verified", f"{label} 必须确认中文五段式导演编译底稿顺序完整。", path))
    if preflight.get("h3_structure_verified") is not True:
        issues.append(issue("error", "prompt_h3_structure_not_verified", f"{label} 必须确认 h3-prompt-writing 成稿字段、标记与台词合同通过客观校验。", path))
    compiled_once = preflight.get("shot_ids_compiled_once")
    if not isinstance(compiled_once, list) or compiled_once != expected_shot_ids or len(set(compiled_once)) != len(compiled_once):
        issues.append(issue("error", "prompt_shot_preflight_mismatch", f"{label} shot_ids_compiled_once 必须按分镜顺序恰好列出每个镜头一次。", path))
    if preflight.get("result") != "passed":
        issues.append(issue("error", "prompt_preflight_not_passed", f"{label} 最终客观校验必须通过后才能生成。", path))


def check_h3_skill_conversion(
    root: Path,
    segment: dict[str, Any],
    draft_path: Path | None,
    prompt_path: Path | None,
    path: Path,
    issues: list[dict[str, Any]],
) -> None:
    label = str(segment.get("segment_id") or "segment")
    conversion = segment.get("h3_conversion")
    if not isinstance(conversion, dict):
        issues.append(issue("error", "h3_conversion_missing", f"{label} 必须登记真实 h3-prompt-writing Skill 转换血缘。", path))
        return
    if (
        conversion.get("skill_name") != "h3-prompt-writing"
        or conversion.get("invocation_channel") != "host_skill_tool"
        or conversion.get("invoked") is not True
    ):
        issues.append(issue("error", "h3_skill_invocation_missing", f"{label} 必须由主 Agent 通过宿主 Skill 工具真实调用 h3-prompt-writing；阅读文档或手写同格式文本不算转换。", path))
    if parse_iso_time(conversion.get("converted_at")) is None:
        issues.append(issue("error", "h3_conversion_time_invalid", f"{label} h3_conversion.converted_at 必须是带时区 ISO-8601 时间。", path))
    hashes: dict[str, str] = {}
    for field in ("source_draft_sha256", "compiled_prompt_sha256"):
        value = str(conversion.get(field) or "").strip()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            issues.append(issue("error", "h3_conversion_hash_invalid", f"{label} h3_conversion.{field} 必须是 64 位小写 SHA-256。", path))
        else:
            hashes[field] = value
    source_hash = hashes.get("source_draft_sha256")
    if draft_path is None or not draft_path.is_file():
        issues.append(issue("error", "h3_conversion_source_missing", f"{label} 真实 Skill 转换必须绑定存在的 director_draft_file。", path))
    elif source_hash:
        try:
            actual_hash = file_sha256(draft_path)
        except OSError as exc:
            issues.append(issue("error", "h3_conversion_source_unreadable", f"无法读取导演底稿计算 sha256：{exc}", draft_path))
        else:
            if actual_hash != source_hash:
                issues.append(issue("error", "h3_conversion_source_hash_mismatch", f"{label} 源底稿已在转换后改变，必须重新真实调用 h3-prompt-writing。", draft_path))
    compiled_hash = hashes.get("compiled_prompt_sha256")
    if prompt_path is None or not prompt_path.is_file():
        issues.append(issue("error", "h3_conversion_compiled_prompt_missing", f"{label} 真实 Skill 转换必须绑定存在的 compiled_prompt_file。", path))
    elif compiled_hash:
        try:
            actual_hash = file_sha256(prompt_path)
        except OSError as exc:
            issues.append(issue("error", "h3_conversion_compiled_prompt_unreadable", f"无法读取 H3 成稿计算 sha256：{exc}", prompt_path))
        else:
            if actual_hash != compiled_hash:
                issues.append(issue("error", "h3_conversion_compiled_hash_mismatch", f"{label} H3 成稿与 Skill 转换记录不一致，禁止提交模型。", prompt_path))
    prompt_hash = str(segment.get("prompt_sha256") or "").strip()
    if compiled_hash and prompt_hash and compiled_hash != prompt_hash:
        issues.append(issue("error", "h3_conversion_prompt_hash_mismatch", f"{label} h3_conversion.compiled_prompt_sha256 必须等于实际提交文本的 prompt_sha256。", path))
