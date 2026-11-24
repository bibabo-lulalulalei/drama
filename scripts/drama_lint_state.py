from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Any

try:
    from .drama_lint_confirmations import has_confirmation, load_confirmation_records
    from .drama_lint_domain import (
        CURRENT_STAGE_ACTIVE_VALUES,
        EPISODE_STAGES,
        H3_CAPABILITIES,
        MERGEABLE_LIGHTWEIGHT_STAGES,
        STAGES,
        STATUS_VALUES,
        ProductionPlan,
        episode_dirs,
        issue,
        load_json,
    )
except ImportError:
    from drama_lint_confirmations import has_confirmation, load_confirmation_records
    from drama_lint_domain import (
        CURRENT_STAGE_ACTIVE_VALUES,
        EPISODE_STAGES,
        H3_CAPABILITIES,
        MERGEABLE_LIGHTWEIGHT_STAGES,
        STAGES,
        STATUS_VALUES,
        ProductionPlan,
        episode_dirs,
        issue,
        load_json,
    )


class ProductionScope(str, Enum):
    PROJECT = "project"
    EPISODE = "episode"
    UNSUPPORTED = "unsupported"


class EpisodePosition(Enum):
    PREVIOUS = -1
    CURRENT = 0
    FUTURE = 1

    @classmethod
    def compare(cls, episode_position: int, active_position: int) -> "EpisodePosition":
        return cls((episode_position > active_position) - (episode_position < active_position))


@dataclass(frozen=True)
class StateContext:
    root: Path
    path: Path
    state: dict[str, Any]
    plan: ProductionPlan
    current: Any
    current_episode: Any
    phases: dict[str, Any]
    episode_ids: list[str]
    scope: ProductionScope

    @classmethod
    def create(cls, root: Path, path: Path, state: dict[str, Any], plan: Any) -> "StateContext":
        current = state.get("current_stage")
        current_episode = state.get("current_episode")
        if current == "planning" or (current == "script" and current_episode in {None, ""}):
            scope = ProductionScope.PROJECT
        elif current in EPISODE_STAGES:
            scope = ProductionScope.EPISODE
        else:
            scope = ProductionScope.UNSUPPORTED
        return cls(
            root=root,
            path=path,
            state=state,
            plan=ProductionPlan(plan),
            current=current,
            current_episode=current_episode,
            phases=state["phases"],
            episode_ids=[episode_id for episode_id, _ in episode_dirs(root)],
            scope=scope,
        )

    @property
    def revision(self) -> int | None:
        return self.plan.revision(self.state)

    @property
    def lightweight(self) -> bool:
        return self.plan.is_lightweight

    @property
    def lightweight_valid(self) -> bool:
        return self.plan.lightweight_valid

    @property
    def target(self) -> str | None:
        return self.plan.target

    @property
    def allowed_script_statuses(self) -> set[str]:
        return {"confirmed", "merged"} if self.lightweight_valid else {"confirmed"}

    def completed_statuses(self, stage: str) -> set[str]:
        if self.lightweight_valid and stage in MERGEABLE_LIGHTWEIGHT_STAGES:
            return {"confirmed", "merged"}
        return {"confirmed"}

    def merge_is_valid(self, stage: str) -> bool:
        return self.lightweight_valid and stage in MERGEABLE_LIGHTWEIGHT_STAGES


class StateReporter:
    def __init__(self, path: Path, issues: list[dict[str, Any]]):
        self.path = path
        self.issues = issues

    def error(self, code: str, message: str) -> None:
        self.issues.append(issue("error", code, message, self.path))


class EpisodeProgressRule:
    def validate(
        self,
        context: StateContext,
        reporter: StateReporter,
        episode_id: str,
        statuses: dict[str, Any],
    ) -> None:
        return


class BeforePlanningRule(EpisodeProgressRule):
    def validate(self, context: StateContext, reporter: StateReporter, episode_id: str, statuses: dict[str, Any]) -> None:
        for stage in EPISODE_STAGES:
            value = statuses.get(stage)
            if value is not None and value not in {"pending", "invalidated"}:
                reporter.error("episode_stage_before_planning_confirmed", f"项目仍在 planning，{episode_id}.{stage} 只能是 pending 或 invalidated。")


