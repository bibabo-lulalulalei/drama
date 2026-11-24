from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Any

if __package__:
    from .drama_lint_domain import (
        combined_strings,
        episode_dirs,
        file_exists,
        issue,
        load_json,
        relative_file,
    )
else:
    from drama_lint_domain import (
        combined_strings,
        episode_dirs,
        file_exists,
        issue,
        load_json,
        relative_file,
    )


class AssetStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class VisualReferenceDecision(str, Enum):
    USED = "used"
    NONE_AVAILABLE = "none_available"
    EXPLICIT_USER_OVERRIDE = "explicit_user_override"


class ProjectVisualMode(str, Enum):
    LIVE_ACTION = "live_action"
    PHOTOREAL = "photoreal"
    COMIC_2D = "2d_comic"
    ANIME = "anime"
    INK_ANIMATION = "ink_animation"
    ILLUSTRATION = "illustration"
    STYLIZED_3D = "stylized_3d"
    MIXED_WITH_EXPLICIT_SCOPE = "mixed_with_explicit_scope"


class AssetCategory(str, Enum):
    CHARACTER = "character"
    SCENE = "scene"
    PROP = "prop"
    VOICE = "voice"
    STYLE = "style"
    CROWD = "crowd"


class AssetScope(str, Enum):
    SHARED = "shared"
    EPISODE = "episode"


class ImageGenerationRoute(str, Enum):
    IMAGE_GEN = "image_gen"
    IMAGE_EDIT = "image_edit"


ASSET_STATUS_VALUES = {status.value for status in AssetStatus}
VISUAL_REFERENCE_DECISIONS = {decision.value for decision in VisualReferenceDecision}
PROJECT_VISUAL_MODES = {mode.value for mode in ProjectVisualMode}
IMAGE_GENERATION_TOOLS = {route.value for route in ImageGenerationRoute}
VISUAL_ASSET_CATEGORIES = {
    AssetCategory.CHARACTER.value,
    AssetCategory.SCENE.value,
    AssetCategory.PROP.value,
    AssetCategory.STYLE.value,
    AssetCategory.CROWD.value,
}
ASSET_PREFIX_BY_CATEGORY = {
    AssetCategory.CHARACTER.value: "CHR",
    AssetCategory.SCENE.value: "SCN",
    AssetCategory.PROP.value: "PROP",
    AssetCategory.VOICE.value: "VOICE",
    AssetCategory.STYLE.value: "STYLE",
    AssetCategory.CROWD.value: "CRD",
}


def check_style_anchor_contract(
    root: Path,
    owner_path: Path,
    owner_label: str,
    tool: Any,
    prompt_path_value: Any,
    style_anchor_refs: list[str],
    terms: list[str],
    adopt: list[str],
    exclude: list[str],
    issues: list[dict[str, Any]],
    visual_reference_decision: Any = None,
) -> None:
    if not style_anchor_refs:
        return
    if tool != ImageGenerationRoute.IMAGE_EDIT.value:
        issues.append(issue("error", "style_anchor_requires_image_edit", f"{owner_label} 使用 style_anchor_reference 时必须走 image_edit。", owner_path))
    if visual_reference_decision == VisualReferenceDecision.NONE_AVAILABLE.value:
        issues.append(issue("error", "style_anchor_visual_reference_decision_conflict", f"{owner_label} 使用 style_anchor_reference 时 visual_reference_decision 不能写 none_available。", owner_path))
    if not terms:
        issues.append(issue("error", "style_prompt_terms_missing", f"{owner_label} 使用 style_anchor_reference 时 style_prompt_terms 必须是非空字符串数组。", owner_path))
    if not adopt:
        issues.append(issue("error", "style_adopt_missing", f"{owner_label} 使用 style_anchor_reference 时 style_adopt 必须是非空字符串数组。", owner_path))
    if not exclude:
        issues.append(issue("error", "style_exclude_missing", f"{owner_label} 使用 style_anchor_reference 时 style_exclude 必须是非空字符串数组。", owner_path))
    prompt_path = relative_file(root, prompt_path_value)
    if prompt_path is None:
        issues.append(issue("error", "style_prompt_path_missing", f"{owner_label} 使用 style_anchor_reference 时必须登记项目相对 prompt_path。", owner_path))
    elif not prompt_path.is_file():
        issues.append(issue("error", "style_prompt_file_missing", f"{owner_label} style_anchor_reference 对应 Prompt 文件不存在。", prompt_path))


