from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import hashlib
import json
import re
from typing import Any

try:
    from .drama_lint_confirmations import check_confirmation_transport
    from .drama_lint_domain import (
        check_video_model,
        issue,
        markdown_table_column_counts,
        normalized_speech,
        parse_iso_time,
    )
except ImportError:
    from drama_lint_confirmations import check_confirmation_transport
    from drama_lint_domain import (
        check_video_model,
        issue,
        markdown_table_column_counts,
        normalized_speech,
        parse_iso_time,
    )


class ConfirmationReporter:
    def __init__(self, path: Path, issues: list[dict[str, Any]]):
        self.path = path
        self.issues = issues

    def error(self, code: str, message: str) -> None:
        self.issues.append(issue("error", code, message, self.path))


def generated_segment_indexes(segments: list[Any]) -> list[int]:
    indexes: list[int] = []
    for fallback_index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            continue
        has_output = bool(str(segment.get("output_file") or "").strip())
        status = segment.get("status")
        if not has_output and status not in {"candidate", "accepted"}:
            continue
        index = segment.get("episode_segment_index")
        if isinstance(index, int) and not isinstance(index, bool):
            indexes.append(index)
        else:
            indexes.append(fallback_index)
    return sorted(set(indexes))


class SegmentCatalog:
    def __init__(self, segments: list[Any], reporter: ConfirmationReporter):
        self.segments = segments
        self.reporter = reporter
        self.by_index: dict[int, dict[str, Any]] = {}
        self.generated = generated_segment_indexes(segments)
        self._index_segments()

    def _index_segments(self) -> None:
        declared_indexes: list[int] = []
        for segment in self.segments:
            if not isinstance(segment, dict):
                continue
            index_value = segment.get("episode_segment_index")
            if not isinstance(index_value, int) or isinstance(index_value, bool) or index_value < 1:
                self.reporter.error("episode_segment_index_invalid", "每个视频片段必须填写从 1 开始的正整数 episode_segment_index。")
                continue
            if index_value in self.by_index:
                self.reporter.error("episode_segment_index_duplicate", f"episode_segment_index 重复：{index_value}")
                continue
            declared_indexes.append(index_value)
            self.by_index[index_value] = segment
        if sorted(declared_indexes) != list(range(1, len(self.by_index) + 1)):
            self.reporter.error("episode_segment_index_not_contiguous", "episode_segment_index 必须唯一并按 1..N 连续编号。")

    def has_endpoints(self, start: int, end: int) -> bool:
        return start in self.by_index and end in self.by_index

    def range(self, start: int, end: int) -> list[dict[str, Any] | None]:
        return [self.by_index.get(index) for index in range(start, end + 1)]


@dataclass
class GenerationConfirmation:
    item: dict[str, Any]
    confirmation_index: int
    start: int
    end: int
    attempt: Any
    confirmation_id: str
    confirmed_at: datetime | None
    serial_run: bool
    planning_preview: bool
    expected_segments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def covered_count(self) -> int:
        return self.end - self.start + 1

    @property
    def planned_count(self) -> Any:
        return self.item.get("planned_video_count")

    @property
    def final_text(self) -> str:
        return str(self.item.get("final_parameters_text") or "")

    @property
    def previous_attempt(self) -> int | None:
        return self.attempt if isinstance(self.attempt, int) else None

    @property
    def expected_total(self) -> float:
        return sum(
            float(segment.get("duration_s"))
            for segment in self.expected_segments
            if isinstance(segment.get("duration_s"), (int, float)) and not isinstance(segment.get("duration_s"), bool)
        )


class ConfirmationLedger:
    def __init__(self, reporter: ConfirmationReporter):
        self.reporter = reporter
        self.confirmation_ids: set[str] = set()
        self.confirmed_ranges: list[tuple[int, int]] = []
        self.records: list[GenerationConfirmation] = []

    def register_id(self, confirmation_id: str) -> None:
        if confirmation_id in self.confirmation_ids:
            self.reporter.error("video_generation_confirmation_id_duplicate", f"generation_confirmations.confirmation_id 重复：{confirmation_id}")
        elif confirmation_id:
            self.confirmation_ids.add(confirmation_id)

    def overlapping(self, record: GenerationConfirmation) -> list[GenerationConfirmation]:
        return [
            prior
            for prior in self.records
            if prior.start <= record.end and record.start <= prior.end
        ]

    def append(self, record: GenerationConfirmation) -> None:
        self.records.append(record)

    def matching(self, segment_index: int) -> list[GenerationConfirmation]:
        return [record for record in self.records if record.start <= segment_index <= record.end]


