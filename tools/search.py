from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.lib import env


def web_search(query: str, count: int) -> list[dict]:
    conf = env.require("SEARCH_ENGINE_HOST", "SEARCH_ENGINE_SUBSCRIPTION_KEY")
    url = conf["SEARCH_ENGINE_HOST"].rstrip("/") + "?" + urlencode(
        {"q": query, "count": count})
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + conf["SEARCH_ENGINE_SUBSCRIPTION_KEY"],
                      "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"搜索服务 HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"搜索服务连接失败: {exc.reason}") from None
    return body.get("webPages", {}).get("value", []) or []


def main() -> None:
    ap = argparse.ArgumentParser(description="drama 联网文本搜索 CLI（小算 Smart Search）")
    ap.add_argument("query")
    ap.add_argument("-n", "--count", type=int, default=8, help="返回条数（默认 8）")
    ap.add_argument("--pretty", action="store_true", help="人类可读列表（默认 JSON）")
    ap.add_argument("--env-file", help="显式 .env 路径")
    args = ap.parse_args()

    env.set_env_file(args.env_file)
    results = web_search(args.query, args.count)
    if args.pretty:
        for i, item in enumerate(results, 1):
            print(f"{i}. {item.get('name', '')}\n"
                  f"   {item.get('url', '')}\n"
                  f"   {item.get('snippet', '')}\n")
        return
    env.emit({"ok": True, "query": args.query, "count": len(results),
              "results": results})


if __name__ == "__main__":
    env.run_cli(main)