def check_generation_prompt_file(
    root: Path,
    owner_path: Path,
    owner_label: str,
    tool: Any,
    prompt_path_value: Any,
    issues: list[dict[str, Any]],
) -> None:
    if tool not in IMAGE_GENERATION_TOOLS:
        return
    prompt_path = relative_file(root, prompt_path_value)
    if prompt_path is None:
        issues.append(issue("error", "generation_prompt_path_missing", f"{owner_label} 使用 {tool} 生成图片时必须登记项目相对 prompt_path。", owner_path))
    elif not prompt_path.is_file():
        issues.append(issue("error", "generation_prompt_file_missing", f"{owner_label} 生成图片 Prompt 文件不存在。", prompt_path))
    else:
        try:
            prompt_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            issues.append(issue("error", "generation_prompt_unreadable", f"{owner_label} 生成图片 Prompt 无法读取：{exc}", prompt_path))


def asset_version_key(asset_id: str, version: str, separator: str = "_") -> str:
    return f"{asset_id}{separator}{version}"


def version_rank(version: str) -> int:
    match = re.search(r"\d+", version)
    return int(match.group()) if match else -1


@dataclass(frozen=True)
class AssetVersionRef:
    asset_id: str
    version: str

    @classmethod
    def parse(cls, ref: Any) -> "AssetVersionRef | None":
        if not isinstance(ref, str):
            return None
        for separator in ("_", ":"):
            head, sep, tail = ref.rpartition(separator)
            if sep and head and re.fullmatch(r"v\d+", tail, flags=re.I):
                return cls(head, tail)
        return None

    def keys(self) -> set[str]:
        return {
            asset_version_key(self.asset_id, self.version, "_"),
            asset_version_key(self.asset_id, self.version, ":"),
        }


def split_asset_version_ref(ref: Any) -> tuple[str, str] | None:
    parsed = AssetVersionRef.parse(ref)
    return (parsed.asset_id, parsed.version) if parsed is not None else None


@dataclass(frozen=True)
class StateAssetRef:
    asset_id: str
    state_id: str
    version: str = ""

    def keys(self) -> set[str]:
        refs = {f"{self.asset_id}:{self.state_id}"}
        if self.version:
            refs.add(f"{self.asset_id}:{self.state_id}_{self.version}")
            refs.add(f"{self.asset_id}:{self.state_id}:{self.version}")
        return refs


def state_ref_keys(asset_id: str, state_id: str, version: str = "") -> set[str]:
    return StateAssetRef(asset_id, state_id, version).keys()