class ConfirmationEnvelopeRule:


    def __init__(self, reporter: ConfirmationReporter, lightweight: bool):
        self.reporter = reporter
        self.lightweight = lightweight

    def parse(
        self,
        item: Any,
        confirmation_index: int,
        ledger: ConfirmationLedger,
        catalog: SegmentCatalog,
    ) -> GenerationConfirmation | None:
        if not isinstance(item, dict):
            self.reporter.error("video_generation_confirmation_invalid", "generation_confirmations 每项必须是对象。")
            return None
        check_confirmation_transport(item, self.reporter.path, self.reporter.issues)
        expected_source = "planning_preview" if self.lightweight and confirmation_index == 0 else "batch_preview"
        if item.get("confirmation_source") != expected_source:
            self.reporter.error("video_confirmation_source_invalid", f"本次确认的 confirmation_source 必须为 {expected_source}，聊天或宿主工具来源另存 confirmation_transport。")
        attempt = item.get("attempt")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            self.reporter.error("video_generation_confirmation_attempt_invalid", "generation_confirmations.attempt 必须是从 1 开始的正整数。")
        confirmation_id = str(item.get("confirmation_id") or "").strip()
        ledger.register_id(confirmation_id)
        start = item.get("batch_start_segment_index")
        end = item.get("batch_end_segment_index")
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            self.reporter.error("video_generation_confirmation_range_invalid", "generation_confirmations 必须填写整数 batch_start_segment_index 和 batch_end_segment_index。")
            return None
        if start < 1 or end - start + 1 < 1:
            self.reporter.error("video_generation_confirmation_range_invalid", "一次用户确认必须覆盖起始、结束均为正整数且 end >= start 的连续 SEG 范围。")
            return None
        if end != start:
            self.reporter.error("video_generation_confirmation_too_large", "每次只确认并生成一个新 SEG；上一段真实尾态复核、登记和交付后才能确认下一段。")
            return None
        record = GenerationConfirmation(
            item=item,
            confirmation_index=confirmation_index,
            start=start,
            end=end,
            attempt=attempt,
            confirmation_id=confirmation_id,
            confirmed_at=parse_iso_time(item.get("confirmed_at")),
            serial_run=item.get("execution_mode") == "serial_real_tail_chain",
            planning_preview=self.lightweight and item.get("confirmation_source") == "planning_preview",
        )
        self._validate_serial_run(record)
        if not catalog.has_endpoints(start, end):
            self.reporter.error("video_generation_confirmation_unknown_segment", "视频生成参数确认范围必须对应 video_manifest 中真实存在的连续 SEG。")
            return None
        return record

    def _validate_serial_run(self, record: GenerationConfirmation) -> None:
        if not record.serial_run:
            return
        run_plan_file = str(record.item.get("run_plan_file") or "").strip()
        run_plan_sha256 = str(record.item.get("run_plan_sha256") or "").strip()
        if not run_plan_file or Path(run_plan_file).is_absolute() or ".." in Path(run_plan_file).parts:
            self.reporter.error("video_serial_run_plan_invalid", "serial_real_tail_chain 确认必须绑定项目相对路径 run_plan_file。")
        if not re.fullmatch(r"[0-9a-f]{64}", run_plan_sha256):
            self.reporter.error("video_serial_run_plan_hash_invalid", "serial_real_tail_chain 确认必须绑定 run_plan_sha256（64 位小写 SHA-256）。")


