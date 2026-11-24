from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.lib import env

LANGUAGES = ("Auto", "Chinese", "English", "Japanese", "Korean", "German",
             "French", "Russian", "Portuguese", "Spanish", "Italian")

REMOTE_RUNNER = r'''
import json, sys, time, urllib.request, uuid

COMFY = "http://127.0.0.1:6006"

def build_prompt(text, instruct, prefix, language="Auto"):
    return {
        "15": {"class_type": "TDQwen3TTSModelLoader", "inputs": {
            "model_path": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            "precision": "bf16", "device": "cuda",
            "attn_implementation": "flash_attention_2",
            "auto_download": False, "download_source": "ModelScope"}},
        "23": {"class_type": "CR Prompt Text", "inputs": {"prompt": text}},
        "25": {"class_type": "CR Prompt Text", "inputs": {"prompt": instruct}},
        "24": {"class_type": "TDQwen3TTSVoiceDesign", "inputs": {
            "model": ["15", 0], "text": ["23", 0], "instruct": ["25", 0],
            "language": language}},
        "21": {"class_type": "SaveAudio", "inputs": {
            "audio": ["24", 0], "filename_prefix": "audio/" + prefix}},
    }

def post(url, payload):
    req = urllib.request.Request(url, method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"))
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def run(text, instruct, prefix, language="Auto"):
    resp = post(COMFY + "/prompt",
                {"prompt": build_prompt(text, instruct, prefix, language),
                 "client_id": str(uuid.uuid4())})
    pid = resp.get("prompt_id")
    if not pid:
        print("SUBMIT FAIL " + json.dumps(resp, ensure_ascii=False)[:500])
        return 1
    print("[queued] " + pid, flush=True)
    for _ in range(180):
        time.sleep(5)
        item = get(COMFY + "/history/" + pid).get(pid)
        if not item:
            continue
        status = item.get("status") or {}
        if status.get("completed"):
            outs = item.get("outputs", {})
            audio = outs.get("21", {}).get("audio", [])
            if not audio:
                print("[error] 本次任务未返回音频文件")
                return 1
            print("[result] " + json.dumps(audio[0], ensure_ascii=False), flush=True)
            return 0
        if status.get("status_str") == "error":
            print("[error] " + json.dumps(item, ensure_ascii=False)[:800])
            return 1
    print("[timeout]")
    return 1

if __name__ == "__main__":
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    sys.exit(run(job["text"], job["instruct"], job["prefix"], job["language"]))
'''

_REMOTE_PYTHON = "/root/miniconda3/bin/python"
_REMOTE_OUTPUT_ROOT = "/root/ComfyUI/output"


def _ssh_config() -> dict:
    conf = env.require("AUTODL_SSH_HOST", "AUTODL_SSH_PASSWORD")
    conf["AUTODL_SSH_PORT"] = env.get("AUTODL_SSH_PORT", "22")
    conf["AUTODL_SSH_USER"] = env.get("AUTODL_SSH_USER", "root")
    return conf


def _ssh_client(conf: dict):
    try:
        import paramiko
    except ImportError:
        raise RuntimeError("缺少依赖 paramiko，请先运行: pip install paramiko")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(conf["AUTODL_SSH_HOST"], port=int(conf["AUTODL_SSH_PORT"]),
                   username=conf["AUTODL_SSH_USER"],
                   password=conf["AUTODL_SSH_PASSWORD"], timeout=30)
    return client


def _to_wav(ffmpeg: str, src: str, dst: str) -> None:
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", src,
                    "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", dst],
                   check=True)


def _validate_jobs(jobs: list[dict], default_language: str) -> list[dict]:
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("roles-file 必须是非空数组")
    for job in jobs:
        if not isinstance(job, dict) or any(
                not isinstance(job.get(key), str) or not job[key].strip()
                for key in ("role", "instruct", "text", "out")):
            raise ValueError("每个角色需非空 role/instruct/text/out")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", job["role"]):
            raise ValueError(f"role 只允许英文字母/数字/下划线/连字符: {job['role']}")
        job.setdefault("language", default_language)
        if job["language"] not in LANGUAGES:
            raise ValueError(f"language 不受支持: {job['language']}")
    return jobs


def _result_audio_path(output: str) -> str:
    results = [json.loads(line[len("[result] "):]) for line in output.splitlines()
               if line.startswith("[result] ")]
    if len(results) != 1 or not isinstance(results[0], dict):
        raise RuntimeError("本次任务未返回唯一音频结果")
    result = results[0]
    filename, subfolder = result.get("filename"), result.get("subfolder", "")
    if result.get("type") != "output" or not isinstance(filename, str) \
            or not isinstance(subfolder, str):
        raise RuntimeError("音频结果路径无效")
    path = posixpath.normpath(posixpath.join(_REMOTE_OUTPUT_ROOT, subfolder, filename))
    if not path.startswith(_REMOTE_OUTPUT_ROOT + "/") or not filename:
        raise RuntimeError("音频结果越出 ComfyUI 输出目录")
    return path


