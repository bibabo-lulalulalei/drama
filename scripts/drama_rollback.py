from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

STAGES = ("planning", "script", "assets", "storyboard", "keyframes", "video", "final")
EPISODE_STAGES = STAGES[1:]
FUTURE_VALUES = {None, "pending", "invalidated"}
EPISODE_ID = re.compile(r"ep_[1-9]\d*")


def safe_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _episode_number(episode_id: str) -> int:
    return int(episode_id.split("_", 1)[1])


def _statuses(episode_state) -> dict | None:
    if not isinstance(episode_state, dict):
        return None
    value = episode_state.get("stage_status")
    return value if isinstance(value, dict) else None


def _validate_request(state, to_stage, episode_id, workflow_mode) -> bool:
    if not isinstance(state, dict):
        raise ValueError("制作状态.json must contain an object")
    if to_stage not in STAGES:
        raise ValueError(f"unknown stage: {to_stage}")
    if episode_id is not None:
        if to_stage not in EPISODE_STAGES:
            raise ValueError("episode-scoped rollback only supports script through final")
        if not EPISODE_ID.fullmatch(episode_id):
            raise ValueError("--episode must use ep_N with a positive integer")
    phases = state.get("phases")
    if not isinstance(phases, dict):
        raise ValueError("制作状态.json.phases must be an object")
    episodes = state.get("episodes")
    if isinstance(episodes, dict) and any(
        not isinstance(key, str) or not EPISODE_ID.fullmatch(key) for key in episodes
    ):
        raise ValueError("制作状态.json.episodes contains an invalid episode ID")
    return workflow_mode == "lightweight" or (
        workflow_mode is None
        and any(phases.get(stage) == "merged" for stage in STAGES[1:-1])
    )


def _lightweight_repair(state: dict, episode_id: str | None) -> dict:
    if state["phases"].get("planning") != "confirmed":
        raise ValueError("lightweight rollback requires confirmed planning; return to planning first")
    episodes = state.get("episodes")
    if (
        not isinstance(episodes, dict)
        or set(episodes) != {"ep_1"}
        or episode_id not in {None, "ep_1"}
    ):
        raise ValueError("lightweight rollback requires exactly ep_1")
    if _statuses(episodes["ep_1"]) is None:
        raise ValueError("ep_1.stage_status must be an object")

    updated = copy.deepcopy(state)
    updated.update(
        revision=int(state.get("revision", 0) or 0) + 1,
        current_stage="final",
        current_episode="ep_1",
    )
    for stage in STAGES[1:-1]:
        updated["phases"][stage] = "merged"
        updated["episodes"]["ep_1"]["stage_status"][stage] = "merged"
    updated["phases"]["final"] = "in_progress"
    updated["episodes"]["ep_1"]["stage_status"]["final"] = "in_progress"
    return updated


def _validate_episode_scope(state, to_stage, episode_id, cascade_later_episodes) -> None:
    episodes = state.get("episodes")
    if episode_id is None:
        if to_stage in STAGES[2:]:
            raise ValueError("assets through final rollback requires --episode ep_N")
        return
    if not isinstance(episodes, dict) or episode_id not in episodes:
        raise ValueError(f"unknown episode: {episode_id}")

    current_episode = str(state.get("current_episode") or "")
    if EPISODE_ID.fullmatch(current_episode) and _episode_number(episode_id) > _episode_number(current_episode):
        raise ValueError(f"cannot rollback future episode before it becomes current: {episode_id}")
    statuses = _statuses(episodes[episode_id])
    if statuses is not None and statuses.get(to_stage) in FUTURE_VALUES:
        raise ValueError(f"cannot rollback unstarted stage: {episode_id}.{to_stage}")

    target_number = _episode_number(episode_id)
    started_later = [
        item_id
        for item_id, episode_state in episodes.items()
        if _episode_number(item_id) > target_number
        and _statuses(episode_state) is not None
        and any(_statuses(episode_state).get(stage) not in FUTURE_VALUES for stage in EPISODE_STAGES)
    ]
    if started_later and not cascade_later_episodes:
        raise ValueError(
            "later episodes already progressed; rerun with --cascade-later-episodes "
            f"to invalidate them explicitly: {started_later}"
        )


def _update_project_phases(updated: dict, to_stage: str, episode_id: str | None) -> None:
    target_index = STAGES.index(to_stage)
    target_status = "awaiting_confirmation" if to_stage == "planning" else "in_progress"
    affected = STAGES[target_index:] if episode_id is None else tuple(
        stage for stage in STAGES[2:] if STAGES.index(stage) >= target_index
    )
    for stage in affected:
        updated["phases"][stage] = target_status if stage == to_stage else "invalidated"


