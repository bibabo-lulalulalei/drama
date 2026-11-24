from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.lib import env, json_state
from tools.lib.h3_domain import MediaSlotRequest, TaskPhase, TaskRecord
from tools.lib.media_facts import media_duration, probe_media, sha256_file

_CAP_FILE = Path(__file__).resolve().parent / "h3.json"


class BackendError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            old, new = urlsplit(req.full_url), urlsplit(newurl)
            if (old.scheme, old.netloc) != (new.scheme, new.netloc):
                redirected.remove_header("Authorization")
        return redirected


def _http(method, url, token, payload=None, timeout=120, raw=False,
          *, error_type=BackendError, label="视频工作流", allow_list=False):
    headers = {"Authorization": token} if token else {}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.build_opener(_SafeRedirect()).open(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise error_type(f"{label} HTTP {exc.code}（响应体已抑制）",
                         http_status=exc.code) from None
    except urllib.error.URLError as exc:
        raise error_type(f"{label} 连接失败: {exc.reason}") from None
    if raw:
        return body
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise error_type(f"{label} 返回了非 JSON 响应（正文已抑制）") from None
    if allow_list and isinstance(value, list):
        return value
    if not isinstance(value, dict):
        raise error_type(f"{label} JSON 顶层不是对象")
    return value


def _load_profile() -> dict:
    profile = json.loads(_CAP_FILE.read_text(encoding="utf-8"))
    return profile["capabilities"]


def _validate_mode_duration(mode: str, value: int, capabilities: dict,
                            *, field: str = "duration") -> None:
    if mode not in capabilities["modes"]:
        raise ValueError(f"未知 mode {mode}；能力档: {capabilities['modes']}")
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} 必须是整数秒")
    low, high = capabilities["min_duration_s"], capabilities["max_duration_s"]
    if not low <= value <= high:
        raise ValueError(f"{field} {value}s 超出能力档 {low}-{high}s 整数区间")


def _read_prompt(args) -> str:
    prompt = (Path(args.prompt_file).read_text(encoding="utf-8")
              if args.prompt_file else args.prompt)
    if not prompt or not prompt.strip():
        raise ValueError("Prompt 为空")
    return prompt


def _redact_data_uris(value):
    if isinstance(value, dict):
        return {key: _redact_data_uris(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_data_uris(item) for item in value]
    if isinstance(value, str) and value.startswith("data:"):
        return f"<data-uri {len(value)} chars>"
    return value


def _build_slots(images, videos, audios, mode, limits) -> tuple[dict, list[dict]]:
    return MediaSlotRequest(
        images, videos, audios, mode, limits, media_duration,
    ).build()


def _marker_summary(prompt: str, records: list[dict]) -> dict:
    summary = {}
    for kind, label in (("image", "Picture"), ("video", "Video"), ("audio", "Audio")):
        actual = {int(v) for v in re.findall(r"<\s*" + label + r"\s*(\d+)\s*>",
                                             prompt, re.I)}
        expected = set(range(1, sum(1 for r in records if r["kind"] == kind) + 1))
        if expected:
            summary[kind] = {"markers": sorted(actual), "expected": sorted(expected),
                             "match": actual == expected}
    return summary


def _default_task_file(args) -> Path:
    if args.task_file:
        return Path(args.task_file).resolve()
    if getattr(args, "out", None):
        return Path(str(args.out) + ".h3task.json").resolve()
    return Path.cwd() / "h3_task.json"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _save_state(path: Path, state: dict) -> None:
    json_state.save_state(path, state)


def _validate(path: Path, require_audio: bool) -> dict:
    facts = probe_media(str(path))
    if require_audio and not facts["has_audio"]:
        raise BackendError("结果缺音频流；下载文件已保留")
    decode = subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(path),
         "-map", "0:v:0", "-map", "0:a?", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if decode.returncode:
        raise BackendError("视频完整解码失败；下载文件已保留")
    facts["decode_ok"] = True
    return facts


def _save_download(task_file: Path, state: dict, out: Path, body: bytes,
                   require_audio: bool) -> dict:
    part = out.with_name(out.name + ".h3-download.part")
    part.write_bytes(body)
    task = TaskRecord(state)
    task.transition(TaskPhase.DOWNLOADED)
    _save_state(task_file, state)
    media = _validate(part, require_audio)
    task.transition(TaskPhase.VALIDATED, output_sha256=sha256_file(part), media=media)
    _save_state(task_file, state)
    os.replace(part, out)
    task.transition(TaskPhase.COMPLETE, out=str(out))
    _save_state(task_file, state)
    return media
