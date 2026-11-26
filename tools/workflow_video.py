from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from urllib.parse import urlencode, urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import video as common
from tools.lib import env
from tools.lib.h3_domain import TaskPhase, TaskRecord
from tools.lib.media_facts import sha256_file

_DEFAULT_TIMEOUT_S = 900
_DEFAULT_INTERVAL_S = 10
_STALE = "STALE_OR_UNAVAILABLE"
_SUCCESS = {"SUCCESS", "SUCCEEDED", "COMPLETE", "COMPLETED", "DONE", "FINISHED"}
_BAD = {"FAILED", "FAILURE", "ERROR", "CANCEL", "CANCELLED", "CANCELED"}
_ASPECTS = [
    "1:1 (Square)", "2:3 (Portrait Photo)", "3:2 (Photo)",
    "3:4 (Portrait Standard)", "4:3 (Standard)",
    "9:16 (Portrait Widescreen)", "16:9 (Widescreen)", "21:9 (Ultrawide)",
]
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
_SKIP_RESULT_KEYS = {"input", "inputs", "input_values", "request", "payload"}


PROVIDER_ID = "autodl"
ADAPTER_VERSION = "1.0"
EXECUTION_DEPENDENCY_FILES = (
    "autodl_instance.py",
    "media.py",
    "video.py",
    "video_run.py",
    "workflow_series.py",
    "lib/env.py",
    "lib/h3_domain.py",
    "lib/json_state.py",
    "lib/media_facts.py",
    "lib/video_providers.py",
)


