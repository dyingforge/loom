"""01 探针：真实 MiniMax 端点连通性与最小可用验证。

不模拟任何返回；网络/凭据/模型任一失败均按 AGENTS.md 第 9 条如实抛出。
"""
import os
import sys
import json
import urllib.request
import urllib.error


def main() -> int:
    key = os.environ.get("MINIMAX_API_KEY")
    if not key:
        print("MINIMAX_API_KEY missing in environment", file=sys.stderr)
        return 2
    endpoint = os.environ.get(
        "MINIMAX_CHAT_URL",
        "https://api.minimax.chat/v1/text/chatcompletion_v2",
    )
    body = json.dumps({
        "model": "MiniMax-M2.7",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            print("status:", resp.status)
            print("body:", raw)
            return 0
    except urllib.error.HTTPError as e:
        print("HTTPError:", e.code, e.reason, file=sys.stderr)
        print(e.read().decode("utf-8", "replace"), file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print("URLError:", e.reason, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
