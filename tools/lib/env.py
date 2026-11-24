from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

SKILL_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = SKILL_ROOT / "tools"

_EXPLICIT_ENV_FILE: str | None = None
_LOADED = False

_MIME = {

    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".bmp": "image/bmp", ".tif": "image/tiff",
    ".tiff": "image/tiff", ".gif": "image/gif", ".heic": "image/heic",
    ".heif": "image/heif",

    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
    ".m4v": "video/x-m4v",

    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac",
    ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
}


class ConfigError(RuntimeError):
    pass


def set_env_file(path: str | None) -> None:
    global _EXPLICIT_ENV_FILE, _LOADED
    _EXPLICIT_ENV_FILE = path
    _LOADED = False


def _candidate_files() -> list[Path]:
    paths = []
    if _EXPLICIT_ENV_FILE:
        paths.append(Path(_EXPLICIT_ENV_FILE))
    env_var = os.environ.get("DRAMA_ENV_FILE")
    if env_var:
        paths.append(Path(env_var))
    paths.append(TOOLS_DIR / ".env")
    paths.append(SKILL_ROOT / ".env")
    return paths


def load_dotenv() -> None:

    global _LOADED
    if _LOADED:
        return
    for path in _candidate_files():
        try:
            if not path.is_file():
                continue
            with path.open("r", encoding="utf-8-sig") as stream:
                for raw in stream:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    if line.startswith("export "):
                        line = line[len("export "):]
                    key, sep, value = line.partition("=")
                    key = key.strip()
                    if key and sep:
                        os.environ.setdefault(key, value.strip().strip("'\""))
        except OSError:

            continue
    _LOADED = True


def get(name: str, default: str | None = None) -> str | None:
    load_dotenv()
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def require(*names: str) -> dict[str, str]:
    load_dotenv()
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise ConfigError(
            "缺凭证/配置：" + ", ".join(missing)
            + "。请设置环境变量，或写入 skill 的 .env（可用 --env-file 指定）。")
    return {name: os.environ[name] for name in names}


def emit(obj: dict) -> None:

    print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def fail(message: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": str(message)},
                     ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def is_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def mime_of(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return _MIME.get(suffix) or mimetypes.guess_type(path)[0] or ""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode_data_uri(path: str) -> tuple[str, str, str]:

    mime = mime_of(path)
    if not mime:
        raise ValueError(f"无法识别媒体类型: {path}")
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    uri = "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")
    return uri, mime, digest


def run_cli(main_fn) -> None:

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        main_fn()
    except ConfigError as exc:
        fail(str(exc))
    except (OSError, ValueError, RuntimeError) as exc:
        fail(str(exc))