class SupersessionRule:
    def validate(self, record: GenerationConfirmation, ledger: ConfirmationLedger, reporter: ConfirmationReporter) -> None:
        supersedes = record.item.get("supersedes_confirmation_ids", [])
        if not isinstance(supersedes, list) or not all(isinstance(value, str) and value.strip() for value in supersedes):
            reporter.error("video_generation_supersedes_invalid", "supersedes_confirmation_ids 必须是确认 ID 字符串数组。")
            supersedes = []
        overlapping_prior = ledger.overlapping(record)
        overlapping_ids = {prior.confirmation_id for prior in overlapping_prior if prior.confirmation_id}
        if overlapping_ids and not overlapping_ids.issubset(set(supersedes)):
            reporter.error("video_generation_confirmation_overlap", "重生或返修覆盖既有 SEG 时，必须通过 supersedes_confirmation_ids 显式替代所有重叠的旧确认。")
        unknown_supersedes = sorted(set(supersedes) - {prior.confirmation_id for prior in ledger.records})
        if unknown_supersedes:
            reporter.error("video_generation_supersedes_unknown", f"supersedes_confirmation_ids 引用了不存在或尚未发生的确认：{unknown_supersedes}")
        unrelated_supersedes = sorted(set(supersedes) - overlapping_ids)
        if unrelated_supersedes:
            reporter.error("video_generation_supersedes_unrelated", f"supersedes_confirmation_ids 只能列出与本次范围重叠的旧确认：{unrelated_supersedes}")
        for prior in overlapping_prior:
            if prior.confirmation_id in supersedes and record.confirmed_at is not None and prior.confirmed_at is not None and record.confirmed_at <= prior.confirmed_at:
                reporter.error("video_generation_supersedes_time_invalid", "替代确认的 confirmed_at 必须晚于被替代确认。")
        if overlapping_prior and isinstance(record.attempt, int) and not isinstance(record.attempt, bool):
            prior_attempts = [prior.previous_attempt for prior in overlapping_prior if isinstance(prior.previous_attempt, int)]
            if prior_attempts and record.attempt <= max(prior_attempts):
                reporter.error("video_generation_confirmation_attempt_not_incremented", "返修或重生确认的 attempt 必须高于其覆盖的旧确认。")
        elif not overlapping_prior and record.attempt != 1:
            reporter.error("video_generation_confirmation_initial_attempt_invalid", "首次覆盖一组 SEG 的确认 attempt 必须为 1。")
        ledger.append(record)


class SegmentAuthorizationRule:
    REQUIRED_FIELDS = (
        "confirmation_id",
        "model",
        "video_provider",
        "video_provider_adapter_version",
        "video_provider_adapter_sha256",
        "cloud_config_sha256",
        "aspect_ratio",
        "duration_s",
        "planned_video_count",
        "creative_direction",
        "cost_notice",
        "final_parameters_text",
        "interaction_ask_call_id",
        "interaction_ask_result",
        "user_message",
        "confirmed_at",
    )

    def validate(self, record: GenerationConfirmation, catalog: SegmentCatalog, reporter: ConfirmationReporter) -> None:
        planned_count = record.planned_count
        if not isinstance(planned_count, int) or isinstance(planned_count, bool) or planned_count < 1:
            reporter.error("video_generation_count_invalid", "planned_video_count 必须是正整数，并等于本次确认覆盖的连续 SEG 数。")
        elif planned_count != record.covered_count:
            reporter.error("video_generation_count_mismatch", "planned_video_count 必须等于本轮确认覆盖的 SEG 数。")
        for field_name in self.REQUIRED_FIELDS:
            if not str(record.item.get(field_name) or "").strip():
                reporter.error("video_generation_confirmation_field_missing", f"视频生成参数确认缺少 {field_name}。")
        if record.planning_preview and (record.start != 1 or record.end != 1 or planned_count != 1):
            reporter.error("lightweight_generation_scope_invalid", "轻量模式规划确认只能授权唯一一个视频。")
        expected = catalog.range(record.start, record.end)
        if any(segment is None for segment in expected):
            reporter.error("video_generation_confirmation_unknown_segment", "视频生成参数确认范围必须对应 video_manifest 中真实存在的连续 SEG。")
            expected = []
        record.expected_segments = [segment for segment in expected if segment is not None]
        for segment in record.expected_segments:
            self._validate_segment(segment, reporter)

    def _validate_segment(self, segment: dict[str, Any], reporter: ConfirmationReporter) -> None:
        segment_id = str(segment.get("segment_id") or "segment")
        conversion = segment.get("h3_conversion")
        if not isinstance(conversion, dict) or (
            conversion.get("skill_name") != "h3-prompt-writing"
            or conversion.get("invocation_channel") != "host_skill_tool"
            or conversion.get("invoked") is not True
        ):
            reporter.error("video_generation_before_h3_skill_conversion", f"{segment_id} 未完成真实 h3-prompt-writing Skill 转换，不得进入生成确认批。")
        incoming_seam = segment.get("incoming_seam")
        if not isinstance(incoming_seam, dict) or incoming_seam.get("seam_mode") != "continuous":
            return
        tail_frame_id = str(incoming_seam.get("previous_tail_frame_id") or "").strip()
        references = segment.get("reference_inputs")
        tail_ready = bool(tail_frame_id) and isinstance(references, list) and any(
            isinstance(reference, dict)
            and reference.get("source_type") == "frame"
            and reference.get("source_id") == tail_frame_id
            and reference.get("role") in {"previous_tail_reference", "previous_tail_as_start_frame"}
            and bool(str(reference.get("file") or "").strip())
            for reference in references
        )
        if not tail_ready:
            reporter.error("video_continuous_tail_not_ready", f"{segment_id} 是 continuous 段；确认前必须已登记上一段真实 tail FRM、真实文件和来源关系。不得以未来 tail 依赖或计划路径代替。")