@dataclass
class AssetVersionIndex:


    data: dict[str, Any]

    @classmethod
    def blank(cls) -> "AssetVersionIndex":
        return cls({
            "known_asset_ids": set(),
            "known_version_refs": set(),
            "approved_version_refs": set(),
            "approved_versions_by_asset": {},
            "latest_approved_version": {},
            "known_state_refs": set(),
            "approved_state_refs": set(),
            "files_by_ref": {},
        })

    def remember_version(self, asset_id: str, version: str, status: Any) -> None:
        self.data["known_asset_ids"].add(asset_id)
        if not version:
            return
        ref = AssetVersionRef(asset_id, version)
        self.data["known_version_refs"].update(ref.keys())
        if status != AssetStatus.APPROVED.value:
            return
        self.data["approved_version_refs"].update(ref.keys())
        approved = self.data["approved_versions_by_asset"].setdefault(asset_id, set())
        approved.add(version)
        latest = self.data["latest_approved_version"].get(asset_id)
        if latest is None or version_rank(version) > version_rank(latest):
            self.data["latest_approved_version"][asset_id] = version

    def remember_state(self, asset_id: str, state_id: str, version: str, status: Any) -> None:
        refs = state_ref_keys(asset_id, state_id, version)
        self.data["known_state_refs"].update(refs)
        if status == AssetStatus.APPROVED.value:
            self.data["approved_state_refs"].update(refs)

    def remember_files(self, asset: dict[str, Any]) -> None:
        asset_id = str(asset.get("asset_id") or "")
        version = str(asset.get("version") or "")
        state_id = str(asset.get("state_id") or "")
        if not asset_id or not version or asset.get("status") != AssetStatus.APPROVED.value:
            return
        files = {value for value in asset.get("files", []) if isinstance(value, str)} if isinstance(asset.get("files"), list) else set()
        refs = AssetVersionRef(asset_id, version).keys()
        if state_id:
            refs.update(state_ref_keys(asset_id, state_id, version))
        for ref in refs:
            self.data["files_by_ref"].setdefault(ref, set()).update(files)

    def check_stale(self, ref: Any, path: Path, issues: list[dict[str, Any]], owner: str) -> None:
        parsed = AssetVersionRef.parse(ref)
        if parsed is None:
            return
        latest = self.data["latest_approved_version"].get(parsed.asset_id)
        if latest and version_rank(parsed.version) < version_rank(latest):
            issues.append(issue("error", "downstream_asset_version_stale", f"{owner} 仍引用旧资产版本 {ref}；最新 approved 版本是 {asset_version_key(parsed.asset_id, latest)}。", path))


def blank_asset_index() -> dict[str, Any]:
    return AssetVersionIndex.blank().data


def remember_asset_version(index: dict[str, Any], asset_id: str, version: str, status: Any) -> None:
    AssetVersionIndex(index).remember_version(asset_id, version, status)


def remember_state_version(index: dict[str, Any], asset_id: str, state_id: str, version: str, status: Any) -> None:
    AssetVersionIndex(index).remember_state(asset_id, state_id, version, status)


def remember_asset_files(index: dict[str, Any], asset: dict[str, Any]) -> None:
    AssetVersionIndex(index).remember_files(asset)


def check_stale_asset_version(ref: Any, index: dict[str, Any], path: Path, issues: list[dict[str, Any]], owner: str) -> None:
    AssetVersionIndex(index).check_stale(ref, path, issues, owner)


def check_asset_ref(ref: Any, index: dict[str, Any], path: Path, issues: list[dict[str, Any]], owner: str) -> None:
    if not isinstance(ref, str) or not ref.strip():
        issues.append(issue("error", "asset_ref_invalid", f"{owner} 的 asset_refs 必须是非空字符串。", path))
        return
    if ref in index["known_asset_ids"]:
        issues.append(issue("error", "asset_ref_version_missing", f"{owner} 引用资产 {ref} 时必须带版本号。", path))
        return
    if ref not in index["known_version_refs"]:
        issues.append(issue("error", "asset_ref_unknown", f"{owner} 引用了不存在的资产版本：{ref}", path))
        return
    if ref not in index["approved_version_refs"]:
        issues.append(issue("error", "downstream_asset_not_approved", f"{owner} 引用了未 approved 的资产版本：{ref}", path))
        return
    check_stale_asset_version(ref, index, path, issues, owner)


def check_state_ref(ref: Any, index: dict[str, Any], path: Path, issues: list[dict[str, Any]], owner: str) -> None:
    if not isinstance(ref, str) or not ref.strip():
        issues.append(issue("error", "state_ref_invalid", f"{owner} 的 state_refs 必须是非空字符串。", path))
        return
    if ref not in index["known_state_refs"]:
        issues.append(issue("error", "state_ref_unknown", f"{owner} 引用了不存在的状态资产：{ref}", path))
        return
    if ref not in index["approved_state_refs"]:
        issues.append(issue("error", "downstream_state_not_approved", f"{owner} 引用了未 approved 的状态资产：{ref}", path))
        return
    check_stale_asset_version(ref, index, path, issues, owner)