class BeforeScriptRule(EpisodeProgressRule):
    def validate(self, context: StateContext, reporter: StateReporter, episode_id: str, statuses: dict[str, Any]) -> None:
        if statuses.get("script") not in {"pending", "invalidated"}:
            reporter.error("episode_script_started_before_global_confirmation", f"{episode_id}.script 在项目级故事包确认前只能是 pending 或 invalidated。")
        for stage in STAGES[2:]:
            value = statuses.get(stage)
            if value is not None and value not in {"pending", "invalidated"}:
                reporter.error("episode_stage_before_script_confirmed", f"项目级故事包尚未确认，{episode_id}.{stage} 只能是 pending 或 invalidated。")


class PreviousEpisodeRule(EpisodeProgressRule):
    def validate(self, context: StateContext, reporter: StateReporter, episode_id: str, statuses: dict[str, Any]) -> None:
        completed_through = STAGES.index(context.target) if context.target in EPISODE_STAGES else STAGES.index("final")
        for stage in EPISODE_STAGES:
            if STAGES.index(stage) <= completed_through:
                if statuses.get(stage) not in context.completed_statuses(stage):
                    reporter.error("previous_episode_incomplete", f"{episode_id}.{stage} 必须完成后才能推进 {context.current_episode}。")
            elif statuses.get(stage) not in {"pending", "invalidated"}:
                reporter.error("previous_episode_beyond_target", f"{episode_id}.{stage} 超出 target_stage={context.target}，只能是 pending 或 invalidated。")


class FutureEpisodeRule(EpisodeProgressRule):
    def validate(self, context: StateContext, reporter: StateReporter, episode_id: str, statuses: dict[str, Any]) -> None:
        if statuses.get("script") not in {"pending", "invalidated"}:
            reporter.error("future_episode_script_started_early", f"{episode_id}.script 在该集开始制作前只能是 pending 或 invalidated。")
        for stage in STAGES[2:]:
            if statuses.get(stage) not in {"pending", "invalidated"}:
                reporter.error("future_episode_started_early", f"{episode_id}.{stage} 在 {context.current_episode} 达到目标前只能是 pending 或 invalidated。")


class CurrentEpisodeRule(EpisodeProgressRule):
    def validate(self, context: StateContext, reporter: StateReporter, episode_id: str, statuses: dict[str, Any]) -> None:
        current_index = STAGES.index(context.current)
        if context.current != "script" and statuses.get("script") not in context.allowed_script_statuses:
            reporter.error("current_episode_script_incomplete", f"{episode_id}.script 必须在后续生产前确认为 confirmed；合法轻量模式可为 merged。")
        episode_position = context.episode_ids.index(episode_id)
        current_is_last_episode = episode_position == len(context.episode_ids) - 1
        for stage in EPISODE_STAGES:
            value = statuses.get(stage)
            stage_index = STAGES.index(stage)
            if stage_index < current_index and value not in {"confirmed", "merged"}:
                reporter.error("episode_phase_order_invalid", f"{episode_id}.{stage} 应先完成后再进入 {context.current}。")
            if stage_index > current_index and value not in {"pending", "invalidated"}:
                reporter.error("episode_future_phase_status_invalid", f"{episode_id}.{stage} 晚于当前集 current_stage={context.current}，只能是 pending 或 invalidated。")
            if stage_index == current_index:
                allowed_current = set(CURRENT_STAGE_ACTIVE_VALUES)
                if current_is_last_episode and context.current in {"final", context.target}:
                    allowed_current.add("confirmed")
                if context.merge_is_valid(stage):
                    allowed_current.add("merged")
                if value not in allowed_current:
                    reporter.error("episode_current_phase_status_invalid", f"{episode_id}.{stage} 是当前集阶段，状态不能是 {value}。")


class ProductionScopePolicy:
    def validate_project(self, context: StateContext, reporter: StateReporter) -> None:
        return

    def requires_confirmation_log(self, context: StateContext) -> bool:
        return False

    def episode_rule(self, context: StateContext, episode_id: str) -> EpisodeProgressRule:
        return EpisodeProgressRule()

    def validate_aggregate_alignment(self, context: StateContext, reporter: StateReporter, episodes: dict[str, Any]) -> None:
        return


class UnsupportedScopePolicy(ProductionScopePolicy):
    pass


