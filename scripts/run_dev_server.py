from pathlib import Path
import os
import sys

from dotenv import load_dotenv
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

if __name__ == "__main__":
    uvicorn.run("server.adapters.http:app", host="127.0.0.1",
                port=int(os.environ.get("PORT", "8000")))
