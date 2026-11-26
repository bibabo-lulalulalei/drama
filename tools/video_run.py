from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import workflow_series
from tools.lib import env

SKILL_ROOT = Path(__file__).resolve().parents[1]
EPISODE_RE = re.compile(r"ep_[A-Za-z0-9_-]+")


class VideoRunError(RuntimeError):
    pass


def paths(project_root: Path, episode: str) -> tuple[Path, Path]:
    if not EPISODE_RE.fullmatch(episode):
        raise VideoRunError("episode 必须形如 ep_1，且不能包含路径分隔符")
    folder = project_root.resolve() / "episodes" / episode / "04_视频片段"
    return folder / "串行执行.json", folder / "串行运行.log"


def build_command(project_root: Path, episode: str, execute: bool,
                  env_file: str | None = None) -> tuple[list[str], Path, dict]:
    root = project_root.resolve()
    run_file, log_file = paths(root, episode)
    data = json.loads(run_file.read_text(encoding="utf-8-sig"))
    if not isinstance(data.get("segments"), list) or not data["segments"]:
        raise VideoRunError("串行执行.json 必须包含非空 segments")

    authorized = []
    confirmations = []
    for entry in data["segments"]:
        segment_id = entry["segment_id"]
        operation = entry.get("operation")
        if operation == "reuse":
            continue
        if operation not in {"generate", "recover"}:
            raise VideoRunError(f"{segment_id} 的 operation 必须为 generate|recover|reuse")
        if operation == "recover" and not workflow_series._inside(
                root, entry["task_file"]).is_file():
            raise VideoRunError(f"{segment_id} 为 recover 时必须已有任务文件，禁止新 POST")
        confirmation = entry.get("confirmation_id")
        if not isinstance(confirmation, str) or not confirmation:
            raise VideoRunError(f"{segment_id} 缺少 confirmation_id")
        authorized.extend(["--authorized-segment", segment_id])
        confirmations.extend(["--confirmation", f"{segment_id}={confirmation}"])

    if sum(1 for entry in data["segments"] if entry.get("operation") == "generate") > 1:
        raise VideoRunError("每次运行只允许一个新 generate 段；真实尾态复核后再编译并确认下一段")
    by_id = {entry.get("segment_id"): entry for entry in data["segments"]}
    for entry in data["segments"]:
        if entry.get("operation") != "generate":
            continue
        for image in entry.get("images", []):
            if not isinstance(image, dict) or "previous_tail_of" not in image:
                continue
            source = by_id.get(image["previous_tail_of"])
            tail_file = str(source.get("tail_file") or "") if source else ""
            if not source or source.get("operation") != "reuse" or not tail_file \
                    or not workflow_series._inside(root, tail_file).is_file():
                raise VideoRunError("新 generate 不得使用同次运行的未来 tail；先完成上一段并登记真实尾帧")
    if not authorized:
        raise VideoRunError("没有可执行的 generate|recover 段")
    cloud_path = root / data["cloud_config"]
    cloud = json.loads(cloud_path.read_text(encoding="utf-8-sig"))
    base_url = cloud["base_url"].rstrip("/")
    power = data["power"]
    instance = power["instance_uuid"]
    power_timeout = str(power.get("timeout_s", 1200))
    poll = data.get("poll", {})
    timeout = str(poll.get("timeout_s", 900))
    interval = str(poll.get("interval_s", 10))

    manager = [sys.executable, "-I", str(SKILL_ROOT / "tools/autodl_instance.py")]
    if env_file:
        manager.extend(["--env-file", env_file])
    manager.extend(["run-managed", "--instance-uuid", instance])
    if execute:
        manager.extend(["--execute", "--confirm-power", instance])
    manager.extend([
        "--power-timeout", power_timeout,
        "--health-url", base_url + "/api/comfy/status",
        "--health-http-status", "200",
        "--health-json", "running=true",
        "--health-interval", "10",
        "--health-timeout", "300",
    ])
    child = ["--", sys.executable, "-I", str(SKILL_ROOT / "tools/workflow_series.py")]
    if env_file:
        child.extend(["--env-file", env_file])
    child.extend([
        "run", "--queue", str(run_file), "--project-root", str(root),
        *authorized, *confirmations, "--timeout", timeout, "--interval", interval,
    ])
    return manager + child, log_file, data


def run(project_root: Path, episode: str, execute: bool,
        env_file: str | None = None) -> dict:
    root = project_root.resolve()
    run_file, _ = paths(root, episode)
    preflight = workflow_series.cmd_preflight(argparse.Namespace(
        queue=str(run_file), project_root=str(root), require_ready=True,
        require_confirmed=execute))
    argv, log_file, data = build_command(root, episode, execute, env_file)
    if not execute:
        confirmation_binding = {
            key: preflight.get(key) for key in (
                "run_plan_file", "run_plan_sha256", "video_provider",
                "video_provider_adapter_version", "video_provider_adapter_sha256",
                "cloud_config_sha256",
            )
        }
        return {
            "ok": True,
            "dry_run": True,
            "network": False,
            "process_started": False,
            "run_file": str(run_file),
            "segment_count": len(data["segments"]),
            "preflight": preflight["ok"],
            **confirmation_binding,
        }
    with log_file.open("ab") as stream:
        completed = subprocess.run(
            argv, cwd=str(root), stdout=stream,
            stderr=subprocess.STDOUT, check=False)
    return {
        "ok": completed.returncode == 0,
        "dry_run": False,
        "process_started": True,
        "process_exit_code": completed.returncode,
        "run_file": str(run_file),
        "log_file": str(log_file),
        "run_state_file": data["run_state_file"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="读取固定串行执行 JSON 并启动完整视频队列")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    env.set_env_file(args.env_file)
    result = run(Path(args.project_root), args.episode, args.execute, args.env_file)
    env.emit(result)
    if result.get("process_exit_code"):
        raise SystemExit(result["process_exit_code"])


if __name__ == "__main__":
    env.run_cli(main)