class ProjectScopePolicy(ProductionScopePolicy):
    def validate_project(self, context: StateContext, reporter: StateReporter) -> None:
        if context.current_episode not in {None, ""}:
            reporter.error("current_episode_must_be_empty", f"current_stage={context.current} 时 current_episode 必须为空。")
        current_index = STAGES.index(context.current)
        for index, stage in enumerate(STAGES):
            value = context.phases.get(stage)
            if index < current_index and value not in {"confirmed", "merged"}:
                reporter.error("phase_order_invalid", f"{stage} 应先完成后再进入 {context.current}。")
            if index > current_index and value not in {"pending", "invalidated"}:
                reporter.error("future_phase_status_invalid", f"{stage} 晚于 current_stage={context.current}，只能是 pending 或 invalidated。")
            if index == current_index:
                allowed_current = set(CURRENT_STAGE_ACTIVE_VALUES)
                if context.current == "final" or context.current == context.target:
                    allowed_current.add("confirmed")
                if context.merge_is_valid(stage):
                    allowed_current.add("merged")
                if value not in allowed_current:
                    reporter.error("current_phase_status_invalid", f"{stage} 是 current_stage，状态不能是 {value}。")
            if value == "merged" and not context.merge_is_valid(stage):
                reporter.error("phase_merged_invalid", f"{stage} 不能标记为 merged。")

    def requires_confirmation_log(self, context: StateContext) -> bool:
        return STAGES.index(context.current) > 0

    def episode_rule(self, context: StateContext, episode_id: str) -> EpisodeProgressRule:
        if context.current == "planning":
            return BeforePlanningRule()
        return BeforeScriptRule()


class EpisodeScopePolicy(ProductionScopePolicy):
    EPISODE_RULES = {
        EpisodePosition.PREVIOUS: PreviousEpisodeRule,
        EpisodePosition.CURRENT: CurrentEpisodeRule,
        EpisodePosition.FUTURE: FutureEpisodeRule,
    }

    def validate_project(self, context: StateContext, reporter: StateReporter) -> None:
        if context.current_episode not in context.episode_ids:
            reporter.error("current_episode_invalid", "逐集生产阶段必须把 current_episode 指向计划内分集。")
        if context.target in STAGES and STAGES.index(context.current) > STAGES.index(context.target):
            reporter.error("current_stage_beyond_target", f"current_stage={context.current} 不得晚于 objective.target_stage={context.target}。")
        if context.phases.get("planning") != "confirmed":
            reporter.error("project_prerequisite_not_confirmed", "进入逐集生产前 phases.planning 必须为 confirmed。")
        if context.phases.get("script") not in context.allowed_script_statuses:
            reporter.error("project_prerequisite_not_confirmed", "进入逐集生产前项目级 phases.script 必须为 confirmed；合法轻量模式可为 merged。")
        for stage in STAGES[2:]:
            if context.phases.get(stage) == "merged" and not context.merge_is_valid(stage):
                reporter.error("phase_merged_invalid", f"{stage} 不能标记为 merged。")

    def requires_confirmation_log(self, context: StateContext) -> bool:
        return True

    def episode_rule(self, context: StateContext, episode_id: str) -> EpisodeProgressRule:
        if context.current_episode not in context.episode_ids:
            return EpisodeProgressRule()
        episode_position = context.episode_ids.index(episode_id) if episode_id in context.episode_ids else -1
        active_position = context.episode_ids.index(str(context.current_episode))
        position = EpisodePosition.compare(episode_position, active_position)
        return self.EPISODE_RULES[position]()

    def validate_aggregate_alignment(self, context: StateContext, reporter: StateReporter, episodes: dict[str, Any]) -> None:
        if context.current_episode not in episodes:
            return
        current_episode = episodes[context.current_episode]
        current_statuses = current_episode.get("stage_status") if isinstance(current_episode, dict) else {}
        current_index = STAGES.index(context.current)
        for stage in STAGES[2:]:
            phase_value = context.phases.get(stage)
            stage_index = STAGES.index(stage)
            completed_values = context.completed_statuses(stage)
            all_completed = all(
                isinstance(episode_state, dict)
                and isinstance(episode_state.get("stage_status"), dict)
                and episode_state["stage_status"].get(stage) in completed_values
                for episode_state in episodes.values()
            )
            any_completed = any(
                isinstance(episode_state, dict)
                and isinstance(episode_state.get("stage_status"), dict)
                and episode_state["stage_status"].get(stage) in completed_values
                for episode_state in episodes.values()
            )
            if all_completed:
                valid_merged = context.merge_is_valid(stage) and phase_value == "merged"
                if phase_value != "confirmed" and not valid_merged:
                    reporter.error("aggregate_phase_status_mismatch", f"phases.{stage} 必须反映全部分集已完成。")
            elif stage == context.current:
                current_value = current_statuses.get(stage) if isinstance(current_statuses, dict) else None
                if phase_value != current_value:
                    reporter.error("aggregate_current_phase_mismatch", f"phases.{stage} 必须与 {context.current_episode}.{stage} 当前活动状态一致。")
            elif stage_index > current_index and phase_value not in ({"pending", "invalidated", "in_progress"} if any_completed else {"pending", "invalidated"}):
                reporter.error("aggregate_future_phase_started", f"phases.{stage} 与已完成分集的聚合状态不一致。")
            elif stage_index < current_index and phase_value not in {"in_progress", "confirmed", "merged"}:
                reporter.error("aggregate_previous_phase_invalid", f"phases.{stage} 已有分集完成但尚未全量完成，必须保持 in_progress 或合法完成态。")