class _RemoteBatch:


    def __init__(self, conf: dict, ffmpeg: str):
        self.conf = conf
        self.ffmpeg = ffmpeg
        self.run_id = uuid.uuid4().hex
        self.client = None
        self.sftp = None
        self.remote_files: list[str] = []
        self.runner_path = f"/tmp/qwen3tts_runner_{self.run_id}.py"

    def __enter__(self):
        try:
            self.client = _ssh_client(self.conf)
            self.sftp = self.client.open_sftp()
            self._write(self.runner_path, REMOTE_RUNNER)
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _write(self, path: str, content: str) -> None:
        self.remote_files.append(path)
        with self.sftp.open(path, "w") as stream:
            stream.write(content)

    def _remote_output(self, job: dict, index: int) -> tuple[str, str]:
        job_path = f"/tmp/qwen3tts_job_{self.run_id}_{index}.json"
        payload = json.dumps({
            "text": job["text"], "instruct": job["instruct"],
            "prefix": f"{job['role']}_tts_{self.run_id}", "language": job["language"],
        }, ensure_ascii=False)
        self._write(job_path, payload)
        _, stdout, stderr = self.client.exec_command(
            f"{_REMOTE_PYTHON} {shlex.quote(self.runner_path)} {shlex.quote(job_path)}",
            timeout=1200,
        )
        return (
            stdout.read().decode("utf-8", "replace"),
            stderr.read().decode("utf-8", "replace"),
        )

    def _download_and_convert(self, remote_flac: str, out_path: Path) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as stream:
                temporary = stream.name
            self.sftp.get(remote_flac, temporary)
            _to_wav(self.ffmpeg, temporary, str(out_path))
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def run(self, job: dict, index: int) -> dict:
        output, remote_stderr = self._remote_output(job, index)
        try:
            remote_flac = _result_audio_path(output)
        except (RuntimeError, ValueError) as exc:
            return {"role": job["role"], "ok": False, "error": str(exc),
                    "remote_stderr": remote_stderr[:300]}

        out_path = Path(job["out"]).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._download_and_convert(remote_flac, out_path)
        except (OSError, subprocess.CalledProcessError) as exc:
            return {"role": job["role"], "ok": False, "error": f"下载或转码失败: {exc}"}
        return {"role": job["role"], "ok": True,
                "out": str(out_path), "bytes": out_path.stat().st_size}

    def close(self) -> None:
        if self.sftp is not None:
            for remote_file in self.remote_files:
                try:
                    self.sftp.remove(remote_file)
                except OSError:
                    pass
            self.sftp.close()
            self.sftp = None
        if self.client is not None:
            self.client.close()
            self.client = None


def _parse_args():
    parser = argparse.ArgumentParser(description="drama TTS CLI（AutoDL Qwen3-TTS 角色参考音）")
    parser.add_argument("--env-file", help="显式 .env 路径")
    parser.add_argument("--role")
    parser.add_argument("--instruct")
    parser.add_argument("--text")
    parser.add_argument("--out")
    parser.add_argument("--language", choices=LANGUAGES, default="Auto")
    parser.add_argument("--roles-file", help='[{"role","instruct","text","out","language"?},...]')
    parser.add_argument("--ffmpeg", default="ffmpeg")
    return parser.parse_args()


def _jobs_from_args(args) -> list[dict]:
    if args.roles_file:
        jobs = json.loads(Path(args.roles_file).read_text(encoding="utf-8-sig"))
    elif args.role and args.instruct and args.text and args.out:
        jobs = [{"role": args.role, "instruct": args.instruct,
                 "text": args.text, "out": args.out}]
    else:
        raise ValueError("给 --role/--instruct/--text/--out，或 --roles-file")
    return _validate_jobs(jobs, args.language)


def main() -> None:
    args = _parse_args()
    env.set_env_file(args.env_file)
    jobs = _jobs_from_args(args)
    with _RemoteBatch(_ssh_config(), args.ffmpeg) as batch:
        report = [batch.run(job, index) for index, job in enumerate(jobs)]

    failed = [item for item in report if not item["ok"]]
    env.emit({"ok": not failed, "total": len(report), "failed": len(failed), "jobs": report})
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    env.run_cli(main)