@dataclass(frozen=True)
class GenerationRequest:
    root: Path
    record: dict[str, Any]
    owner_path: Path
    scope: AssetScope
    issues: list[dict[str, Any]]
    generation: dict[str, Any]
    asset_id: str
    state_id: str
    tool: Any
    reference_asset_ids: list[Any]
    available_visual_refs: list[str]
    decision: Any
    visual_inputs: list[Any]
    style_anchor_refs: list[str]
    style_terms: list[str]

    @classmethod
    def from_record(
        cls,
        root: Path,
        record: dict[str, Any],
        owner_path: Path,
        scope: AssetScope,
        issues: list[dict[str, Any]],
    ) -> "GenerationRequest":
        generation = record.get("generation") if isinstance(record.get("generation"), dict) else {}
        refs = [*record.get("reference_asset_ids", [])] if isinstance(record.get("reference_asset_ids"), list) else []
        available_visual_refs: list[str] = []
        for field_owner in (record, generation):
            value = field_owner.get("available_visual_reference_ids") if isinstance(field_owner, dict) else None
            if isinstance(value, list):
                available_visual_refs.extend(item for item in value if isinstance(item, str) and item.strip())
        visual_inputs: list[Any] = []
        for field in ("reference_inputs", "input_files", "input_images"):
            value = generation.get(field)
            if isinstance(value, list):
                visual_inputs.extend(value)
        return cls(
            root=root,
            record=record,
            owner_path=owner_path,
            scope=scope,
            issues=issues,
            generation=generation,
            asset_id=str(record.get("asset_id") or ""),
            state_id=str(record.get("state_id") or ""),
            tool=generation.get("tool"),
            reference_asset_ids=refs,
            available_visual_refs=available_visual_refs,
            decision=record.get("visual_reference_decision") or generation.get("visual_reference_decision"),
            visual_inputs=visual_inputs,
            style_anchor_refs=combined_strings(record, generation, field="style_anchor_reference_ids"),
            style_terms=combined_strings(record, generation, field="style_prompt_terms"),
        )

    @property
    def route_label(self) -> Any:
        if self.scope == AssetScope.SHARED:
            return self.record.get("asset_id")
        return self.asset_id or "分集资产"

    @property
    def fallback_label(self) -> str:
        return "资产" if self.scope == AssetScope.SHARED else "分集资产"

    def code(self, base: str) -> str:
        return base if self.scope == AssetScope.SHARED else f"episode_{base}"

    def report(self, base: str, message: str) -> None:
        self.issues.append(issue("error", self.code(base), message, self.owner_path))

    def validate(self) -> None:
        if self.decision is not None and self.decision not in VISUAL_REFERENCE_DECISIONS:
            self.report("visual_reference_decision_invalid", f"{self.route_label} visual_reference_decision 无效：{self.decision}")
        category = self.record.get("category")
        project_visual_mode = self.record.get("project_visual_mode") or self.generation.get("project_visual_mode")
        if category in VISUAL_ASSET_CATEGORIES and self.record.get("status") == AssetStatus.APPROVED.value:
            if project_visual_mode not in PROJECT_VISUAL_MODES:
                self.report("project_visual_mode_missing_or_invalid", f"{self.asset_id or self.fallback_label} approved 图片资产必须登记有效 project_visual_mode。")
        strategy = GENERATION_ROUTE_STRATEGIES.get(self.tool)
        if strategy is not None:
            strategy.validate(self)
        if (
            category == AssetCategory.CHARACTER.value
            and self.state_id
            and self.tool == ImageGenerationRoute.IMAGE_GEN.value
            and self.decision != VisualReferenceDecision.EXPLICIT_USER_OVERRIDE.value
        ):
            self.report("character_state_asset_requires_image_edit", f"{self.asset_id or '角色状态资产'} 是人物状态资产时必须基于已批准人物图使用 image_edit；除非用户明确要求重做并记录 explicit_user_override。")
        check_generation_prompt_file(
            self.root,
            self.owner_path,
            self.asset_id or self.fallback_label,
            self.tool,
            self.generation.get("prompt_path"),
            self.issues,
        )

        if self.scope == AssetScope.SHARED:
            check_style_anchor_contract(
                self.root,
                self.owner_path,
                self.asset_id or self.fallback_label,
                self.tool,
                self.generation.get("prompt_path"),
                self.style_anchor_refs,
                self.style_terms,
                combined_strings(self.record, self.generation, field="style_adopt"),
                combined_strings(self.record, self.generation, field="style_exclude"),
                self.issues,
                self.decision,
            )