class WorkflowBackendError(common.BackendError):
    def __init__(self, message: str, *, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


class WorkflowRecoveryError(WorkflowBackendError):
    pass


def _http(method: str, url: str, token: str | None, *, payload=None,
          timeout: int = 120, raw: bool = False, allow_list: bool = False):
    return common._http(method, url, token, payload, timeout, raw,
                        error_type=WorkflowBackendError, label="workflow",
                        allow_list=allow_list)


def _config(path: str | None) -> dict:
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("workflow config 顶层必须是 JSON 对象")
    forbidden = {"token", "api_key", "authorization", "password"}
    if forbidden & {str(key).lower() for key in value}:
        raise ValueError("workflow config 不得保存凭证；请使用 H3_WORKFLOW_API_KEY 环境变量")
    return value


def _redacted_payload(payload: dict) -> dict:
    return common._redact_data_uris(payload)


def prepare(args) -> dict:
    config = _config(getattr(args, "config", None))
    capabilities = common._load_profile()
    seconds = args.seconds
    common._validate_mode_duration(args.mode, seconds, capabilities, field="seconds")

    aspect = (args.aspect_ratio or env.get("H3_WORKFLOW_ASPECT_RATIO")
              or config.get("aspect_ratio"))
    if aspect not in _ASPECTS:
        raise ValueError(f"aspect_ratio 必须是: {_ASPECTS}")
    megapixels = args.megapixels
    if megapixels is None:
        raw_mp = env.get("H3_WORKFLOW_MEGAPIXELS")
        megapixels = raw_mp if raw_mp is not None else config.get("megapixels")
    try:
        megapixels = float(megapixels)
    except (TypeError, ValueError):
        raise ValueError("megapixels 必须是有限正数") from None
    if not math.isfinite(megapixels) or megapixels <= 0:
        raise ValueError("megapixels 必须是有限正数")

    workflow = (args.workflow or env.get("H3_WORKFLOW_ID")
                or config.get("workflow_id"))
    base = (args.base_url or env.get("H3_WORKFLOW_BASE_URL")
            or config.get("base_url") or "").rstrip("/")
    if not workflow or not isinstance(workflow, str):
        raise ValueError("缺 workflow_id")
    if not env.is_url(base):
        raise ValueError("base_url 必须是有效 HTTP(S) URL")

    limits = capabilities["mode_ref_limits"][args.mode]
    slots, records = common._build_slots(
        args.image, args.video, args.audio, args.mode, limits)
    prompt = common._read_prompt(args)
    markers = common._marker_summary(prompt, records)
    mismatched = [kind for kind, value in markers.items() if not value["match"]]
    if mismatched:
        raise ValueError(f"Prompt 媒体标记与真实槽位不一致: {mismatched}")

    input_values = dict(slots)
    input_values.update(prompt=prompt, seconds=seconds,
                        aspect_ratio=aspect, megapixels=megapixels)
    payload = {"workflow_id": workflow, "input_values": input_values}
    view_path = config.get("view_path", "/api/comfy/proxy/view")
    if not isinstance(view_path, str) or not view_path.startswith("/"):
        raise ValueError("view_path 必须是以 / 开头的路径")
    digest_view = _redacted_payload(payload)
    params_digest = hashlib.sha256(json.dumps(
        {"payload": digest_view, "base_url": base, "view_path": view_path},
        ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "workflow_id": workflow, "base_url": base, "view_path": view_path,
        "payload": payload, "slots": records, "markers": markers,
        "seconds": seconds, "aspect_ratio": aspect, "megapixels": megapixels,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "params_sha256": params_digest,
    }


def _task_file(args) -> Path:
    return common._default_task_file(args)


def _token() -> str | None:
    return env.get("H3_WORKFLOW_API_KEY")


def _load_state(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"任务文件不存在: {path}（先 submit/run）")
    state = json.loads(path.read_text(encoding="utf-8-sig"))
    if state.get("protocol") != "comfy_workflow_v1":
        raise ValueError("任务文件不是 comfy_workflow_v1 协议")
    if not state.get("prompt_id"):
        raise ValueError(
            f"任务文件没有 prompt_id: {path}；禁止盲目重提，请先核对服务端任务")
    return state


def cmd_submit(args) -> dict:
    prepared = prepare(args)
    task_file = _task_file(args)
    dry_run = getattr(args, "dry_run", False)
    if dry_run:
        return {
            "ok": True, "dry_run": True, "protocol": "comfy_workflow_v1",
            "base_url": prepared["base_url"],
            "payload": _redacted_payload(prepared["payload"]),
            "slots": prepared["slots"], "markers": prepared["markers"],
            "prompt_sha256": prepared["prompt_sha256"],
            "params_sha256": prepared["params_sha256"], "prompt_id": None,
        }
    if task_file.exists():
        raise WorkflowBackendError(
            f"任务文件已存在 {task_file}；拒绝重复 POST，用 poll/status 恢复")
    out = Path(args.out).resolve() if getattr(args, "out", None) else None
    if out and out.exists():
        raise WorkflowBackendError(f"正式输出已存在，提交前停止以免覆盖: {out}")

    state = {
        "version": 1, "protocol": "comfy_workflow_v1", "prompt_id": None,
        "phase": TaskPhase.SUBMISSION_PENDING.value, "workflow_id": prepared["workflow_id"],
        "base_url": prepared["base_url"], "view_path": prepared["view_path"],
        "mode": args.mode, "seconds": prepared["seconds"],
        "aspect_ratio": prepared["aspect_ratio"],
        "megapixels": prepared["megapixels"], "slots": prepared["slots"],
        "prompt_sha256": prepared["prompt_sha256"],
        "params_sha256": prepared["params_sha256"],
        "out": str(out) if out else None, "created_at": common._now(),
    }
    task = TaskRecord(state)
    task_file.parent.mkdir(parents=True, exist_ok=True)
    common._save_state(task_file, state)
    try:
        response = _http(
            "POST", f"{prepared['base_url']}/api/workflow/generate", _token(),
            payload=prepared["payload"], timeout=180)
        prompt_id = response.get("prompt_id") or (response.get("data") or {}).get("prompt_id")
        if not isinstance(prompt_id, (str, int)) or not str(prompt_id):
            task.transition(TaskPhase.SUBMISSION_UNKNOWN)
            raise WorkflowBackendError(
                "提交响应缺 prompt_id；禁止自动重提，请先核对服务端是否已接收任务")
        task.transition(TaskPhase.SUBMITTED, prompt_id=str(prompt_id), http_post_count=1)
    except BaseException:
        if task.phase == TaskPhase.SUBMISSION_PENDING.value:
            task.transition(TaskPhase.SUBMISSION_UNKNOWN)
        common._save_state(task_file, state)
        raise
    common._save_state(task_file, state)
    return {"ok": True, "phase": "submitted", "prompt_id": state["prompt_id"],
            "task_file": str(task_file), "http_post_count": 1}


@dataclass(frozen=True)
class WorkflowResult:


    body: dict
    prompt_id: str

    @property
    def record(self) -> dict:
        direct = self.body.get(self.prompt_id)
        if isinstance(direct, dict):
            return direct
        data = self.body.get("data")
        if isinstance(data, dict):
            record = data.get(self.prompt_id)
            if isinstance(record, dict):
                return record
            if data.get("prompt_id") == self.prompt_id:
                return data
        return self.body

    @property
    def status(self) -> str:
        record = self.record
        candidates = [
            record, record.get("data") if isinstance(record.get("data"), dict) else {},
            self.body,
            self.body.get("data") if isinstance(self.body.get("data"), dict) else {},
        ]
        for item in candidates:
            if item.get("error"):
                return "FAILED"
            status = item.get("status")
            if isinstance(status, str):
                return status.upper()
            if isinstance(status, dict):
                text = str(status.get("status_str") or status.get("state") or "").upper()
                if text in _BAD or status.get("error"):
                    return "FAILED"
                if text:
                    return text
                if status.get("completed") is True:
                    return "SUCCESS"
            for key in ("state", "status_str"):
                if isinstance(item.get(key), str):
                    return item[key].upper()
            if item.get("completed") is True:
                return "SUCCESS"
            if item.get("pending") is False:
                return "SUCCESS"
            if item.get("pending") is True:
                return "PENDING"
        return ""


def _history_record(body: dict, prompt_id: str) -> dict:
    return WorkflowResult(body, prompt_id).record


def _status_of(body: dict, prompt_id: str) -> str:
    return WorkflowResult(body, prompt_id).status


def _looks_video_url(value: str) -> bool:
    try:
        path = urlsplit(value).path
    except ValueError:
        return False
    return Path(path).suffix.lower() in _VIDEO_EXTENSIONS


def _video_url(body: dict, *, prompt_id: str, base: str, view_path: str) -> str:
    candidates: list[tuple[int, str]] = []

    def add(value: str, score: int) -> None:
        if not isinstance(value, str) or not value.strip():
            return
        absolute = value if env.is_url(value) else urljoin(base + "/", value)
        if env.is_url(absolute):
            candidates.append((score, absolute))

    def walk(node, context: str = "", inherited_score: int = 0) -> None:
        if isinstance(node, dict):
            kind = " ".join(str(node.get(key, "")) for key in
                            ("type", "kind", "mime", "format", "media_type")).lower()
            dict_score = 30 if ("video" in kind or "mp4" in kind) else inherited_score
            filename = node.get("filename")
            if isinstance(filename, str) and Path(filename).suffix.lower() in _VIDEO_EXTENSIONS:
                query = urlencode({
                    "filename": filename, "subfolder": node.get("subfolder", ""),
                    "type": node.get("type", "output"),
                })
                add(f"{view_path}?{query}", max(50, dict_score))
            for key, value in node.items():
                if key.lower() in _SKIP_RESULT_KEYS:
                    continue
                lowered = str(key).lower()
                score = dict_score
                if lowered in {"video", "videos", "video_url", "result", "results", "output", "outputs"}:
                    score = max(score, 40)
                if isinstance(value, str) and lowered in {
                        "video", "video_url", "url", "download_url", "file_url"}:
                    if _looks_video_url(value):


                        add(value, max(score, 60))
                    elif score >= 30 or "view?" in value:
                        add(value, max(score, 20))
                elif isinstance(value, str) and _looks_video_url(value) and score >= 20:
                    add(value, score)
                else:
                    walk(value, lowered, score)
        elif isinstance(node, list):
            for value in node:
                walk(value, context, inherited_score)
        elif isinstance(node, str) and inherited_score >= 40 and _looks_video_url(node):
            add(node, inherited_score)

    record = _history_record(body, prompt_id)
    walk(record)
    if not candidates and record is not body:
        walk(body)
    if not candidates:
        raise WorkflowBackendError("成功响应中未找到可下载视频；不会自动重新生成")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _history_has_record(body: dict, prompt_id: str) -> bool:
    if isinstance(body.get(prompt_id), dict):
        return True
    data = body.get("data")
    return isinstance(data, dict) and isinstance(data.get(prompt_id), dict)


@dataclass(frozen=True)
class PollObservation:
    body: dict
    style: str
    status: str
    history_confirmed: bool
    missing: bool
    trigger: str = ""


def _history_observation(body: dict, prompt_id: str, trigger: str = "") -> PollObservation:
    confirmed = _history_has_record(body, prompt_id)
    status = _status_of(body, prompt_id)
    if confirmed and not status:
        status = "PENDING"
    return PollObservation(body, "history", status, confirmed, not confirmed, trigger)


def _observe_once(state: dict, *, preferred_style: str = "result") -> PollObservation:

    base, prompt_id = state["base_url"], state["prompt_id"]
    query = urlencode({"prompt_id": prompt_id})
    history_url = f"{base}/api/comfy/proxy/history?{query}"
    if preferred_style == "history":
        return _history_observation(_http("GET", history_url, _token()), prompt_id)
    try:
        body = _http("GET", f"{base}/api/workflow/result?{query}", _token())
    except WorkflowBackendError as exc:
        if exc.http_status not in {404, 405, 501, 500}:
            raise
        history = _http("GET", history_url, _token())
        return _history_observation(history, prompt_id, f"result_http_{exc.http_status}")

    status = _status_of(body, prompt_id)
    return PollObservation(body, "result", status, False, False)


def _poll_once(state: dict, *, preferred_style: str = "result") -> tuple[dict, str]:

    observed = _observe_once(state, preferred_style=preferred_style)
    return observed.body, observed.style


def _error_fact(exc: WorkflowBackendError) -> dict:
    return {"error_type": type(exc).__name__, "http_status": exc.http_status}


def _response_items(body, key: str) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body.get(key), list):
        return body[key]
    data = body.get("data")
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data[key]
    raise WorkflowBackendError(f"持久化资产响应缺少 {key} 数组")


def _persistent_output_url(value: str, base: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise WorkflowBackendError("持久化资产 URL 无效")
    if any(part == ".." for part in value.split("/")):
        raise WorkflowBackendError("持久化资产 URL 不允许父目录跳转")
    absolute = urljoin(base + "/", value)
    parsed, root = urlsplit(absolute), urlsplit(base)
    if (parsed.scheme, parsed.netloc) != (root.scheme, root.netloc) \
            or not parsed.path.startswith("/output/") or not _looks_video_url(absolute):
        raise WorkflowBackendError("持久化资产必须同源且位于 /output/ 视频路径")
    return absolute


def _recover_persistent_video(state: dict) -> tuple[str | None, dict]:

    base = state["base_url"]
    prompt_id = str(state["prompt_id"])
    workflow_id = str(state.get("workflow_id") or "")
    evidence = {"status": "not_found", "source": None,
                "exact_asset_matches": 0, "unique_asset_videos": 0,
                "output_listing_identity": "insufficient_standalone",
                "automatic_regeneration": False}
    candidates: dict[str, dict] = {}
    saved_url = state.get("result_url")
    if saved_url:
        try:
            url = _persistent_output_url(saved_url, base)
        except WorkflowBackendError as exc:
            evidence["saved_result_url_error"] = _error_fact(exc)
        else:
            evidence.update(status="recovered", source="saved_result_url")
            return url, evidence
    try:
        body = _http("GET", f"{base}/api/concurrent/assets", _token(), allow_list=True)
        assets = _response_items(body, "assets")
        exact = [item for item in assets if isinstance(item, dict)
                 and str(item.get("promptId") or "") == prompt_id
                 and str(item.get("workflowId") or "") == workflow_id]
        evidence["exact_asset_matches"] = len(exact)
        for item in exact:
            names = (item.get("url"), item.get("originalFile"), item.get("localFile"))
            if not any(isinstance(value, str) and _looks_video_url(value) for value in names):
                continue
            try:
                url = _persistent_output_url(item.get("url"), base)
            except WorkflowBackendError:
                evidence["invalid_asset_urls"] = evidence.get("invalid_asset_urls", 0) + 1
                continue
            candidates[url] = item
    except WorkflowBackendError as exc:
        evidence["assets_error"] = _error_fact(exc)

    evidence["unique_asset_videos"] = len(candidates)
    if len(candidates) == 1:
        url, item = next(iter(candidates.items()))
        evidence.update(status="recovered", source="concurrent_assets",
                        asset={key: item.get(key) for key in
                               ("localFile", "originalFile", "promptId", "workflowId", "url")})
        return url, evidence

    try:
        body = _http("GET", f"{base}/api/images", _token(), allow_list=True)
        images = _response_items(body, "images")
        evidence["output_video_count"] = sum(
            1 for item in images if isinstance(item, dict)
            and isinstance(item.get("relativePath"), str)
            and _looks_video_url(item["relativePath"]))
    except WorkflowBackendError as exc:
        evidence["images_error"] = _error_fact(exc)
    if len(candidates) > 1:
        evidence["status"] = "ambiguous"
    return None, evidence


def cmd_status(args) -> dict:
    task_file = _task_file(args)
    state = _load_state(task_file)
    observed = _observe_once(state, preferred_style=getattr(args, "poll_style", "result"))
    status = _STALE if observed.missing else observed.status
    state.update(backend_status=status, last_poll_style=observed.style,
                 history_confirmed=observed.history_confirmed,
                 last_query_trigger=observed.trigger)
    common._save_state(task_file, state)
    return {"ok": True, "prompt_id": state["prompt_id"], "phase": state.get("phase"),
            "backend_status": status, "poll_style": observed.style,
            "history_confirmed": observed.history_confirmed, "task_file": str(task_file)}


def _save_recovery(task_file: Path, state: dict, evidence: dict) -> None:
    state["recovery"] = evidence
    common._save_state(task_file, state)


def _download_result(task_file: Path, state: dict, out: Path, video_url: str,
                     require_audio: bool) -> dict:

    state["result_url"] = video_url
    common._save_state(task_file, state)
    body = _http("GET", video_url, None, raw=True, timeout=300)
    media = common._save_download(task_file, state, out, body, require_audio)
    return {"ok": True, "phase": "complete", "prompt_id": state["prompt_id"],
            "out": str(out), "sha256": state["output_sha256"], "media": media,
            "recovery_source": state.get("recovery", {}).get("source"),
            "task_file": str(task_file)}


def cmd_poll(args) -> dict:
    task_file = _task_file(args)
    state = _load_state(task_file)
    task = TaskRecord(state)
    if task.phase in {TaskPhase.FAILED.value, TaskPhase.SUBMISSION_UNKNOWN.value}:
        raise WorkflowBackendError(
            f"任务状态 {state['phase']}；不会自动重新生成，请先核对真实任务")
    out = Path(args.out).resolve() if args.out else (
        Path(state["out"]).resolve() if state.get("out") else None)
    if not out:
        raise ValueError("需要 --out（任务文件未登记输出路径）")
    if out.exists():
        if task.phase == TaskPhase.COMPLETE.value:
            return {"ok": True, "prompt_id": state["prompt_id"], "phase": "complete",
                    "out": str(out), "sha256": state.get("output_sha256"),
                    "media": state.get("media"), "task_file": str(task_file), "resumed": True}
        if task.phase == TaskPhase.VALIDATED.value \
                and state.get("output_sha256") == sha256_file(out):
            task.transition(TaskPhase.COMPLETE, out=str(out))
            common._save_state(task_file, state)
            return {"ok": True, "prompt_id": state["prompt_id"], "phase": "complete",
                    "out": str(out), "sha256": state["output_sha256"],
                    "media": state.get("media"), "task_file": str(task_file), "resumed": True}
        raise WorkflowBackendError(f"输出已存在但任务状态不能安全接管，拒绝覆盖: {out}")

    out.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.timeout
    preferred_style = getattr(args, "poll_style", None) or state.get("last_poll_style", "result")
    recover_stale = getattr(args, "recover_stale", True)
    recovery_attempted = False
    video_url = None

    def recover_persistent() -> None:
        nonlocal video_url, recovery_attempted
        video_url, evidence = _recover_persistent_video(state)
        recovery_attempted = True
        if video_url:
            state["result_url"] = video_url
        _save_recovery(task_file, state, evidence)

    if recover_stale:
        recover_persistent()

    while not video_url:
        try:
            observed = _observe_once(state, preferred_style=preferred_style)
        except WorkflowBackendError as exc:
            if not recovery_attempted and (recover_stale or exc.http_status == 500):
                recover_persistent()
                if video_url:
                    break
            if exc.http_status != 500:
                raise
            observed = PollObservation(
                {}, preferred_style, _STALE, False, True, "query_http_500")

        status = _STALE if observed.missing else observed.status
        state.update(backend_status=status, last_poll_style=observed.style,
                     history_confirmed=observed.history_confirmed,
                     last_query_trigger=observed.trigger)
        common._save_state(task_file, state)
        if observed.status in _SUCCESS:
            video_url = _video_url(observed.body, prompt_id=state["prompt_id"],
                                   base=state["base_url"], view_path=state["view_path"])
            state["result_url"] = video_url
            if recover_stale:
                state["recovery"] = {"status": "recovered", "source": observed.style,
                                     "automatic_regeneration": False}
            common._save_state(task_file, state)
            break
        if observed.status in _BAD:
            task.fail()
            common._save_state(task_file, state)
            raise WorkflowBackendError(
                f"prompt_id={state['prompt_id']} 后端状态 {observed.status}；不会自动重新生成")
        if not observed.missing:
            recovery_attempted = False
        if time.monotonic() >= deadline:
            if observed.missing:
                if not recovery_attempted:
                    recover_persistent()
                    if video_url:
                        break
                state["backend_status"] = _STALE
                common._save_state(task_file, state)
                raise WorkflowRecoveryError(
                    "轮询达到时限，prompt_id 当前无活动记录，且持久化资产没有唯一匹配；"
                    "任务保留，输出目录不用于模糊认领，不自动重新生成")
            raise WorkflowBackendError(
                f"轮询超时；任务保留，重新执行 poll 即可继续（prompt_id={state['prompt_id']}）")
        time.sleep(args.interval)

    return _download_result(task_file, state, out, video_url, args.require_audio)


def cmd_run(args) -> dict:
    submitted = cmd_submit(args)
    if submitted.get("dry_run"):
        return submitted
    poll_args = argparse.Namespace(
        task_file=submitted["task_file"], out=args.out, timeout=args.timeout,
        interval=args.interval, require_audio=args.require_audio, poll_style="result",
        recover_stale=False)
    return cmd_poll(poll_args)




def load_config(path: str) -> dict:
    return _config(path)


def prompt_markers(prompt: str, records: list[dict]) -> dict:
    return common._marker_summary(prompt, records)


def _segment_args(*, config: str, entry: dict, images: list[str], audio: list[str],
                  prompt_file: str, task_file: str, output: str) -> argparse.Namespace:
    return argparse.Namespace(
        config=config, mode=entry.get("h3_mode", "Ref2VA"),
        seconds=entry["duration_s"], aspect_ratio=entry.get("aspect_ratio"),
        megapixels=entry.get("megapixels"), workflow=entry.get("workflow_id"),
        base_url=entry.get("base_url"), image=images, video=None, audio=audio,
        prompt_file=prompt_file, prompt=None, task_file=task_file, out=output,
        dry_run=False,
    )


def verify_task_inputs(task_file: str, *, config: str, entry: dict,
                       images: list[str], audio: list[str], prompt_file: str,
                       output: str) -> None:
    args = _segment_args(
        config=config, entry=entry, images=images, audio=audio,
        prompt_file=prompt_file, task_file=task_file, output=output)
    prepared = prepare(args)
    state = _load_state(Path(task_file))
    expected_fields = {
        "workflow_id": prepared["workflow_id"],
        "base_url": prepared["base_url"],
        "view_path": prepared["view_path"],
        "mode": args.mode,
        "seconds": prepared["seconds"],
        "aspect_ratio": prepared["aspect_ratio"],
        "megapixels": prepared["megapixels"],
        "prompt_sha256": prepared["prompt_sha256"],
        "params_sha256": prepared["params_sha256"],
    }
    mismatched = [field for field, value in expected_fields.items() if state.get(field) != value]
    saved_output = state.get("out")
    if not isinstance(saved_output, str) or Path(saved_output).resolve() != Path(output).resolve():
        mismatched.append("out")
    if mismatched:
        raise WorkflowBackendError(
            f"已有任务与当前完整请求不一致（{', '.join(mismatched)}），拒绝盲目续跑: {task_file}")
    slots = state.get("slots", [])
    expected_inputs = images + audio
    if not isinstance(slots, list) or len(slots) != len(expected_inputs):
        raise WorkflowBackendError(f"已有任务与当前输入数量不一致，拒绝盲目续跑: {task_file}")
    for slot, filename in zip(slots, expected_inputs):
        path = Path(filename).resolve()
        if not isinstance(slot, dict) or Path(slot.get("ref", "")).resolve() != path \
                or slot.get("sha256") != sha256_file(path):
            raise WorkflowBackendError(
                f"已有任务的 {slot.get('slot') if isinstance(slot, dict) else '未知槽位'} 与当前真实输入不一致: {task_file}")


def _provider_result(result: dict) -> dict:
    value = dict(result)
    value.setdefault("task_id", value.get("prompt_id"))
    value["video_provider"] = PROVIDER_ID
    return value


def submit_segment(*, config: str, entry: dict, images: list[str], audio: list[str],
                   prompt_file: str, task_file: str, output: str) -> dict:

    args = _segment_args(
        config=config, entry=entry, images=images, audio=audio,
        prompt_file=prompt_file, task_file=task_file, output=output)
    return _provider_result(cmd_submit(args))


def poll_segment(*, task_file: str, output: str, timeout: int, interval: int,
                 require_audio: bool, resumed: bool) -> dict:
    args = argparse.Namespace(
        task_file=task_file, out=output, timeout=timeout, interval=interval,
        require_audio=require_audio, poll_style="result", recover_stale=resumed,
    )
    return _provider_result(cmd_poll(args))


def _add_common(parser: argparse.ArgumentParser, *, need_prompt: bool = True) -> None:
    parser.add_argument("--env-file", help="显式 .env 路径；凭证只读环境变量")
    if need_prompt:
        prompt = parser.add_mutually_exclusive_group(required=True)
        prompt.add_argument("--prompt-file", help="h3-prompt-writing 的 H3 英文成稿")
        prompt.add_argument("--prompt", help="H3 英文成稿文本")
        parser.add_argument("--mode", required=True,
                            choices=["T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"])
        parser.add_argument("--seconds", required=True, type=int, help="整数秒 4-15")
        parser.add_argument("--image", action="append", help="图片路径或 URL，可重复")
        parser.add_argument("--video", action="append", help="视频路径或 URL，可重复")
        parser.add_argument("--audio", action="append", help="音频路径或 URL，可重复")
        parser.add_argument("--aspect-ratio", choices=_ASPECTS)
        parser.add_argument("--megapixels", type=float)
        parser.add_argument("--workflow", help="覆盖配置 workflow_id")
        parser.add_argument("--base-url", help="覆盖配置 base_url")
        parser.add_argument("--config", help="无凭证的 workflow JSON 配置")
    parser.add_argument("--task-file", help="任务文件；缺省为 <out>.h3task.json")
    if not need_prompt:
        parser.add_argument("--poll-style", choices=["result", "history"], default="result")


def main() -> None:
    parser = argparse.ArgumentParser(description="自部署 Comfy workflow H3 视频执行器")
    sub = parser.add_subparsers(dest="command", required=True)
    p_submit = sub.add_parser("submit", help="提交一次，或 --dry-run 离线核验")
    _add_common(p_submit)
    p_submit.add_argument("--out", help="预期输出路径")
    p_submit.add_argument("--dry-run", action="store_true", help="不联网、不创建任务文件")
    p_submit.set_defaults(func=cmd_submit)

    p_run = sub.add_parser("run", help="提交一次并轮询、下载、基础校验")
    _add_common(p_run)
    p_run.add_argument("--out", required=True, help="正式 MP4 输出路径")
    p_run.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT_S)
    p_run.add_argument("--interval", type=int, default=_DEFAULT_INTERVAL_S)
    p_run.add_argument("--require-audio", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_poll = sub.add_parser(
        "poll", help="恢复原任务：先只读找回持久化资产，不重新 POST")
    _add_common(p_poll, need_prompt=False)
    p_poll.add_argument("--out", help="输出路径；任务文件已有时可省略")
    p_poll.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT_S)
    p_poll.add_argument("--interval", type=int, default=_DEFAULT_INTERVAL_S)
    p_poll.add_argument("--require-audio", action="store_true")
    p_poll.set_defaults(func=cmd_poll)

    p_status = sub.add_parser("status", help="按已有 prompt_id 查询一次")
    _add_common(p_status, need_prompt=False)
    p_status.set_defaults(func=cmd_status)
    args = parser.parse_args()
    env.set_env_file(getattr(args, "env_file", None))
    env.emit(args.func(args))


if __name__ == "__main__":
    env.run_cli(main)
