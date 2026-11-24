from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Any


class Stage(str, Enum):
    PLANNING = "planning"
    SCRIPT = "script"
    ASSETS = "assets"
    STORYBOARD = "storyboard"
    KEYFRAMES = "keyframes"
    VIDEO = "video"
    FINAL = "final"


class PhaseStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    MERGED = "merged"
    INVALIDATED = "invalidated"
    BLOCKED = "blocked"


class WorkflowMode(str, Enum):
    FULL = "full"
    LIGHTWEIGHT = "lightweight"


STAGES = tuple(stage.value for stage in Stage)
EPISODE_STAGES = set(STAGES[1:])
STATUS_VALUES = {status.value for status in PhaseStatus}
MERGEABLE_LIGHTWEIGHT_STAGES = {
    Stage.SCRIPT.value,
    Stage.ASSETS.value,
    Stage.STORYBOARD.value,
    Stage.KEYFRAMES.value,
    Stage.VIDEO.value,
}
CURRENT_STAGE_ACTIVE_VALUES = {
    PhaseStatus.IN_PROGRESS.value,
    PhaseStatus.AWAITING_CONFIRMATION.value,
    PhaseStatus.INVALIDATED.value,
    PhaseStatus.BLOCKED.value,
}

H3_PROFILE = json.loads((Path(__file__).resolve().parents[1] / "tools/h3.json").read_text(encoding="utf-8"))
H3_MODEL = H3_PROFILE["model"]
H3_CAPABILITIES = H3_PROFILE["capabilities"]
H3_MODES = set(H3_CAPABILITIES["modes"])
ISO_TIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")
EPISODE_ID_PATTERN = re.compile(r"ep_[1-9]\d*")
REFERENCE_ROLES = {
    "first_frame",
    "last_frame",
    "previous_tail_as_start_frame",
    "previous_tail_reference",
    "previous_scene_anchor_reference",
    "previous_character_state_reference",
    "previous_prop_state_reference",
    "segment_highlight_reference",
    "identity_reference",
    "character_state_reference",
    "face_anchor_reference",
    "scene_layout",
    "scene_state_reference",
    "prop_structure",
    "prop_state_reference",
    "style_reference",
    "crowd_reference",
    "repair_reference",
    "video_input_reference",
}
VIDEO_INPUT_ROLES = {
    "previous_segment_video_reference",
    "style_video_reference",
    "character_video_reference",
    "scene_video_reference",
    "source_video_for_edit",
}
AUDIO_INPUT_ROLES = {
    "voice_audio_reference",
    "music_reference",
    "sound_effect_reference",
    "ambient_reference",
}
STATE_REFERENCE_ROLES = {"character_state_reference", "prop_state_reference", "scene_state_reference"}
FRAME_REFERENCE_POSITIONS = {"first_frame": "first", "last_frame": "last", "previous_tail_as_start_frame": "first"}
IMAGE_INPUT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

SPEECH_IGNORED_PUNCTUATION = frozenset("。？！….!?，、；：,;:—“”‘’\"'《》〈〉（）()")


def issue(level: str, code: str, message: str, path: Path | None = None, hint: str = "") -> dict[str, Any]:
    data: dict[str, Any] = {"level": level, "code": code, "message": message, "hint": hint}
    if path is not None:
        data["path"] = str(path)
    return data


