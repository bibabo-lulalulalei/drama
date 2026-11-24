from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import media
from tools.lib import env, json_state, video_providers
from tools.lib.media_facts import media_duration, sha256_file


class SeriesError(RuntimeError):
    pass


class SegmentPhase(str, Enum):
    REUSED = "reused"
    COMPLETE = "complete"
    TAIL_READY = "tail_ready"
    REUSED_TAIL_READY = "reused_tail_ready"


class QueueRunStatus(str, Enum):
    COMPLETE = "complete"
    STOPPED = "stopped"


@dataclass(frozen=True)
class TailDependency:
    root: Path
    target_segment_id: str
    source_id: str
    source: dict
    run_state: dict

    @classmethod
    def resolve(cls, root: Path, entry: dict, source_id: str,
                by_id: dict, run_state: dict) -> "TailDependency":
        source = by_id.get(source_id)
        if not source:
            raise SeriesError(f"{entry['segment_id']} 的上一段 {source_id} 不在队列中")
        return cls(root, entry["segment_id"], source_id, source, run_state)

    def verified_path(self) -> str:
        tail = _inside(self.root, self.source["tail_file"])
        receipt = self.run_state.get("segments", {}).get(self.source_id, {})
        tail_fact = receipt.get("tail", {})
        source_output = _inside(self.root, self.source["output_file"])
        if not tail.is_file() or not source_output.is_file():
            raise SeriesError(f"等待真实尾帧: {self.source_id} -> {tail}；禁止用计划图代替")
        if tail_fact.get("file") != _relative(self.root, tail) \
                or tail_fact.get("sha256") != sha256_file(tail) \
                or tail_fact.get("source_video_sha256") != sha256_file(source_output) \
                or receipt.get("output_sha256") != sha256_file(source_output):
            raise SeriesError(
                f"{self.source_id} 尾帧来源或哈希未闭合，禁止提交 {self.target_segment_id}")
        return str(tail)


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须是对象: {path}")
    return value


def _inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError(f"队列只接受项目内相对路径: {relative!r}")
    root = root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"队列路径越出项目根目录: {relative}") from None
    return path


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _load_queue(queue_file: Path, project_root: Path | None = None) -> tuple[Path, dict]:
    root = (project_root or queue_file.parent).resolve()
    queue = _read(queue_file)
    if queue.get("schema_version") != "1.0" or not isinstance(queue.get("segments"), list):
        raise ValueError("队列 schema_version 必须为 1.0 且包含 segments")
    if not queue["segments"]:
        raise ValueError("空 SEG 队列")
    return root, queue


def _images(root: Path, entry: dict, by_id: dict, run_state: dict) -> list[str]:
    result = []
    for item in entry.get("images", []):
        if "previous_tail_of" in item:
            dependency = TailDependency.resolve(
                root, entry, item["previous_tail_of"], by_id, run_state)
            result.append(dependency.verified_path())
        else:
            result.append(str(_inside(root, item["file"])))
    return result


def _verify_task_inputs(provider, task_file: Path, root: Path, entry: dict,
                        images: list[str]) -> None:
    expected = images + [str(_inside(root, value)) for value in entry.get("audio", [])]
    prompt = _inside(root, entry["prompt_file"]).read_text(encoding="utf-8")
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    provider.verify_task_inputs(
        str(task_file), prompt_sha256=prompt_sha256, expected_inputs=expected)


def _resolve_provider(root: Path, queue: dict):
    config_path = _inside(root, queue["cloud_config"])
    raw_config = _read(config_path)
    provider = video_providers.select_adapter(queue, raw_config)
    provider.load_config(str(config_path))
    binding = video_providers.adapter_binding(provider)
    binding["cloud_config_sha256"] = sha256_file(config_path)
    return provider, binding, config_path


def _fixed_files(root: Path, entry: dict) -> list[Path]:
    files = [_inside(root, entry["prompt_file"])]
    files.extend(_inside(root, item["file"]) for item in entry.get("images", []) if "file" in item)
    files.extend(_inside(root, value) for value in entry.get("audio", []))
    return files


