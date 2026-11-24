from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import mimetypes
from pathlib import Path
import sys
from typing import Protocol
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.lib import env

ENV_VARS = ("OSS_ENDPOINT_URL", "OSS_BUCKET_NAME", "OSS_ACCESS_KEY_ID",
            "OSS_SECRET_KEY_SECRET", "OSS_ANTI_THEFT_CHAIN")


def _s3_config() -> dict:
    missing = [name for name in ENV_VARS if not env.get(name)]
    if missing:
        raise env.ConfigError(
            "上传未配置，缺少: " + ", ".join(missing)
            + "。请写入 skill .env 或设置环境变量后再用；视频/图片交付可先落本地。")
    return {"endpoint_url": env.get("OSS_ENDPOINT_URL"),
            "bucket_name": env.get("OSS_BUCKET_NAME"),
            "access_key_id": env.get("OSS_ACCESS_KEY_ID"),
            "secret_key": env.get("OSS_SECRET_KEY_SECRET"),
            "cdn_base": env.get("OSS_ANTI_THEFT_CHAIN").rstrip("/")}


class SourceReader(Protocol):
    def fetch(self) -> tuple[bytes, str]:
        ...


@dataclass(frozen=True)
class RemoteSource:
    url: str

    def fetch(self) -> tuple[bytes, str]:
        request = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read(), response.headers.get("Content-Type", "")


@dataclass(frozen=True)
class LocalSource:
    path: str

    def fetch(self) -> tuple[bytes, str]:
        path = Path(self.path)
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {self.path}")
        content_type, _ = mimetypes.guess_type(self.path)
        return path.read_bytes(), content_type or ""


def source_reader(source: str) -> SourceReader:
    if source.lower().startswith(("http://", "https://")):
        return RemoteSource(source)
    return LocalSource(source)


def _fetch(source: str) -> tuple[bytes, str]:
    return source_reader(source).fetch()


@dataclass(frozen=True)
class UploadObject:
    data: bytes
    source: str
    prefix: str
    content_type: str

    @property
    def key(self) -> str:
        digest = hashlib.md5(self.data).hexdigest()
        extension = Path(self.source.split("?")[0]).suffix
        if not extension:
            extension = mimetypes.guess_extension(
                mimetypes.guess_type(self.source)[0] or "application/octet-stream") or ""
        return f"{self.prefix}{digest}{extension}"

    @property
    def upload_content_type(self) -> str:
        return self.content_type or "application/octet-stream"


def _object_key(data: bytes, source: str, prefix: str) -> str:
    return UploadObject(data, source, prefix, "").key


def upload_one(source: str, prefix: str, conf: dict) -> str:
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise RuntimeError("缺少依赖 boto3，请先运行: pip install boto3")
    data, content_type = _fetch(source)
    item = UploadObject(data, source, prefix, content_type)
    key = item.key
    client = boto3.client(
        "s3",
        aws_access_key_id=conf["access_key_id"],
        aws_secret_access_key=conf["secret_key"],
        endpoint_url=conf["endpoint_url"],
        config=Config(signature_version="s3v4",
                      s3={"addressing_style": "virtual"}))
    client.upload_fileobj(io.BytesIO(item.data), conf["bucket_name"], key,
                          ExtraArgs={"ContentType": item.upload_content_type})
    return f"{conf['cdn_base']}/{key}"


def main() -> None:
    ap = argparse.ArgumentParser(description="drama 上传 CLI（S3/CDN，内容 MD5 幂等）")
    ap.add_argument("paths", nargs="+", help="本地路径或 http(s) URL")
    ap.add_argument("--prefix", default="", help="对象 key 前缀，如 shots/")
    ap.add_argument("--env-file", help="显式 .env 路径")
    args = ap.parse_args()

    env.set_env_file(args.env_file)
    conf = _s3_config()
    items, failed = [], 0
    for source in args.paths:
        try:
            url = upload_one(source, args.prefix, conf)
            items.append({"source": source, "ok": True, "url": url})
        except (OSError, ValueError, RuntimeError) as exc:
            items.append({"source": source, "ok": False, "error": str(exc)})
            failed += 1
    env.emit({"ok": not failed, "uploaded": len(items) - failed,
              "failed": failed, "items": items})
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    env.run_cli(main)
