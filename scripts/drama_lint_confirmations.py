from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any

try:
    from .drama_lint_domain import EPISODE_STAGES, STAGES, issue, parse_iso_time
except ImportError:
    from drama_lint_domain import EPISODE_STAGES, STAGES, issue, parse_iso_time


class ConfirmationMode(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


class ConfirmationTransport(str, Enum):
    USER_MESSAGE = "user_message"
    HOST_TOOL = "host_tool"


CONFIRMATION_MODES = {mode.value for mode in ConfirmationMode}
CONFIRMATION_TRANSPORTS = {transport.value for transport in ConfirmationTransport}


def check_confirmation_transport(data: dict[str, Any], path: Path, issues: list[dict[str, Any]]) -> None:
    transport = data.get("confirmation_transport")
    call_id = str(data.get("interaction_ask_call_id") or "").strip()
    if not isinstance(transport, str) or transport not in CONFIRMATION_TRANSPORTS:
        issues.append(issue("error", "confirmation_transport_invalid", "confirmation_transport 必须为 user_message 或 host_tool；它与 confirmation_source 分开记录。", path))
    elif not call_id or (transport == ConfirmationTransport.USER_MESSAGE.value) != call_id.startswith("local:") or call_id == "local:":
        issues.append(issue("error", "confirmation_transport_call_id_mismatch", "聊天确认必须使用唯一 local: 记录 ID；host_tool 必须保存真实、非 local: 的宿主调用 ID。", path))


@dataclass
class ConfirmationLog:


    path: Path
    issues: list[dict[str, Any]]
    records: list[dict[str, Any]] = field(default_factory=list)
    full_revisions_by_scope: dict[tuple[str, str], set[int]] = field(default_factory=dict)
    interaction_call_ids: dict[str, tuple[str, str, str]] = field(default_factory=dict)

    def error(self, code: str, message: str) -> None:
        self.issues.append(issue("error", code, message, self.path))

    def register_interaction(self, data: dict[str, Any], stage: Any, episode_id: str, line_number: int) -> None:
        call_id = str(data.get("interaction_ask_call_id") or "").strip()
        if not call_id:
            return
        purpose_key = (
            str(data.get("confirmation_purpose") or ""),
            str(data.get("interaction_ask_result") or ""),
            f"{stage}:{episode_id}",
        )
        previous_purpose = self.interaction_call_ids.get(call_id)
        if previous_purpose is not None and previous_purpose != purpose_key:
            self.error("interaction_call_id_reused", f"用户确认记录第 {line_number} 行 interaction_ask_call_id 已被其他用途使用。")
        self.interaction_call_ids[call_id] = purpose_key


class ConfirmationModePolicy:
    def validate(self, data: dict[str, Any], line_number: int, log: ConfirmationLog) -> None:
        raise NotImplementedError


class FullConfirmationPolicy(ConfirmationModePolicy):
    def validate(self, data: dict[str, Any], line_number: int, log: ConfirmationLog) -> None:
        revision = data.get("revision")
        if isinstance(revision, int) and not isinstance(revision, bool):
            scope = (str(data.get("stage")), str(data.get("episode_id") or ""))
            log.full_revisions_by_scope.setdefault(scope, set()).add(revision)


class IncrementalConfirmationPolicy(ConfirmationModePolicy):
    def validate(self, data: dict[str, Any], line_number: int, log: ConfirmationLog) -> None:
        base_revision = data.get("base_revision")
        if not isinstance(base_revision, int) or isinstance(base_revision, bool):
            log.error("confirmation_base_revision_invalid", f"用户确认记录第 {line_number} 行 incremental 必须填写整数 base_revision。")
        else:
            scope = (str(data.get("stage")), str(data.get("episode_id") or ""))
            if base_revision not in log.full_revisions_by_scope.get(scope, set()):
                log.error("confirmation_base_revision_missing", f"用户确认记录第 {line_number} 行找不到同阶段对应的全量确认 base_revision。")
        if not isinstance(data.get("changed_artifacts"), list) or not data.get("changed_artifacts"):
            log.error("confirmation_changed_artifacts_missing", f"用户确认记录第 {line_number} 行 incremental 必须填写 changed_artifacts。")
        if not isinstance(data.get("impact_scope"), list) or not data.get("impact_scope"):
            log.error("confirmation_impact_scope_missing", f"用户确认记录第 {line_number} 行 incremental 必须填写 impact_scope。")


MODE_POLICIES: dict[str, ConfirmationModePolicy] = {
    ConfirmationMode.FULL.value: FullConfirmationPolicy(),
    ConfirmationMode.INCREMENTAL.value: IncrementalConfirmationPolicy(),
}


@dataclass(frozen=True)
class PlanningInteractionRequirement:
    purpose: str
    result: str

    def satisfied_by(self, record: dict[str, Any]) -> bool:
        return (
            record.get("confirmation_purpose") == self.purpose
            and bool(str(record.get("interaction_ask_call_id") or "").strip())
            and record.get("interaction_ask_result") == self.result
        )


PLANNING_INTERACTIONS = {
    False: PlanningInteractionRequirement("project_execution", "proceed_project"),
    True: PlanningInteractionRequirement("video_generation", "generate"),
}


class ConfirmationLogReader:
    def __init__(self, root: Path, issues: list[dict[str, Any]]):
        self.path = root / "00_制作控制/用户确认记录.jsonl"
        self.log = ConfirmationLog(self.path, issues)

    def read(
        self,
        required: bool,
        require_planning_interaction: bool = False,
        lightweight: bool = False,
    ) -> list[dict[str, Any]]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            if required:
                self.log.error("confirmation_log_missing", "阶段已确认或推进到后续阶段时必须存在用户确认记录。")
            return []
        except (OSError, UnicodeError) as exc:
            self.log.error("confirmation_log_unreadable", f"用户确认记录无法读取：{exc}")
            return []

        for line_number, line in enumerate(raw.splitlines(), start=1):
            self._parse_line(line, line_number)
        if require_planning_interaction:
            self._check_planning_interaction(PLANNING_INTERACTIONS[lightweight])
        return self.log.records

    def _parse_line(self, line: str, line_number: int) -> None:
        if not line.strip():
            self.log.error("confirmation_log_blank_line", f"用户确认记录第 {line_number} 行为空行。")
            return
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            self.log.error("confirmation_log_json_invalid", f"用户确认记录第 {line_number} 行不是有效 JSON：{exc}")
            return
        if not isinstance(data, dict):
            self.log.error("confirmation_log_row_invalid", f"用户确认记录第 {line_number} 行必须是对象。")
            return

        check_confirmation_transport(data, self.path, self.log.issues)
        stage = data.get("stage")
        episode_id = str(data.get("episode_id") or "")
        self._validate_common_fields(data, stage, episode_id, line_number)
        self.log.register_interaction(data, stage, episode_id, line_number)
        policy = MODE_POLICIES.get(data.get("confirmation_mode"))
        if policy is not None:
            policy.validate(data, line_number, self.log)
        self.log.records.append(data)

    def _validate_common_fields(self, data: dict[str, Any], stage: Any, episode_id: str, line_number: int) -> None:
        if stage not in STAGES:
            self.log.error("confirmation_stage_invalid", f"用户确认记录第 {line_number} 行 stage 无效。")
        if episode_id and not re.fullmatch(r"ep_[1-9]\d*", episode_id):
            self.log.error("confirmation_episode_id_invalid", f"用户确认记录第 {line_number} 行 episode_id 无效。")
        if stage == "planning" and episode_id:
            self.log.error("project_confirmation_has_episode", f"用户确认记录第 {line_number} 行 planning 阶段不得填写 episode_id。")
        if stage in EPISODE_STAGES - {"script"} and not episode_id:
            self.log.error("episode_confirmation_missing_episode_id", f"用户确认记录第 {line_number} 行 {stage} 阶段必须填写 episode_id。")
        if data.get("decision") != "confirmed":
            self.log.error("confirmation_decision_invalid", f"用户确认记录第 {line_number} 行 decision 必须是 confirmed。")
        if data.get("confirmation_mode") not in CONFIRMATION_MODES:
            self.log.error("confirmation_mode_invalid", f"用户确认记录第 {line_number} 行 confirmation_mode 无效。")
        if not isinstance(data.get("revision"), int) or isinstance(data.get("revision"), bool):
            self.log.error("confirmation_revision_invalid", f"用户确认记录第 {line_number} 行 revision 必须是整数。")
        if not str(data.get("user_message") or "").strip():
            self.log.error("confirmation_user_message_missing", f"用户确认记录第 {line_number} 行 user_message 不能为空。")
        if parse_iso_time(data.get("confirmed_at")) is None:
            self.log.error("confirmation_time_invalid", f"用户确认记录第 {line_number} 行 confirmed_at 必须是带时区 ISO-8601 时间。")

    def _check_planning_interaction(self, requirement: PlanningInteractionRequirement) -> None:
        planning_records = [record for record in self.log.records if record.get("stage") == "planning"]
        latest_revision = max(
            (
                record.get("revision")
                for record in planning_records
                if isinstance(record.get("revision"), int) and not isinstance(record.get("revision"), bool)
            ),
            default=None,
        )
        latest_records = [record for record in planning_records if record.get("revision") == latest_revision]
        if not any(requirement.satisfied_by(record) for record in latest_records):
            self.log.error(
                "planning_interaction_confirmation_missing",
                f"最新 planning 确认必须记录 {requirement.purpose}、真实 interaction_ask_call_id 和 {requirement.result}。",
            )


def load_confirmation_records(
    root: Path,
    issues: list[dict[str, Any]],
    required: bool,
    require_planning_interaction: bool = False,
    lightweight: bool = False,
) -> list[dict[str, Any]]:
    return ConfirmationLogReader(root, issues).read(required, require_planning_interaction, lightweight)


def has_confirmation(
    records: list[dict[str, Any]],
    stage: str,
    revision: int | None,
    episode_id: str | None = None,
) -> bool:
    for record in records:
        if record.get("stage") != stage or record.get("decision") != "confirmed":
            continue
        if revision is not None and record.get("revision") != revision:
            continue
        record_episode = str(record.get("episode_id") or "")
        if episode_id is not None and record_episode != episode_id:
            continue
        if episode_id is None and record_episode:
            continue
        if str(record.get("user_message") or "").strip():
            return True
    return False