def _audio_duration_total(root: Path, entry: dict, fail) -> float:
    audio = entry.get("audio", [])
    if not isinstance(audio, list):
        fail("audio", "必须是项目相对音频路径数组")
        return 0.0
    total = 0.0
    for value in audio:
        try:
            path = _inside(root, value)
        except ValueError as exc:
            fail("audio_file", str(exc))
            continue
        if not path.is_file():
            continue
        try:
            duration = media_duration(str(path))
        except ValueError as exc:
            fail("audio_duration", f"{value}: {exc}")
            continue
        if not 2 <= duration <= 15:
            fail("audio_duration", f"{value} 实际 {duration:.6f} 秒，单项须为 2-15 秒")
        total += duration
    if total > 15 + 1e-6:
        fail("audio_duration_total", f"实际合计 {total:.6f} 秒，H3 上限为 15 秒")
    return total


def cmd_preflight(args) -> dict:
    queue_file = Path(args.queue).resolve()
    root, queue = _load_queue(queue_file, Path(args.project_root) if args.project_root else None)
    issues: list[dict] = []
    seen: set[str] = set()
    by_id: dict[str, dict] = {}
    rows = []
    previous_id = None
    provider = None
    provider_binding = {}
    try:
        provider, provider_binding, _ = _resolve_provider(root, queue)
    except (KeyError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        issues.append({"segment_id": None, "code": "video_provider", "detail": str(exc)})
    for index, entry in enumerate(queue["segments"]):
        segment_id = entry.get("segment_id")
        local = []

        def fail(code: str, detail: str) -> None:
            local.append({"segment_id": segment_id, "code": code, "detail": detail})

        if not isinstance(segment_id, str) or not segment_id or segment_id in seen:
            fail("segment_id", "缺失或重复")
            continue
        seen.add(segment_id)
        by_id[segment_id] = entry
        duration = entry.get("duration_s")
        if not isinstance(duration, int) or isinstance(duration, bool) or not 4 <= duration <= 15:
            fail("duration_s", "必须为 H3 的 4-15 整数秒")
        images = entry.get("images")
        if not isinstance(images, list) or not images:
            fail("images", "Ref2VA 至少需要一个图片输入")
            images = []
        tail_refs = [item.get("previous_tail_of") for item in images if "previous_tail_of" in item]
        if index == 0 and tail_refs:
            fail("previous_tail", "首段不能引用本队列内上一段")
        if index > 0:
            if tail_refs != [previous_id] or images[0].get("previous_tail_of") != previous_id:
                fail("previous_tail", f"连续段第一个图片槽位必须且只能引用 {previous_id}")
            if not entry.get("tail_file"):
                fail("tail_file", "缺少真实尾帧输出路径")
        try:
            prompt_path = _inside(root, entry["prompt_file"])
            if not prompt_path.is_file():
                fail("prompt_missing", entry["prompt_file"])
                prompt = ""
            else:
                prompt = prompt_path.read_text(encoding="utf-8")
        except (KeyError, ValueError) as exc:
            fail("prompt_file", str(exc))
            prompt = ""
        for path in _fixed_files(root, entry)[1:]:
            if not path.is_file():
                fail("fixed_input_missing", _relative(root, path))
        audio_duration = _audio_duration_total(root, entry, fail)
        expected_hashes = entry.get("input_sha256", {})
        if not isinstance(expected_hashes, dict):
            fail("input_sha256", "必须是 项目相对路径 -> SHA-256 的对象")
            expected_hashes = {}
        for relative, expected in expected_hashes.items():
            try:
                path = _inside(root, relative)
                if not path.is_file() or sha256_file(path) != expected:
                    fail("fixed_input_sha256", relative)
            except ValueError as exc:
                fail("fixed_input_sha256", str(exc))
        for key in ("output_file", "task_file", "tail_file"):
            try:
                _inside(root, entry[key])
            except (KeyError, ValueError) as exc:
                fail(key, str(exc))
        records = ([{"kind": "image"} for _ in images]
                   + [{"kind": "audio"} for _ in entry.get("audio", [])])
        markers = provider.prompt_markers(prompt, records) if provider else {}
        if provider and any(not value["match"] for value in markers.values()):
            fail("prompt_markers", json.dumps(markers, ensure_ascii=False))
        if "<Video " in prompt or entry.get("video"):
            fail("video_reference", "本队列只使用图片和音频，禁止视频参考")
        output = _inside(root, entry["output_file"])
        if output.exists() and entry.get("operation") != "reuse":
            task_file = _inside(root, entry["task_file"])
            try:
                task = _read(task_file)
                recoverable = (task.get("phase") in {"complete", "validated"}
                               and task.get("output_sha256") == sha256_file(output))
            except (FileNotFoundError, json.JSONDecodeError, ValueError):
                recoverable = False
            if not recoverable:
                fail("unexpected_output", "输出已存在且无同源完成/校验任务，拒绝覆盖")
        if entry.get("operation") == "reuse":
            tail = _inside(root, entry["tail_file"])
            if not output.is_file() or not tail.is_file():
                fail("reuse_missing", "复用段必须同时存在输出和真实尾帧")
            expected_sha = entry.get("existing_output_sha256")
            if output.is_file() and expected_sha and sha256_file(output) != expected_sha:
                fail("reuse_sha256", "复用输出哈希变化")
        rows.append({"segment_id": segment_id, "duration_s": duration,
                     "images": len(images), "audio": len(entry.get("audio", [])),
                     "audio_duration_s": round(audio_duration, 6),
                     "markers": markers, "ready": not local})
        issues.extend(local)
        previous_id = segment_id
    result = {"ok": not issues, "dry_run": True, "network": False,
              "queue": str(queue_file), "project_root": str(root),
              **provider_binding,
              "segment_count": len(rows), "segments": rows, "issues": issues,
              "task_files_created": False, "manifest_modified": False}
    if args.require_ready and issues:
        raise SeriesError("本次执行预检未通过；尚未提交任何视频: " + json.dumps(issues, ensure_ascii=False))
    return result


def _save_run(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    json_state.save_state(path, state)


def _extract_tail(root: Path, entry: dict, output_sha256: str) -> dict:
    output = _inside(root, entry["output_file"])
    tail = _inside(root, entry["tail_file"])
    if tail.exists():
        raise SeriesError(f"真实尾帧文件已存在，拒绝覆盖: {tail}")
    tail.parent.mkdir(parents=True, exist_ok=True)
    facts = media.cmd_frame(argparse.Namespace(
        video=str(output), out=str(tail), tail=True, at=None, first=False))
    if facts.get("source_sha256") != output_sha256:
        raise SeriesError("尾帧来源视频哈希不一致")
    return {"file": _relative(root, tail), "sha256": sha256_file(tail),
            "source_video_sha256": output_sha256,
            "frame_index": facts.get("frame_index"),
            "timestamp_s": facts.get("timestamp_s")}


def _verify_existing_tail(root: Path, entry: dict, output_sha256: str,
                          run_state: dict) -> dict:
    segment_id = entry["segment_id"]
    tail = _inside(root, entry["tail_file"])
    if not tail.is_file():
        return _extract_tail(root, entry, output_sha256)
    saved = run_state["segments"].get(segment_id, {}).get("tail")
    if saved and saved.get("source_video_sha256") == output_sha256 \
            and saved.get("sha256") == sha256_file(tail):
        return saved
    if entry.get("operation") == "reuse":
        return {"file": _relative(root, tail), "sha256": sha256_file(tail),
                "source_video_sha256": output_sha256,
                "frame_index": entry.get("existing_tail_frame_index"),
                "timestamp_s": entry.get("existing_tail_timestamp_s")}
    raise SeriesError(f"尾帧已存在但没有可核验的同源运行记录，拒绝猜测或覆盖: {tail}")


@dataclass(frozen=True)
class SegmentExecutionContext:
    root: Path
    queue: dict
    entry: dict
    by_id: dict
    run_state: dict
    args: argparse.Namespace
    output: Path
    provider: object

    @property
    def segment_id(self) -> str:
        return self.entry["segment_id"]


class ReusedSegmentStrategy:
    def execute(self, context: SegmentExecutionContext) -> tuple[str, dict]:
        output_sha = sha256_file(context.output)
        result = {
            "segment_id": context.segment_id, "phase": SegmentPhase.REUSED.value,
            "task_id": None, "output_file": _relative(context.root, context.output),
            "output_sha256": output_sha,
            "media": context.entry.get("existing_media", {}),
        }
        return output_sha, result


class GeneratedSegmentStrategy:
    def execute(self, context: SegmentExecutionContext) -> tuple[str, dict]:
        entry, root = context.entry, context.root
        task_file = _inside(root, entry["task_file"])
        images = _images(root, entry, context.by_id, context.run_state)
        resumed = task_file.exists()
        if entry.get("operation") == "recover" and not resumed:
            raise SeriesError(f"{entry['segment_id']} 缺少原任务文件，recover 禁止新 POST")
        if resumed:
            _verify_task_inputs(context.provider, task_file, root, entry, images)
            submitted = {"phase": "resumed", "task_id": None}
        else:
            submitted = context.provider.submit_segment(
                config=str(_inside(root, context.queue["cloud_config"])), entry=entry,
                images=images,
                audio=[str(_inside(root, value)) for value in entry.get("audio", [])],
                prompt_file=str(_inside(root, entry["prompt_file"])),
                task_file=str(task_file), output=str(context.output),
            )
        completed = context.provider.poll_segment(
            task_file=str(task_file), output=str(context.output),
            timeout=context.args.timeout, interval=context.args.interval,
            require_audio=True, resumed=resumed,
        )
        output_sha = completed.get("sha256") or sha256_file(context.output)
        if not output_sha:
            raise SeriesError(f"{context.segment_id} 输出缺少 SHA-256")
        result = {
            "segment_id": context.segment_id, "phase": SegmentPhase.COMPLETE.value,
            "task_id": completed.get("task_id"),
            "output_file": _relative(root, context.output), "output_sha256": output_sha,
            "media": completed.get("media", {}), "submission": submitted.get("phase"),
        }
        return output_sha, result


def _execute_one(root: Path, queue: dict, entry: dict, by_id: dict,
                 run_state: dict, run_file: Path, args, provider) -> dict:
    segment_id = entry["segment_id"]
    output = _inside(root, entry["output_file"])
    saved = run_state["segments"].get(segment_id, {})
    context = SegmentExecutionContext(
        root=root, queue=queue, entry=entry, by_id=by_id, run_state=run_state,
        args=args, output=output, provider=provider)
    strategy = ReusedSegmentStrategy() if entry.get("operation") == "reuse" \
        else GeneratedSegmentStrategy()
    output_sha, result = strategy.execute(context)
    saved.update(result)
    run_state["segments"][segment_id] = saved
    run_state["current_segment"] = segment_id
    _save_run(run_file, run_state)
    tail = _verify_existing_tail(root, entry, output_sha, run_state)
    saved["tail"] = tail
    saved["phase"] = (
        SegmentPhase.REUSED_TAIL_READY.value
        if result["phase"] == SegmentPhase.REUSED.value
        else SegmentPhase.TAIL_READY.value
    )
    run_state["segments"][segment_id] = saved
    _save_run(run_file, run_state)
    return saved


def _authorized_scope(entries: list[dict], args) -> tuple[set[str], int, dict]:
    authorized = set(args.authorized_segment or [])
    if not authorized:
        raise ValueError("至少需要一个 --authorized-segment；不会默认生成整集")
    ids = [entry["segment_id"] for entry in entries]
    unknown = authorized - set(ids)
    if unknown:
        raise ValueError(f"授权 SEG 不在队列中: {sorted(unknown)}")
    last = max(ids.index(value) for value in authorized)
    reusable = {entry["segment_id"] for entry in entries
                if entry.get("operation") == "reuse"}
    missing = set(ids[:last + 1]) - authorized - reusable
    if missing:
        raise ValueError(f"连续队列中存在未授权且不可复用的前序 SEG: {sorted(missing)}")
    confirmations = dict(item.split("=", 1) for item in (args.confirmation or []))
    if set(confirmations) != authorized or any(not value for value in confirmations.values()):
        raise ValueError("每个授权 SEG 都必须用 --confirmation SEGxxx=VCxxx 绑定独立确认")
    return authorized, last, confirmations


@contextmanager
def _execution_lock(run_file: Path):
    lock = run_file.with_name(run_file.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SeriesError(f"串行执行锁已存在: {lock}；禁止两个队列并发推进同一尾帧链") from None
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _load_run_state(run_file: Path, queue_file: Path, binding: dict) -> dict:
    if run_file.exists():
        state = _read(run_file)
        if state.get("queue_sha256") != sha256_file(queue_file):
            raise SeriesError("运行状态对应不同队列版本；禁止混用尾帧和任务")
        for key, value in binding.items():
            if state.get(key) != value:
                raise SeriesError(f"运行状态必须完整锁定 {key}；禁止补齐、切换后端或适配器")
        return state
    return {"schema_version": "1.0", "queue_sha256": sha256_file(queue_file),
            **binding, "current_segment": None, "segments": {}, "manifest_modified": False}


def cmd_run(args) -> dict:
    queue_file = Path(args.queue).resolve()
    preflight = cmd_preflight(argparse.Namespace(
        queue=str(queue_file), project_root=args.project_root, require_ready=True))
    root = Path(preflight["project_root"])
    queue = _read(queue_file)
    entries = queue["segments"]
    authorized, last, confirmations = _authorized_scope(entries, args)
    by_id = {entry["segment_id"]: entry for entry in entries}
    run_file = _inside(root, queue["run_state_file"])
    provider, provider_binding, _ = _resolve_provider(root, queue)

    with _execution_lock(run_file):
        run_state = _load_run_state(run_file, queue_file, provider_binding)
        try:
            receipts = []
            for entry in entries[:last + 1]:
                segment_id = entry["segment_id"]
                if segment_id not in authorized and entry.get("operation") != "reuse":
                    break
                if segment_id in authorized:
                    saved = run_state["segments"].setdefault(segment_id, {})
                    saved["confirmation_id"] = confirmations[segment_id]
                receipts.append(_execute_one(
                    root, queue, entry, by_id, run_state, run_file, args, provider))
            run_state["last_run_authorized_segments"] = [
                entry["segment_id"] for entry in entries[:last + 1]]
            run_state["last_run_status"] = QueueRunStatus.COMPLETE.value
            _save_run(run_file, run_state)
        except BaseException as exc:
            if run_file.exists():
                run_state = _read(run_file)
                run_state["last_run_status"] = QueueRunStatus.STOPPED.value
                run_state["last_error_type"] = type(exc).__name__
                _save_run(run_file, run_state)
            raise
    return {"ok": True, "phase": "queue_scope_complete", "network": True,
            **provider_binding,
            "completed_segments": [item["segment_id"] for item in receipts],
            "receipts": receipts, "run_state_file": str(run_file),
            "manifest_modified": False, "automatic_regeneration": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="可插拔视频 provider 的 SEG 串行队列与真实尾帧接力")
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--queue", required=True)
    common.add_argument("--project-root")

    preflight = sub.add_parser("preflight", parents=[common])
    preflight.add_argument("--require-ready", action="store_true")
    preflight.set_defaults(func=cmd_preflight)

    run = sub.add_parser("run", parents=[common])
    run.add_argument("--authorized-segment", action="append")
    run.add_argument("--confirmation", action="append", help="SEGxxx=VCxxx")
    run.add_argument("--timeout", type=int, default=900)
    run.add_argument("--interval", type=int, default=10)
    run.set_defaults(func=cmd_run)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    env.set_env_file(args.env_file)
    env.emit(args.func(args))


if __name__ == "__main__":
    env.run_cli(main)