class ImageGenStrategy:
    def validate(self, request: GenerationRequest) -> None:
        style_anchor_is_input = request.scope == AssetScope.EPISODE
        if request.reference_asset_ids or request.visual_inputs or (style_anchor_is_input and request.style_anchor_refs):
            request.report("image_gen_should_not_have_visual_inputs", f"{request.route_label} 使用 image_gen 时不应登记图片参考输入。")
        if request.available_visual_refs and request.decision != VisualReferenceDecision.EXPLICIT_USER_OVERRIDE.value:
            request.report("image_gen_visual_reference_available", f"{request.route_label} 已登记可用视觉参考，必须使用 image_edit；除非用户明确要求不参考并记录 explicit_user_override。")
        if request.decision == VisualReferenceDecision.USED.value:
            request.report("image_gen_visual_reference_decision_conflict", f"{request.route_label} visual_reference_decision=used 时不能使用 image_gen。")


class ImageEditStrategy:
    def validate(self, request: GenerationRequest) -> None:
        if not (request.reference_asset_ids or request.visual_inputs or request.style_anchor_refs):
            request.report("image_edit_reference_missing", f"{request.route_label} 使用 image_edit 时必须登记实际参考来源。")
        if request.decision == VisualReferenceDecision.NONE_AVAILABLE.value:
            request.report("image_edit_visual_reference_decision_conflict", f"{request.route_label} 使用 image_edit 时 visual_reference_decision 不能写 none_available。")


GENERATION_ROUTE_STRATEGIES = {
    ImageGenerationRoute.IMAGE_GEN.value: ImageGenStrategy(),
    ImageGenerationRoute.IMAGE_EDIT.value: ImageEditStrategy(),
}


def check_global_style_moodboard(asset: dict[str, Any], generation: dict[str, Any], path: Path, issues: list[dict[str, Any]]) -> None:
    if asset.get("category") != AssetCategory.STYLE.value or asset.get("asset_id") != "STYLE001":
        return
    status = asset.get("status")
    style_asset_type = asset.get("style_asset_type") or generation.get("style_asset_type")
    if status == AssetStatus.APPROVED.value and style_asset_type is None:
        issues.append(issue("error", "style_asset_type_missing", "STYLE001 approved 前必须登记 style_asset_type=global_visual_language_moodboard。", path))
    if style_asset_type is not None and style_asset_type != "global_visual_language_moodboard":
        issues.append(issue("error", "style_asset_type_invalid", "STYLE001 必须登记为 global_visual_language_moodboard。", path))
    scene_links = asset.get("style_scene_atmosphere_links") or generation.get("style_scene_atmosphere_links")
    if status == AssetStatus.APPROVED.value and (not isinstance(scene_links, list) or not any(str(item).strip() for item in scene_links)):
        issues.append(issue("error", "style_scene_atmosphere_links_missing", "STYLE001 approved 时 style_scene_atmosphere_links 必须是非空数组。", path))
    visual_language = asset.get("style_visual_language") or generation.get("style_visual_language")
    if status == AssetStatus.APPROVED.value:
        if not isinstance(visual_language, dict):
            issues.append(issue("error", "style_visual_language_missing", "STYLE001 必须登记色彩、光线、构图、材质或空间氛围等视觉语言。", path))
        else:
            filled = [
                key
                for key, value in visual_language.items()
                if isinstance(value, list) and any(str(item).strip() for item in value)
            ]
            if len(filled) < 2:
                issues.append(issue("error", "style_visual_language_too_sparse", "STYLE001 视觉语言至少填写两类：palette/lighting/composition/materials/space_atmosphere/texture_or_grain。", path))
    if asset.get("contains_story_characters") is not False and generation.get("contains_story_characters") is not False:
        issues.append(issue("error", "style_moodboard_contains_characters_unknown", "STYLE001 全局风格 moodboard 必须明确 contains_story_characters=false。", path))
    if asset.get("contains_story_props") is not False and generation.get("contains_story_props") is not False:
        issues.append(issue("error", "style_moodboard_contains_props_unknown", "STYLE001 全局风格 moodboard 必须明确 contains_story_props=false。", path))


