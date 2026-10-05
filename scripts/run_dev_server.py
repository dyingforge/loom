from pathlib import Path
import os
import sys

from dotenv import load_dotenv
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
env_setting = os.environ.get("LOOM_ENV_FILE")
ENV_FILE = Path(env_setting) if env_setting else ROOT / ".env"
if env_setting and not ENV_FILE.is_file():
    raise SystemExit(f"LOOM_ENV_FILE 指向的文件不存在：{ENV_FILE}")
load_dotenv(ENV_FILE)

if __name__ == "__main__":
    uvicorn.run("server.adapters.http:app", host="127.0.0.1",
                port=int(os.environ.get("PORT", "8000")))