def _rollback_episode(
    episode_state,
    *,
    item_id: str,
    to_stage: str,
    episode_id: str | None,
    cascade_later_episodes: bool,
):
    statuses = _statuses(episode_state)
    if statuses is None:
        return episode_state
    next_state = dict(episode_state)
    statuses = dict(statuses)
    target_index = STAGES.index(to_stage)

    if episode_id is not None and item_id != episode_id:
        if cascade_later_episodes and _episode_number(item_id) > _episode_number(episode_id):
            for stage in EPISODE_STAGES:
                if stage in statuses and statuses[stage] not in {"pending", "invalidated"}:
                    statuses[stage] = "invalidated"
    else:


        for stage in STAGES[target_index:]:
            if stage != "planning" and stage in statuses:
                statuses[stage] = (
                    "in_progress" if episode_id is not None and stage == to_stage else "invalidated"
                )
    next_state["stage_status"] = statuses
    return next_state


def rollback_state(
    state: dict,
    to_stage: str,
    episode_id: str | None = None,
    cascade_later_episodes: bool = False,
    workflow_mode: str | None = None,
) -> dict:
    lightweight = _validate_request(state, to_stage, episode_id, workflow_mode)
    if lightweight and to_stage != "planning":
        return _lightweight_repair(state, episode_id)
    _validate_episode_scope(state, to_stage, episode_id, cascade_later_episodes)

    updated = copy.deepcopy(state)
    updated.update(
        revision=int(state.get("revision", 0) or 0) + 1,
        current_stage=to_stage,
        current_episode=episode_id,
    )
    _update_project_phases(updated, to_stage, episode_id)
    episodes = state.get("episodes")
    if isinstance(episodes, dict):
        updated["episodes"] = {
            item_id: _rollback_episode(
                episode_state,
                item_id=item_id,
                to_stage=to_stage,
                episode_id=episode_id,
                cascade_later_episodes=cascade_later_episodes,
            )
            for item_id, episode_state in episodes.items()
        }
    return updated


def append_log(
    project_root: Path,
    to_stage: str,
    episode_id: str | None,
    cascade_later_episodes: bool,
    reason: str,
    state_path: Path,
    input_revision: int,
) -> None:
    log_path = project_root / "00_制作控制/操作日志.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    relative_state = str(state_path.relative_to(project_root))
    record = {
        "operation_id": f"rollback_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}",
        "input_revision": input_revision,
        "stage": to_stage,
        "target_ids": [item for item in (episode_id, to_stage) if item],
        "tool": "drama_rollback.py",
        "tool_call_id": "",
        "params_summary": {
            "to_stage": to_stage,
            "episode_id": episode_id,
            "cascade_later_episodes": cascade_later_episodes,
            "reason": reason,
        },
        "attempt": 1,
        "status": "succeeded",
        "outputs": [relative_state],
        "output_metadata": {"state_path": relative_state},
        "tool_calls": [],
        "recovery_action": "downstream stages invalidated; regenerate affected artifacts before confirmation",
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def _load_updated_state(project_root: Path, args) -> tuple[dict, dict]:
    state_path = project_root / "00_制作控制/制作状态.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    plan_path = project_root / "00_制作控制/drama_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.is_file() else {}
    objective = plan.get("objective", {}) if isinstance(plan, dict) else {}
    workflow_mode = objective.get("workflow_mode") if isinstance(objective, dict) else None
    updated = rollback_state(
        state, args.to_stage, args.episode, args.cascade_later_episodes, workflow_mode
    )
    return state, updated


def _commit(project_root: Path, state_path: Path, state: dict, updated: dict, args) -> tuple[int, dict | None]:
    try:
        safe_write_json(state_path, updated)
        append_log(
            project_root,
            updated["current_stage"],
            updated["current_episode"],
            args.cascade_later_episodes,
            args.reason,
            state_path,
            int(state.get("revision", 0) or 0),
        )
    except (OSError, UnicodeError) as exc:
        try:
            safe_write_json(state_path, state)
        except (OSError, UnicodeError) as restore_exc:
            return 3, {
                "error": "rollback_partial_commit",
                "message": str(exc),
                "restore_error": str(restore_exc),
            }
        return 2, {"error": "rollback_log_failed", "message": str(exc), "state_restored": True}
    return 0, None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rollback drama stage state.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--to-stage", required=True, choices=STAGES)
    parser.add_argument("--episode", help="limit rollback to one ep_N; valid for script through final")
    parser.add_argument("--cascade-later-episodes", action="store_true", help="explicitly invalidate already-started later episodes")
    parser.add_argument("--reason", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    state_path = project_root / "00_制作控制/制作状态.json"
    try:
        state, updated = _load_updated_state(project_root, args)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": "rollback_failed", "message": str(exc)}, ensure_ascii=False))
        return 2

    changed = state != updated
    if changed and not args.dry_run:
        code, error = _commit(project_root, state_path, state, updated, args)
        if error is not None:
            print(json.dumps(error, ensure_ascii=False))
            return code

    print(json.dumps({
        "status": "dry_run" if args.dry_run else "updated",
        "changed": changed,
        "to_stage": updated["current_stage"],
        "requested_to_stage": args.to_stage,
        "episode_id": updated["current_episode"],
        "cascade_later_episodes": args.cascade_later_episodes,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