def _check_registry(root: Path, issues: list[dict[str, Any]], index: AssetVersionIndex) -> None:
    registry_path = root / "shared/03_资产/asset_registry.json"
    registry = load_json(registry_path, issues, required=False)
    if not isinstance(registry, dict):
        return
    assets = registry.get("assets")
    if isinstance(assets, list):
        version_keys: set[tuple[str, str]] = set()
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            asset_id = asset.get("asset_id")
            category = asset.get("category")
            version = str(asset.get("version") or "")
            if isinstance(asset_id, str) and asset_id.strip():
                index.remember_version(asset_id, version, asset.get("status"))
                index.remember_files(asset)
                key = (asset_id, version)
                if key in version_keys:
                    issues.append(issue("error", "asset_version_duplicate", f"asset_id + version 重复：{asset_id} {version}", registry_path))
                version_keys.add(key)
                expected_prefix = ASSET_PREFIX_BY_CATEGORY.get(str(category))
                if expected_prefix and not asset_id.startswith(expected_prefix):
                    issues.append(issue("error", "asset_id_prefix_mismatch", f"{asset_id} 与 category={category} 的前缀不一致。", registry_path))
            else:
                issues.append(issue("error", "asset_id_missing", "资产缺少 asset_id。", registry_path))
            status = asset.get("status")
            if status is not None and status not in ASSET_STATUS_VALUES:
                issues.append(issue("error", "asset_status_invalid", f"资产状态无效：{status}", registry_path))
            state_id = str(asset.get("state_id") or "")
            if isinstance(asset_id, str) and asset_id.strip() and state_id:
                index.remember_state(asset_id, state_id, version, status)
            for file_value in asset.get("files") or []:
                if not file_exists(root, file_value):
                    issues.append(issue("error", "asset_file_missing", f"资产文件不存在：{file_value}", registry_path))
            request = GenerationRequest.from_record(root, asset, registry_path, AssetScope.SHARED, issues)
            request.validate()
            generation = asset.get("generation") if isinstance(asset.get("generation"), dict) else {}
            check_global_style_moodboard(asset, generation, registry_path, issues)
    elif assets is not None:
        issues.append(issue("error", "assets_invalid", "asset_registry.assets 必须是数组。", registry_path))


def _check_shared_usage(
    root: Path,
    episode_id: str,
    shared: Any,
    path: Path,
    issues: list[dict[str, Any]],
    index: AssetVersionIndex,
) -> None:
    if not isinstance(shared, list):
        return
    seen_shared: set[tuple[str, str]] = set()
    for item in shared:
        if not isinstance(item, dict):
            continue
        asset_id = item.get("asset_id")
        version = str(item.get("version") or "")
        if isinstance(asset_id, str):
            if index.data["known_asset_ids"] and asset_id not in index.data["known_asset_ids"]:
                issues.append(issue("error", "asset_usage_unknown_shared_asset", f"{episode_id} 引用了 registry 中不存在的共享资产：{asset_id}", path))
            if not version:
                issues.append(issue("error", "asset_usage_shared_version_missing", f"{episode_id} 共享资产必须填写 version：{asset_id}", path))
            else:
                refs = AssetVersionRef(asset_id, version).keys()
                if index.data["known_version_refs"] and not (refs & index.data["known_version_refs"]):
                    issues.append(issue("error", "asset_usage_unknown_shared_version", f"{episode_id} 引用了 registry 中不存在的共享资产版本：{asset_id} {version}", path))
                elif index.data["known_version_refs"] and not (refs & index.data["approved_version_refs"]):
                    issues.append(issue("error", "asset_usage_shared_not_approved", f"{episode_id} 只能引用 registry 中 approved 的共享资产版本：{asset_id} {version}", path))
            key = (asset_id, version)
            if key in seen_shared:
                issues.append(issue("error", "asset_usage_duplicate", f"{episode_id} 共享资产重复：{asset_id} {version}", path))
            seen_shared.add(key)


