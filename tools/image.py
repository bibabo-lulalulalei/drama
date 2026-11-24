from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from enum import Enum
import json
import math
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.lib import env

_HERE = Path(__file__).resolve().parent
_DEFAULT_CONFIG = _HERE / "image.json"


_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_STANDARD_SIZES = ((1, 1, "1024x1024"), (3, 2, "1536x1024"),
                   (2, 3, "1024x1536"))


class ImageGenerationRoute(str, Enum):


    GENERATIONS = "generations"
    EDITS = "edits"

    @property
    def endpoint(self) -> str:
        return "images/edits" if self is ImageGenerationRoute.EDITS else "images/generations"

    @property
    def tool(self) -> str:
        return "image_edit" if self is ImageGenerationRoute.EDITS else "image_gen"


def size_for_ratio(text: str) -> str:

    raw = (text or "").strip().replace("：", ":")
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError(f"--ratio 应为 '宽:高' 形式，收到 {text!r}")
    try:
        w, h = float(parts[0]), float(parts[1])
    except ValueError:
        raise ValueError(f"--ratio 数值非法：{text!r}") from None
    if not math.isfinite(w) or not math.isfinite(h) or w <= 0 or h <= 0:
        raise ValueError(f"--ratio 数值须为正：{text!r}")
    return min(_STANDARD_SIZES, key=lambda s: abs(w / h - s[0] / s[1]))[2]


def _multipart(fields, files):
    boundary = "----drama-img-" + uuid.uuid4().hex
    out = bytearray()
    for name, value in fields:
        out += (f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n").encode("utf-8")
    for name, path in files:
        mime = env.mime_of(path)
        if not mime or not mime.startswith("image/"):
            raise ValueError(f"不支持的参考图格式: {path}")
        out += (f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{os.path.basename(path)}"\r\n'
                f"Content-Type: {mime}\r\n\r\n").encode("utf-8")
        out += Path(path).read_bytes() + b"\r\n"
    out += f"--{boundary}--\r\n".encode("utf-8")
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _post(url, body, content_type, api_key, timeout):
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": content_type,
                 "Authorization": f"Bearer {api_key}",
                 "User-Agent": _UA}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"知脑中转 API HTTP {exc.code}: {detail[:600]}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"知脑中转连接失败: {exc.reason}") from None


@dataclass(frozen=True)
class ImageHttpRequest:
    url: str
    body: bytes
    content_type: str
    api_key: str
    timeout: int


@dataclass(frozen=True)
class ImageRequest:
    prompt_text: str
    refs: list[str]
    config: dict

    @property
    def route(self) -> ImageGenerationRoute:
        return ImageGenerationRoute.EDITS if self.refs else ImageGenerationRoute.GENERATIONS

    @property
    def model_id(self):
        return self.config.get("model_id")

    def validate(self) -> None:
        if not self.model_id:
            raise RuntimeError("image.json 缺 model_id")
        max_refs = self.config.get("max_reference_images") or 0
        if max_refs and len(self.refs) > max_refs:
            raise ValueError(f"参考图 {len(self.refs)} 张超过后端上限 {max_refs}")

    def prepare(self, api_key: str) -> ImageHttpRequest:
        self.validate()
        base = (env.get("GROK_MODELS_BASE_URL") or self.config.get("base_url")).rstrip("/")
        timeout = self.config.get("timeout_s") or 300
        params = {"model": self.model_id, "prompt": self.prompt_text}
        for key in ("size", "quality"):
            if self.config.get(key):
                params[key] = self.config[key]
        params.update(self.config.get("extra") or {})
        if self.route is ImageGenerationRoute.EDITS:
            for path in self.refs:
                if not Path(path).is_file():
                    raise FileNotFoundError(f"参考图不存在: {path}")
            fields = [(key, value if isinstance(value, str) else json.dumps(value))
                      for key, value in params.items()]
            body, content_type = _multipart(fields, [("image", path) for path in self.refs])
        else:
            body = json.dumps(params).encode("utf-8")
            content_type = "application/json"
        return ImageHttpRequest(
            url=f"{base}/{self.route.endpoint}", body=body,
            content_type=content_type, api_key=api_key, timeout=timeout,
        )


@dataclass(frozen=True)
class ImageResponse:
    raw: dict
    timeout: int

    def read(self) -> bytes:
        data = self.raw.get("data") or []
        if not data:
            raise RuntimeError(
                f"知脑中转返回无图片数据: {json.dumps(self.raw, ensure_ascii=False)[:500]}")
        first = data[0]
        if first.get("error"):
            raise RuntimeError(f"知脑中转图片错误: {json.dumps(first['error'], ensure_ascii=False)}")
        if first.get("b64_json"):
            return base64.b64decode(first["b64_json"])
        if first.get("url"):
            req = urllib.request.Request(first["url"], headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        raise RuntimeError(
            f"返回中既无 b64_json 也无 url: {json.dumps(first, ensure_ascii=False)[:500]}")


def generate(prompt_text: str, refs: list[str], config: dict) -> tuple[bytes, str]:
    request = ImageRequest(prompt_text, refs, config)
    api_key = env.require("XAI_API_KEY")["XAI_API_KEY"]
    prepared = request.prepare(api_key)
    result = _post(
        prepared.url, prepared.body, prepared.content_type,
        prepared.api_key, prepared.timeout,
    )
    return ImageResponse(result, prepared.timeout).read(), request.route.value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="drama 图片生成 CLI（知脑 gpt-image；image_gen/image_edit）")
    parser.add_argument("--env-file", help="显式 .env 路径")
    parser.add_argument("--config", help=f"后端配置 JSON（缺省 {_DEFAULT_CONFIG}）")
    prompt = parser.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt-file", help="提示词文件（取全文）")
    prompt.add_argument("--prompt", help="提示词文本")
    parser.add_argument("--ref", action="append", default=[],
                        help="参考图路径，可重复；存在即走 image_edit（/images/edits）")
    parser.add_argument("--ratio", help="画幅比例，如 16:9（映射最接近的标准尺寸档）")
    parser.add_argument("--size", help="显式标准尺寸（1024x1024/1536x1024/1024x1536），覆盖 --ratio")
    parser.add_argument("--out", required=True, help="成品图片落点")
    return parser


def request_from_args(args: argparse.Namespace, config: dict) -> ImageRequest:
    if args.size:
        if args.size not in {size[2] for size in _STANDARD_SIZES}:
            raise ValueError(f"--size 只接受标准三档: {[size[2] for size in _STANDARD_SIZES]}")
        config["size"] = args.size
    elif args.ratio:
        config["size"] = size_for_ratio(args.ratio)
    if args.prompt_file:
        prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")
    else:
        prompt_text = args.prompt
    if not prompt_text.strip():
        raise ValueError("提示词为空")
    refs = [str(Path(path).resolve()) for path in args.ref]
    return ImageRequest(prompt_text, refs, config)


def main() -> None:
    args = build_parser().parse_args()
    env.set_env_file(args.env_file)
    config_path = Path(args.config) if args.config else _DEFAULT_CONFIG
    config = json.loads(config_path.read_text(encoding="utf-8"))
    request = request_from_args(args, config)
    data, route = generate(request.prompt_text, request.refs, request.config)
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    env.emit({"ok": True, "tool": request.route.tool,
              "backend": "zhinao", "route": route,
              "model": request.model_id, "size": request.config.get("size"),
              "references": len(request.refs), "out": str(out), "bytes": len(data)})


if __name__ == "__main__":
    env.run_cli(main)
