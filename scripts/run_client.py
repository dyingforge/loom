import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, default=ROOT / ".scratch/native/OctoScript-App-Design-Flow")
    parser.add_argument("--state", type=Path, default=ROOT / ".local-state/calendar")
    parser.add_argument("--port", default="8144")
    parser.add_argument("--hidden", action="store_true")
    args = parser.parse_args()
    temporary = ROOT / ".scratch/native-temp"
    temporary.mkdir(parents=True, exist_ok=True)
    command = [str(args.runtime.resolve() / "tools/octo"), "run", str(ROOT / "bundle"),
               "--port", args.port, "--detach", "--app-data", str(args.state.resolve())]
    if args.hidden:
        command.append("--hidden")
    subprocess.run(command, cwd=args.runtime.resolve(),
                   env=dict(os.environ, TMPDIR=str(temporary)), check=True)