class ReuseSourceCatalog:
    def __init__(self, root: Path, issues: list[dict[str, Any]]) -> None:
        self.root = root
        self.issues = issues
        self.cache: dict[str, dict[str, Any] | None] = {}

    def candidates(self, source_episode_id: str) -> list[dict[str, Any]]:
        if source_episode_id not in self.cache:
            source_path = self.root / f"episodes/{source_episode_id}/03_资产/asset_usage_{source_episode_id}.json"
            source_usage = load_json(source_path, self.issues, required=False)
            self.cache[source_episode_id] = source_usage if isinstance(source_usage, dict) else None
        source_usage = self.cache[source_episode_id]
        source_candidates: list[dict[str, Any]] = []
        if isinstance(source_usage, dict):
            for field in ("episode_assets", "reused_episode_assets"):
                values = source_usage.get(field)
                if isinstance(values, list):
                    source_candidates.extend(candidate for candidate in values if isinstance(candidate, dict))
        return source_candidates

    def match(self, source_episode_id: str, asset_id: str, state_id: str, version: str) -> dict[str, Any] | None:
        return next(
            (
                candidate
                for candidate in self.candidates(source_episode_id)
                if str(candidate.get("asset_id") or "") == asset_id
                and str(candidate.get("state_id") or "") == state_id
                and str(candidate.get("version") or "") == version
                and candidate.get("status") == AssetStatus.APPROVED.value
            ),
            None,
        )


def _check_reused_usage(
    root: Path,
    episode_id: str,
    reused: Any,
    path: Path,
    issues: list[dict[str, Any]],
    index: AssetVersionIndex,
    sources: ReuseSourceCatalog,
) -> None:
    if reused is not None and not isinstance(reused, list):
        issues.append(issue("error", "reused_episode_assets_invalid", f"{episode_id} reused_episode_assets 必须是数组。", path))
    if not isinstance(reused, list):
        return
    seen_reused: set[tuple[str, str, str, str]] = set()
    for item in reused:
        if not isinstance(item, dict):
            issues.append(issue("error", "reused_episode_asset_invalid", f"{episode_id} reused_episode_assets 每项必须是对象。", path))
            continue
        source_episode_id = str(item.get("source_episode_id") or "")
        asset_id = str(item.get("asset_id") or "")
        state_id = str(item.get("state_id") or "")
        version = str(item.get("version") or "")
        status = item.get("status")
        source_valid = True
        if not source_episode_id:
            issues.append(issue("error", "reused_episode_source_missing", f"{episode_id} 复用分集资产必须填写 source_episode_id。", path))
            source_valid = False
        elif not re.fullmatch(r"ep_[1-9]\d*", source_episode_id) or int(source_episode_id.split("_", 1)[1]) >= int(episode_id.split("_", 1)[1]):
            issues.append(issue("error", "reused_episode_source_invalid", f"{episode_id} 只能复用更早分集的 approved 资产：{source_episode_id}", path))
            source_valid = False
        if not asset_id or not version:
            issues.append(issue("error", "reused_episode_asset_ref_missing", f"{episode_id} 复用分集资产必须填写 asset_id 和 version。", path))
            source_valid = False
        if status != AssetStatus.APPROVED.value:
            issues.append(issue("error", "reused_episode_asset_not_approved", f"{episode_id} 只能复用 approved 分集资产：{asset_id} {state_id} {version}", path))
            source_valid = False
        if source_valid:
            matching_source = sources.match(source_episode_id, asset_id, state_id, version)
            if matching_source is None:
                issues.append(issue("error", "reused_episode_asset_source_not_found", f"{episode_id} 复用资产在 {source_episode_id} 中找不到一致的 approved 来源：{asset_id} {state_id} {version}", path))
                source_valid = False
            elif sorted(item.get("files") or []) != sorted(matching_source.get("files") or []):
                issues.append(issue("error", "reused_episode_asset_files_mismatch", f"{episode_id} 复用资产文件必须与 {source_episode_id} 来源记录一致：{asset_id} {state_id} {version}", path))
                source_valid = False
        if asset_id and source_valid:
            index.remember_version(asset_id, version, AssetStatus.APPROVED.value if status == AssetStatus.APPROVED.value else status)
            index.remember_files(item)
        if asset_id and state_id and source_valid:
            index.remember_state(asset_id, state_id, version, status)
        key = (source_episode_id, asset_id, state_id, version)
        if key in seen_reused:
            issues.append(issue("error", "reused_episode_asset_duplicate", f"{episode_id} 复用分集资产重复：{source_episode_id} {asset_id} {state_id} {version}", path))
        seen_reused.add(key)
        for file_value in item.get("files") or []:
            if not file_exists(root, file_value):
                issues.append(issue("error", "reused_episode_asset_file_missing", f"复用分集资产文件不存在：{file_value}", path))