def load_json(path: Path, issues: list[dict[str, Any]], required: bool = True) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if required:
            issues.append(issue("error", "file_missing", "缺少流程所需文件。", path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        issues.append(issue("error", "json_invalid", f"JSON 无法读取或解析，后续关系无法确认：{exc}", path))
    return None


def relative_file(root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    try:
        target = (root / rel).resolve()
        target.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return target


def file_exists(root: Path, value: Any) -> bool:
    target = relative_file(root, value)
    return target is not None and target.is_file()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nonempty_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def has_meaningful_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(has_meaningful_value(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and any(has_meaningful_value(item) for item in value.values())
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    return False


def combined_strings(*owners: Any, field: str) -> list[str]:
    values: list[str] = []
    for owner in owners:
        if isinstance(owner, dict):
            values.extend(nonempty_strings(owner.get(field)))
    return values


def check_unique(items: list[Any], field: str, path: Path, issues: list[dict[str, Any]], scope: str) -> set[str]:
    seen: set[str] = set()
    values: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(issue("error", f"{field}_missing", f"{scope} 缺少 {field}。", path))
            continue
        if value in seen:
            issues.append(issue("error", f"{field}_duplicate", f"{scope} 中 {field} 重复：{value}", path))
        seen.add(value)
        values.add(value)
    return values


def parse_iso_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not ISO_TIME_PATTERN.fullmatch(text):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def h3_duration_valid(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    if H3_CAPABILITIES.get("duration_integer_only") and not isinstance(value, int):
        return False
    return H3_CAPABILITIES["min_duration_s"] <= value <= H3_CAPABILITIES["max_duration_s"]


def check_video_model(value: Any, path: Path, label: str, issues: list[dict[str, Any]]) -> None:
    if not isinstance(value, str) or value.strip().casefold() != H3_MODEL.casefold():
        issues.append(issue("error", "video_model_unavailable", f"{label} 视频模型必须为当前唯一可用的 {H3_MODEL}。", path))


def check_declared_video_models(owner: Any, path: Path, label: str, issues: list[dict[str, Any]]) -> None:
    if not isinstance(owner, dict):
        return
    for field in ("video_model", "model", "model_name", "selected_model"):
        if field in owner:
            check_video_model(owner[field], path, f"{label}.{field}", issues)


def check_h3_duration(value: Any, path: Path, label: str, issues: list[dict[str, Any]]) -> None:
    if not h3_duration_valid(value):
        issues.append(issue("error", "h3_segment_duration_invalid", f"{label} duration_s 必须为 H3 能力档规定的 {H3_CAPABILITIES['min_duration_s']}-{H3_CAPABILITIES['max_duration_s']} 整数秒。", path))


def marker_pattern(kind: str, order: int) -> str:
    patterns = {
        "image": rf"<(?:图片\s*{order}(?:\s*-\s*第\s*\d+\s*格)?|IMG\s*{order}(?:\s*-\s*Cell\s*\d+)?|Picture\s*{order})\s*>",
        "video": rf"<(?:视频|VID|Video)\s*{order}\s*>",
        "audio": rf"<(?:音频|AUD|Audio)\s*{order}\s*>",
    }
    return patterns[kind]


def normalized_speech(text: str) -> str:
    return "".join(character for character in text if not character.isspace() and character not in SPEECH_IGNORED_PUNCTUATION)


def markdown_table_column_counts(text: str) -> list[int]:
    counts: list[int] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped[1:-1].split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            counts.append(len(cells))
    return counts


@dataclass(frozen=True)
class ProductionPlan:


    raw: Any

    @property
    def objective(self) -> Any:
        return self.raw.get("objective") if isinstance(self.raw, dict) else None

    @property
    def target(self) -> str | None:
        value = self.objective.get("target_stage") if isinstance(self.objective, dict) else None
        return value if value in STAGES else None

    @property
    def has_valid_target(self) -> bool:
        return isinstance(self.objective, dict) and self.objective.get("target_stage") in STAGES

    @property
    def is_lightweight(self) -> bool:
        return isinstance(self.objective, dict) and self.objective.get("workflow_mode") == WorkflowMode.LIGHTWEIGHT.value

    @property
    def lightweight_constraints_valid(self) -> bool:
        if not isinstance(self.raw, dict):
            return False
        scale = self.raw.get("scale_plan") if isinstance(self.raw.get("scale_plan"), dict) else {}
        count = scale.get("episode_count")
        total = scale.get("total_duration_s")
        if not isinstance(count, int) or isinstance(count, bool) or count != 1:
            return False
        return h3_duration_valid(total)

    @property
    def lightweight_valid(self) -> bool:
        return self.is_lightweight and self.lightweight_constraints_valid

    def revision(self, state: dict[str, Any]) -> int | None:
        plan = self.raw if isinstance(self.raw, dict) else {}
        for source in (state, plan):
            value = source.get("revision") if isinstance(source, dict) else None
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None


def plan_revision(plan: Any, state: dict[str, Any]) -> int | None:
    return ProductionPlan(plan).revision(state)


def is_lightweight_plan(plan: Any) -> bool:
    return ProductionPlan(plan).is_lightweight


def lightweight_constraints_valid(plan: Any) -> bool:
    return ProductionPlan(plan).lightweight_constraints_valid


def target_stage(plan: Any) -> str | None:
    return ProductionPlan(plan).target


def episode_dirs(root: Path, episode_filter: str | None = None) -> list[tuple[str, Path]]:
    episodes_root = root / "episodes"
    if not episodes_root.is_dir():
        return []
    entries = [
        (child.name, child)
        for child in episodes_root.iterdir()
        if child.is_dir() and EPISODE_ID_PATTERN.fullmatch(child.name)
        and (episode_filter is None or child.name == episode_filter)
    ]
    return sorted(entries, key=lambda item: int(item[0].split("_", 1)[1]))