SCOPE_POLICIES: dict[ProductionScope, ProductionScopePolicy] = {
    ProductionScope.PROJECT: ProjectScopePolicy(),
    ProductionScope.EPISODE: EpisodeScopePolicy(),
    ProductionScope.UNSUPPORTED: UnsupportedScopePolicy(),
}


class LightweightStateRule:
    def validate(self, context: StateContext, reporter: StateReporter) -> None:
        if context.lightweight and not context.lightweight_valid:
            reporter.error("lightweight_scope_invalid", f"lightweight 只允许单集单条 H3 视频，总时长必须为 {H3_CAPABILITIES['min_duration_s']}-{H3_CAPABILITIES['max_duration_s']} 整数秒。")
        if not context.lightweight_valid or context.phases.get("planning") != "confirmed":
            return
        if context.current != "final" or context.current_episode != "ep_1":
            reporter.error("lightweight_current_stage_invalid", "轻量规划确认后必须保持 current_stage=final、current_episode=ep_1；内部返修不建立独立中间阶段。")
        for stage in sorted(MERGEABLE_LIGHTWEIGHT_STAGES):
            if context.phases.get(stage) != "merged":
                reporter.error("lightweight_merged_stage_required", f"轻量规划确认后 phases.{stage} 必须保持 merged。")


class EpisodeRecordValidator:
    def __init__(
        self,
        context: StateContext,
        reporter: StateReporter,
        confirmations: list[dict[str, Any]],
        progress_rule: EpisodeProgressRule,
    ):
        self.context = context
        self.reporter = reporter
        self.confirmations = confirmations
        self.progress_rule = progress_rule

    def validate(self, episode_id: str, episode_state: Any) -> None:
        if not re.fullmatch(r"ep_[1-9]\d*", str(episode_id)):
            self.reporter.error("episode_id_invalid", f"分集 ID 无效：{episode_id}")
        statuses = episode_state.get("stage_status") if isinstance(episode_state, dict) else None
        if not isinstance(statuses, dict):
            self.reporter.error("episode_stage_statuses_invalid", f"{episode_id}.stage_status 必须是对象。")
            return
        self._validate_lightweight(episode_id, statuses)
        self._validate_statuses(episode_id, statuses)
        self.progress_rule.validate(self.context, self.reporter, episode_id, statuses)
        self._validate_confirmations(episode_id, statuses)

    def _validate_lightweight(self, episode_id: str, statuses: dict[str, Any]) -> None:
        if not self.context.lightweight_valid or self.context.phases.get("planning") != "confirmed":
            return
        for stage in sorted(MERGEABLE_LIGHTWEIGHT_STAGES):
            if statuses.get(stage) != "merged":
                self.reporter.error("lightweight_episode_merged_stage_required", f"轻量规划确认后 {episode_id}.{stage} 必须保持 merged。")

    def _validate_statuses(self, episode_id: str, statuses: dict[str, Any]) -> None:
        missing_stages = [stage for stage in EPISODE_STAGES if stage not in statuses]
        if missing_stages:
            self.reporter.error("episode_stage_statuses_missing", f"{episode_id}.stage_status 缺少阶段：{missing_stages}")
        for stage, value in statuses.items():
            if stage in EPISODE_STAGES and value not in STATUS_VALUES:
                self.reporter.error("episode_stage_status_invalid", f"{episode_id}.{stage} 状态无效。")
            if stage in EPISODE_STAGES and value == "merged" and not self.context.merge_is_valid(stage):
                self.reporter.error("episode_phase_merged_invalid", f"{episode_id}.{stage} 不能标记为 merged。")

    def _validate_confirmations(self, episode_id: str, statuses: dict[str, Any]) -> None:
        for stage in EPISODE_STAGES:
            if statuses.get(stage) != "confirmed":
                continue
            if stage == "script":
                if not has_confirmation(self.confirmations, "script", None, episode_id):
                    self.reporter.error("episode_script_confirmation_missing", f"{episode_id}.script 已 confirmed，但缺少绑定该集的详细剧本确认记录。")
                continue
            required_revision = self.context.revision if episode_id == self.context.current_episode and stage == self.context.current else None
            if not has_confirmation(self.confirmations, stage, required_revision, episode_id):
                self.reporter.error("episode_confirmation_missing", f"{episode_id}.{stage} 已 confirmed，但缺少绑定该集的有效确认记录。")