class SerialRunBindingRule:

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def validate(self, record: GenerationConfirmation, reporter: ConfirmationReporter) -> None:
        if not record.serial_run:
            return
        manifest_path = reporter.path.resolve()
        if manifest_path.parent.name != "04_视频片段" or not re.fullmatch(
                r"video_manifest_ep_\d+\.json", manifest_path.name):
            return
        try:
            root = manifest_path.parents[3]
        except IndexError:
            return
        run_plan_file = str(record.item.get("run_plan_file") or "").strip()
        if not run_plan_file or Path(run_plan_file).is_absolute() or ".." in Path(run_plan_file).parts:
            return
        queue_path = (root / run_plan_file).resolve()
        try:
            queue_path.relative_to(root)
        except ValueError:
            reporter.error("video_serial_run_plan_invalid", "run_plan_file 必须留在项目根目录内。")
            return
        if queue_path.parent != manifest_path.parent or queue_path.name != "串行执行.json":
            reporter.error("video_serial_run_plan_path_mismatch", "最新确认必须绑定同集 04_视频片段/串行执行.json。")
            return
        try:
            queue_bytes = queue_path.read_bytes()
            queue = json.loads(queue_bytes.decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            reporter.error("video_serial_run_plan_unreadable", f"无法读取最新确认绑定的真实 queue：{exc}")
            return
        if not isinstance(queue, dict) or not isinstance(queue.get("segments"), list):
            reporter.error("video_serial_run_plan_invalid", "真实 queue 必须是包含 segments 数组的对象。")
            return
        if record.item.get("run_plan_sha256") != hashlib.sha256(queue_bytes).hexdigest():
            reporter.error("video_serial_run_plan_hash_mismatch", "最新确认的 run_plan_sha256 必须等于当前 queue 实际字节 SHA-256；queue 变化后必须重新预检与确认。")
        provider = record.item.get("video_provider")
        if queue.get("video_provider") != provider:
            reporter.error("video_generation_provider_queue_mismatch", "最新确认的 video_provider 必须匹配固定 queue。")
        for field_name in ("video_provider_adapter_sha256", "cloud_config_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(record.item.get(field_name) or "")):
                reporter.error("video_generation_provider_binding_hash_invalid", f"{field_name} 必须是 64 位小写 SHA-256。")
        cloud_config = queue.get("cloud_config")
        try:
            if not isinstance(cloud_config, str) or Path(cloud_config).is_absolute() or ".." in Path(cloud_config).parts:
                raise ValueError("cloud_config 必须是项目相对路径")
            cloud_path = (root / cloud_config).resolve()
            cloud_path.relative_to(root)
            actual_cloud_sha256 = self._sha256(cloud_path)
        except (OSError, ValueError) as exc:
            reporter.error("video_generation_cloud_config_unreadable", f"无法核验确认绑定的 cloud config：{exc}")
        else:
            if record.item.get("cloud_config_sha256") != actual_cloud_sha256:
                reporter.error("video_generation_cloud_config_hash_mismatch", "最新确认的 cloud_config_sha256 必须等于当前配置实际字节 SHA-256。")
        queue_by_id = {
            item.get("segment_id"): item for item in queue["segments"]
            if isinstance(item, dict) and isinstance(item.get("segment_id"), str)
        }
        for segment in record.expected_segments:
            segment_id = segment.get("segment_id")
            if segment.get("video_provider") != provider:
                reporter.error("video_generation_provider_segment_mismatch", f"{segment_id} 的 video_provider 必须匹配最新确认。")
            entry = queue_by_id.get(segment_id)
            if not isinstance(entry, dict):
                reporter.error("video_serial_run_segment_missing", f"当前 queue 未登记已确认片段 {segment_id}。")
                continue
            if entry.get("operation") != "reuse" and entry.get("confirmation_id") != record.confirmation_id:
                reporter.error("video_serial_run_confirmation_mismatch", f"{segment_id} 的 queue confirmation_id 必须等于该 SEG 最新有效确认。")
            if entry.get("duration_s") != segment.get("duration_s"):
                reporter.error("video_serial_run_segment_duration_mismatch", f"{segment_id} 的 queue 时长必须与 video_manifest 一致。")


class DurationConfirmationRule:
    def validate(self, record: GenerationConfirmation, reporter: ConfirmationReporter) -> None:
        segment_durations = record.item.get("segment_durations")
        if not isinstance(segment_durations, list) or len(segment_durations) != record.covered_count:
            reporter.error("video_generation_segment_durations_invalid", "segment_durations 必须逐 SEG 记录，项数等于本批次数量。")
            return
        if not record.expected_segments:
            return
        for offset, (duration_item, segment) in enumerate(zip(segment_durations, record.expected_segments), start=record.start):
            if not isinstance(duration_item, dict):
                reporter.error("video_generation_segment_duration_invalid", f"本批第 {offset} 个 segment_durations 必须是对象。")
                continue
            expected_id = str(segment.get("segment_id") or "")
            expected_duration = segment.get("duration_s")
            if duration_item.get("segment_id") != expected_id:
                reporter.error("video_generation_segment_duration_id_mismatch", f"本批第 {offset} 个逐段时长必须对应 {expected_id}。")
            if duration_item.get("duration_s") != expected_duration:
                reporter.error("video_generation_segment_duration_mismatch", f"{expected_id} 的确认时长必须等于实际片段时长。")
        if record.item.get("duration_s") != record.expected_total:
            reporter.error("video_generation_total_duration_mismatch", "批次 duration_s 必须等于逐段时长之和。")


class ParameterDisplayPolicy:
    def validate(self, record: GenerationConfirmation, reporter: ConfirmationReporter) -> None:
        raise NotImplementedError


class PlanningParameterDisplayPolicy(ParameterDisplayPolicy):
    REQUIRED_FIELDS = {
        "task_type",
        "delivery_format",
        "quantity",
        "total_duration",
        "aspect_ratio_and_resolution",
        "model",
        "video_provider",
        "visual_and_continuity",
        "audio_and_subtitles",
        "reference_materials",
        "tool_limits_and_cost",
    }

    def validate(self, record: GenerationConfirmation, reporter: ConfirmationReporter) -> None:
        displayed = record.item.get("displayed_parameter_table")
        if not isinstance(displayed, dict):
            reporter.error("lightweight_planning_parameters_missing", "轻量模式生成确认必须登记已展示的规划参数列表。")
            return
        missing_fields = sorted(field for field in self.REQUIRED_FIELDS if not str(displayed.get(field) or "").strip())
        if missing_fields:
            reporter.error("lightweight_planning_parameters_incomplete", f"轻量模式规划参数缺少视频生成确认字段：{missing_fields}")
        if displayed.get("quantity") != 1:
            reporter.error("lightweight_planning_quantity_invalid", "轻量模式视频数量必须为 1。")
        provider = str(record.item.get("video_provider") or "").strip()
        if provider and provider.casefold() not in str(displayed.get("video_provider") or "").casefold():
            reporter.error("lightweight_planning_provider_mismatch", "轻量规划展示的视频生成后端必须匹配确认记录 video_provider。")
        for field_name, value in displayed.items():
            for rendered in value if isinstance(value, list) else [value]:
                if str(rendered).strip() and str(rendered).strip() not in record.final_text:
                    reporter.error("lightweight_planning_parameter_text_mismatch", f"轻量规划展示文本缺少参数 {field_name} 的确认值。")


class BatchParameterDisplayPolicy(ParameterDisplayPolicy):
    REQUIRED_FIELDS = (
        "task_type",
        "delivery_format",
        "segment_durations",
        "total_duration",
        "aspect_ratio_and_resolution",
        "model",
        "video_provider",
        "visual_and_continuity",
        "audio_and_subtitles",
        "reference_materials",
        "tool_limits_and_cost",
    )

    def validate(self, record: GenerationConfirmation, reporter: ConfirmationReporter) -> None:
        displayed = record.item.get("displayed_parameter_table")
        if not isinstance(displayed, dict):
            reporter.error("video_generation_parameter_table_missing", "必须登记实际展示的一张本批次合并参数确认表。")
            return
        if displayed.get("quantity") != record.planned_count:
            reporter.error("video_generation_displayed_quantity_mismatch", "参数确认表“数量”必须等于 planned_video_count。")
        for field_name in self.REQUIRED_FIELDS:
            value = displayed.get(field_name)
            if isinstance(value, list):
                valid = bool(value) and all(str(entry).strip() for entry in value)
            else:
                valid = bool(str(value or "").strip())
            if not valid:
                reporter.error("video_generation_parameter_table_field_missing", f"合并参数确认表缺少 {field_name}。")
            elif isinstance(value, list):
                for entry in value:
                    if str(entry).strip() not in record.final_text:
                        reporter.error("video_generation_parameter_table_text_mismatch", f"合并参数确认表展示文本缺少 {field_name} 项：{entry}。")
            elif str(value).strip() not in record.final_text:
                reporter.error("video_generation_parameter_table_text_mismatch", f"合并参数确认表展示文本缺少 {field_name} 的确认值。")
        self._validate_durations(record, displayed, reporter)
        self._validate_format(record, displayed, reporter)
        provider = str(record.item.get("video_provider") or "").strip()
        displayed_provider = str(displayed.get("video_provider") or "").strip()
        if provider and provider.casefold() not in displayed_provider.casefold():
            reporter.error("video_generation_displayed_provider_mismatch", "参数确认表中的视频生成后端必须匹配本批次 video_provider。")

    def _validate_durations(self, record: GenerationConfirmation, displayed: dict[str, Any], reporter: ConfirmationReporter) -> None:
        displayed_durations = displayed.get("segment_durations")
        if isinstance(displayed_durations, list) and len(displayed_durations) != record.covered_count:
            reporter.error("video_generation_displayed_duration_count_mismatch", "参数确认表必须按 SEG 分别展示时长，项数等于“数量”。")
        elif isinstance(displayed_durations, list) and record.expected_segments:
            for displayed_duration, segment in zip(displayed_durations, record.expected_segments):
                expected_id = str(segment.get("segment_id") or "")
                expected_duration = segment.get("duration_s")
                duration_text = f"{expected_duration:g}" if isinstance(expected_duration, (int, float)) and not isinstance(expected_duration, bool) else str(expected_duration or "")
                rendered = str(displayed_duration)
                if expected_id not in rendered or not re.search(rf"{re.escape(duration_text)}\s*(?:秒|s\b|sec(?:ond)?s?\b)", rendered, flags=re.I):
                    reporter.error("video_generation_displayed_duration_mismatch", f"参数确认表必须单独显示 {expected_id} 的真实时长。")

    def _validate_format(self, record: GenerationConfirmation, displayed: dict[str, Any], reporter: ConfirmationReporter) -> None:
        displayed_model = str(displayed.get("model") or "")
        if str(record.item.get("model") or "") not in displayed_model:
            reporter.error("video_generation_displayed_model_mismatch", "参数确认表中的视频模型必须匹配本批次 model。")
        displayed_format = str(displayed.get("aspect_ratio_and_resolution") or "")
        if str(record.item.get("aspect_ratio") or "") not in displayed_format:
            reporter.error("video_generation_displayed_aspect_ratio_mismatch", "参数确认表中的画幅必须匹配本批次 aspect_ratio。")
        if record.expected_segments:
            total_text = f"{record.expected_total:g}"
            if not re.search(rf"{re.escape(total_text)}\s*(?:秒|s\b|sec(?:ond)?s?\b)", str(displayed.get("total_duration") or ""), flags=re.I):
                reporter.error("video_generation_displayed_total_duration_mismatch", "参数确认表中的总时长必须等于本批次逐段时长之和。")


class StoryboardDisplayPolicy:
    def validate(self, record: GenerationConfirmation, reporter: ConfirmationReporter) -> None:
        raise NotImplementedError


class PlanningStoryboardDisplayPolicy(StoryboardDisplayPolicy):
    FIELDS = ("time_range", "story_and_action", "audio", "camera_transition", "hook")

    def validate(self, record: GenerationConfirmation, reporter: ConfirmationReporter) -> None:
        rows = record.item.get("displayed_storyboard_rows")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
            reporter.error("lightweight_planning_preview_rows_invalid", "轻量模式规划五列预览必须为 1-8 行。")
            return
        if any(not isinstance(row, dict) or not all(str(row.get(field) or "").strip() for field in self.FIELDS) for row in rows):
            reporter.error("lightweight_planning_preview_field_missing", "轻量模式规划五列预览每行必须填写时间、剧情动作、声音、运镜衔接和钩子。")
            return
        for row in rows:
            for field_name in self.FIELDS:
                if str(row[field_name]).strip() not in record.final_text:
                    reporter.error("lightweight_planning_preview_text_mismatch", f"轻量规划展示文本缺少五列预览的 {field_name} 内容。")
        row_audio = normalized_speech(" ".join(str(row["audio"]) for row in rows))
        for segment in record.expected_segments:
            speech_lines = segment.get("speech_lines") if isinstance(segment.get("speech_lines"), list) else []
            for speech_line in speech_lines:
                spoken = speech_line.get("spoken_text") if isinstance(speech_line, dict) else None
                if isinstance(spoken, str) and normalized_speech(spoken) not in row_audio:
                    reporter.error("lightweight_planning_preview_speech_missing", "轻量五列预览必须完整展示本次生成的全部台词。")


class BatchStoryboardDisplayPolicy(StoryboardDisplayPolicy):
    FIELDS = ("visual_content", "subject_action", "audio", "camera_and_materials")

    def validate(self, record: GenerationConfirmation, reporter: ConfirmationReporter) -> None:
        rows = record.item.get("displayed_storyboard_rows")
        if not isinstance(rows, list) or len(rows) != record.covered_count:
            reporter.error("video_generation_storyboard_rows_invalid", "本批次五列分镜表必须每个 SEG 恰好一行，行数等于“数量”。")
            return
        if not record.expected_segments:
            return
        for offset, (row, segment) in enumerate(zip(rows, record.expected_segments), start=record.start):
            if not isinstance(row, dict):
                reporter.error("video_generation_storyboard_row_invalid", f"本批第 {offset} 行分镜必须是对象。")
                continue
            expected_id = str(segment.get("segment_id") or "")
            if row.get("segment_id") != expected_id or row.get("duration_s") != segment.get("duration_s"):
                reporter.error("video_generation_storyboard_segment_mismatch", f"本批五列分镜第 {offset} 行的片段与时长必须匹配 {expected_id}。")
            for field_name in self.FIELDS:
                if not str(row.get(field_name) or "").strip():
                    reporter.error("video_generation_storyboard_field_missing", f"{expected_id} 五列分镜缺少 {field_name}。")
                elif str(row.get(field_name)).strip() not in record.final_text:
                    reporter.error("video_generation_storyboard_text_mismatch", f"final_parameters_text 缺少 {expected_id} 五列分镜中的 {field_name} 内容。")
            row_audio = str(row.get("audio") or "")
            for speech_line in segment.get("speech_lines") or []:
                if not isinstance(speech_line, dict):
                    continue
                spoken_text = str(speech_line.get("spoken_text") or "").strip()
                if spoken_text and normalized_speech(spoken_text) not in normalized_speech(row_audio):
                    reporter.error("video_generation_storyboard_speech_missing", f"{expected_id} 五列分镜必须完整列出本段台词：{spoken_text}")


class FinalConfirmationRule:
    def __init__(self):
        self.parameter_policies = {
            False: BatchParameterDisplayPolicy(),
            True: PlanningParameterDisplayPolicy(),
        }
        self.storyboard_policies = {
            False: BatchStoryboardDisplayPolicy(),
            True: PlanningStoryboardDisplayPolicy(),
        }

    def validate(self, record: GenerationConfirmation, reporter: ConfirmationReporter) -> None:
        self.parameter_policies[record.planning_preview].validate(record, reporter)
        self.storyboard_policies[record.planning_preview].validate(record, reporter)
        expected_table_counts = [5] if record.planning_preview else [2, 5]
        if markdown_table_column_counts(record.final_text) != expected_table_counts:
            reporter.error("video_generation_confirmation_tables_invalid", "视频生成确认展示结构与当前模式不一致。")
        if record.expected_segments and not record.planning_preview:
            for segment in record.expected_segments:
                segment_id = str(segment.get("segment_id") or "")
                duration = segment.get("duration_s")
                duration_text = f"{duration:g}" if isinstance(duration, (int, float)) and not isinstance(duration, bool) else str(duration or "")
                if segment_id not in record.final_text or not re.search(rf"{re.escape(duration_text)}\s*(?:秒|s\b|sec(?:ond)?s?\b)", record.final_text, flags=re.I):
                    reporter.error("video_generation_segment_details_not_displayed", f"final_parameters_text 必须分别显示 {segment_id} 及其时长。")
        if record.confirmed_at is None:
            reporter.error("video_generation_confirmation_time_invalid", "视频生成参数确认 confirmed_at 必须是带时区 ISO-8601 时间。")
        if str(record.item.get("interaction_ask_result") or "").strip() != "generate":
            reporter.error("video_generation_interaction_confirmation_missing", "视频生成参数确认必须登记真实用户选择 generate；确认渠道由 confirmation_transport 标识。")
        if not str(record.item.get("cost_notice") or "").strip():
            reporter.error("video_generation_cost_notice_missing", "视频生成参数确认必须登记非空 cost_notice；具体措辞由主 Agent 人工复核。")
        check_video_model(record.item.get("model"), reporter.path, "generation_confirmations.model", reporter.issues)


class GeneratedSegmentAuditRule:
    def validate(self, catalog: SegmentCatalog, ledger: ConfirmationLedger, reporter: ConfirmationReporter) -> None:
        for index in catalog.generated:
            if not any(start <= index <= end for start, end in ledger.confirmed_ranges):
                reporter.error("video_generation_confirmation_missing", f"生成 SEG{index:03d} 前必须先取得覆盖该片段的用户确认。")
        for fallback_index, segment in enumerate(catalog.segments, start=1):
            if not isinstance(segment, dict):
                continue
            generated_segment = bool(str(segment.get("output_file") or "").strip()) or segment.get("status") in {"candidate", "accepted"}
            if not generated_segment:
                continue
            index_value = segment.get("episode_segment_index")
            segment_index = index_value if isinstance(index_value, int) and not isinstance(index_value, bool) else fallback_index
            matching = ledger.matching(segment_index)
            if not matching:
                continue
            confirmation_id = str(segment.get("generation_confirmation_id") or "").strip()
            if not confirmation_id:
                reporter.error("video_generation_confirmation_id_missing", f"SEG{segment_index:03d} 已生成，必须登记 generation_confirmation_id。")
            elif all(record.confirmation_id != confirmation_id for record in matching):
                reporter.error("video_generation_confirmation_id_mismatch", f"SEG{segment_index:03d} generation_confirmation_id 必须匹配覆盖该片段的视频生成参数确认。")
            elif confirmation_id != matching[-1].confirmation_id:
                reporter.error("video_generation_confirmation_not_latest", f"SEG{segment_index:03d} 必须引用覆盖该片段的最新有效确认。")
            if not str(segment.get("tool_call_id") or "").strip():
                reporter.error("video_tool_call_id_missing", f"SEG{segment_index:03d} 已生成，必须登记实际视频工具 tool_call_id。")
            called_at = parse_iso_time(segment.get("tool_called_at"))
            if called_at is None:
                reporter.error("video_tool_called_at_invalid", f"SEG{segment_index:03d} 已生成，必须登记带时区 ISO-8601 tool_called_at。")
                continue
            latest_confirmed_at = matching[-1].confirmed_at
            if latest_confirmed_at is None or latest_confirmed_at >= called_at:
                reporter.error("video_confirmation_after_tool_call", f"SEG{segment_index:03d} 的视频生成参数确认时间必须早于视频工具调用时间。")


class VideoGenerationConfirmationValidator:
    def __init__(self, path: Path, issues: list[dict[str, Any]], lightweight: bool):
        self.reporter = ConfirmationReporter(path, issues)
        self.lightweight = lightweight
        self.envelope = ConfirmationEnvelopeRule(self.reporter, lightweight)
        self.supersession = SupersessionRule()
        self.authorization = SegmentAuthorizationRule()
        self.durations = DurationConfirmationRule()
        self.serial_binding = SerialRunBindingRule()
        self.final = FinalConfirmationRule()
        self.audit = GeneratedSegmentAuditRule()

    def validate(self, data: dict[str, Any], segments: list[Any]) -> None:
        catalog = SegmentCatalog(segments, self.reporter)
        confirmations = data.get("generation_confirmations")
        if not catalog.generated and not confirmations:
            return
        if not isinstance(confirmations, list):
            self.reporter.error("video_generation_confirmations_missing", "视频阶段每个新生成 SEG 都必须记录对当前段完整参数的用户确认；原任务恢复不新增确认。")
            return
        if self.lightweight and confirmations and (
            not isinstance(confirmations[0], dict)
            or confirmations[0].get("confirmation_source") != "planning_preview"
        ):
            self.reporter.error("lightweight_planning_confirmation_missing", "轻量模式首次生成确认必须来源于规划参数与五列预览。")
        ledger = ConfirmationLedger(self.reporter)
        for confirmation_index, item in enumerate(confirmations):
            record = self.envelope.parse(item, confirmation_index, ledger, catalog)
            if record is None:
                continue
            ledger.confirmed_ranges.append((record.start, record.end))
            self.supersession.validate(record, ledger, self.reporter)
            self.authorization.validate(record, catalog, self.reporter)
            self.durations.validate(record, self.reporter)
            self.final.validate(record, self.reporter)
        for segment_index in sorted({record.start for record in ledger.records}):
            matching = ledger.matching(segment_index)
            if matching:
                self.serial_binding.validate(matching[-1], self.reporter)
        self.audit.validate(catalog, ledger, self.reporter)


def check_video_generation_confirmations(
    data: dict[str, Any],
    segments: list[Any],
    path: Path,
    issues: list[dict[str, Any]],
    lightweight: bool = False,
) -> None:
    VideoGenerationConfirmationValidator(path, issues, lightweight).validate(data, segments)