def _check_episode_assets(
    root: Path,
    episode_id: str,
    episode_assets: Any,
    path: Path,
    issues: list[dict[str, Any]],
    index: AssetVersionIndex,
) -> None:
    if not isinstance(episode_assets, list):
        return
    state_keys: set[tuple[str, str, str]] = set()
    for item in episode_assets:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id") or "")
        state_id = str(item.get("state_id") or "")
        version = str(item.get("version") or "")
        if asset_id:
            index.remember_version(asset_id, version, item.get("status"))
            index.remember_files(item)
        if asset_id and state_id:
            index.remember_state(asset_id, state_id, version, item.get("status"))
        key = (asset_id, state_id, version)
        if key in state_keys:
            issues.append(issue("error", "episode_asset_duplicate", f"{episode_id} 分集资产重复：{asset_id} {state_id} {version}", path))
        state_keys.add(key)
        if item.get("status") is not None and item.get("status") not in ASSET_STATUS_VALUES:
            issues.append(issue("error", "episode_asset_status_invalid", f"分集资产状态无效：{item.get('status')}", path))
        category = item.get("category")
        expected_prefix = ASSET_PREFIX_BY_CATEGORY.get(str(category))
        if expected_prefix and asset_id and not asset_id.startswith(expected_prefix):
            issues.append(issue("error", "asset_id_prefix_mismatch", f"{asset_id} 与 category={category} 的前缀不一致。", path))
        GenerationRequest.from_record(root, item, path, AssetScope.EPISODE, issues).validate()
        for file_value in item.get("files") or []:
            if not file_exists(root, file_value):
                issues.append(issue("error", "episode_asset_file_missing", f"分集资产文件不存在：{file_value}", path))


def check_assets(root: Path, issues: list[dict[str, Any]], episode_filter: str | None = None) -> dict[str, Any]:
    version_index = AssetVersionIndex.blank()
    _check_registry(root, issues, version_index)
    sources = ReuseSourceCatalog(root, issues)
    for episode_id, episode_root in episode_dirs(root, episode_filter):
        path = episode_root / f"03_资产/asset_usage_{episode_id}.json"
        usage = load_json(path, issues, required=False)
        if not isinstance(usage, dict):
            continue
        _check_shared_usage(root, episode_id, usage.get("shared_assets"), path, issues, version_index)
        _check_reused_usage(root, episode_id, usage.get("reused_episode_assets"), path, issues, version_index, sources)
        _check_episode_assets(root, episode_id, usage.get("episode_assets"), path, issues, version_index)
    return version_index.data