class StateValidator:
    def __init__(self, root: Path, plan: Any, issues: list[dict[str, Any]]):
        self.root = root
        self.plan = plan
        self.issues = issues
        self.path = root / "00_制作控制/制作状态.json"
        self.reporter = StateReporter(self.path, issues)

    def validate(self) -> None:
        state = load_json(self.path, self.issues, required=False)
        if not isinstance(state, dict):
            return
        current = state.get("current_stage")
        phases = state.get("phases")
        if current not in STAGES:
            self.reporter.error("current_stage_invalid", "current_stage 不是有效阶段。")
        if not isinstance(phases, dict):
            self.reporter.error("phases_invalid", "phases 必须是对象。")
            return

        context = StateContext.create(self.root, self.path, state, self.plan)
        if not context.plan.has_valid_target:
            self.reporter.error("target_stage_invalid", "drama_plan.objective.target_stage 必须是有效阶段。")
        for stage in STAGES:
            value = phases.get(stage)
            if value not in STATUS_VALUES:
                self.reporter.error("phase_status_invalid", f"{stage} 状态无效。")

        policy = SCOPE_POLICIES[context.scope]
        policy.validate_project(context, self.reporter)
        LightweightStateRule().validate(context, self.reporter)
        needs_confirmations = any(phases.get(stage) == "confirmed" for stage in STAGES) or policy.requires_confirmation_log(context)
        confirmations = load_confirmation_records(
            self.root,
            self.issues,
            needs_confirmations,
            require_planning_interaction=context.target in {"video", "final"},
            lightweight=context.lightweight_valid,
        )
        self._validate_project_confirmations(context, confirmations)

        episodes = state.get("episodes")
        if not isinstance(episodes, dict):
            self.reporter.error("episode_states_invalid", "制作状态.json.episodes 必须是对象并覆盖全部计划分集。")
            return
        self._validate_episode_coverage(context, episodes)
        for episode_id, episode_state in episodes.items():
            EpisodeRecordValidator(context, self.reporter, confirmations, policy.episode_rule(context, episode_id)).validate(episode_id, episode_state)
        self._validate_aggregate_completion(context, episodes)
        policy.validate_aggregate_alignment(context, self.reporter, episodes)

    def _validate_project_confirmations(self, context: StateContext, confirmations: list[dict[str, Any]]) -> None:
        for stage in ("planning", "script"):
            value = context.phases.get(stage)
            required_revision = context.revision if stage == context.current and context.current_episode in {None, ""} else None
            if value == "confirmed" and not has_confirmation(confirmations, stage, required_revision):
                detail = "同阶段、同 revision" if stage == context.current else "同阶段"
                self.reporter.error("phase_confirmation_missing", f"{stage} 已 confirmed，但缺少{detail}的有效用户确认记录。")

    def _validate_episode_coverage(self, context: StateContext, episodes: dict[str, Any]) -> None:
        state_episode_ids = set(episodes)
        expected_episode_ids = set(context.episode_ids)
        if state_episode_ids == expected_episode_ids:
            return
        missing = sorted(expected_episode_ids - state_episode_ids)
        extra = sorted(state_episode_ids - expected_episode_ids)
        if missing:
            self.reporter.error("episode_states_missing", f"制作状态.json.episodes 缺少计划分集：{missing}")
        if extra:
            self.reporter.error("episode_states_unplanned", f"制作状态.json.episodes 包含计划外分集：{extra}")

    def _validate_aggregate_completion(self, context: StateContext, episodes: dict[str, Any]) -> None:
        for stage in STAGES[2:]:
            if context.phases.get(stage) != "confirmed":
                continue
            stage_values = [
                episode_state.get("stage_status", {}).get(stage)
                for episode_state in episodes.values()
                if isinstance(episode_state, dict) and isinstance(episode_state.get("stage_status"), dict)
            ]
            if not stage_values or any(value not in {"confirmed", "merged"} for value in stage_values):
                self.reporter.error("aggregate_phase_confirmed_early", f"phases.{stage} 只有在全部分集该阶段完成后才能写 confirmed。")


def check_state(root: Path, plan: Any, issues: list[dict[str, Any]]) -> None:
    StateValidator(root, plan, issues).validate()
