import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "bundle" / "assets" / "fonts" / "NotoSansSC.ttf"
WIDTH, HEIGHT = 1920, 1334
FONT_SIZE = 54


def render_caption(text, path):
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT), FONT_SIZE)
    box = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = box[2] - box[0], box[3] - box[1]
    pad_x, pad_y = 32, 18
    rect = ((WIDTH - text_width) // 2 - pad_x, HEIGHT - 190 - pad_y,
            (WIDTH + text_width) // 2 + pad_x, HEIGHT - 190 + text_height + pad_y)
    draw.rounded_rectangle(rect, radius=14, fill=(0, 0, 0, 150))
    draw.text(((WIDTH - text_width) // 2 - box[0], HEIGHT - 190 - box[1]),
              text, font=font, fill=(255, 255, 255, 255))
    image.save(path)


def main(run_dir):
    run_dir = Path(run_dir).resolve()
    frames_dir = run_dir / "frames"
    timeline = json.loads((run_dir / "timeline.json").read_text())

    concat = []
    captions = []
    clock = 0.0
    spans = []
    for entry in timeline:
        concat.append(f"file 'frames/{entry['file']}'")
        concat.append(f"duration {entry['duration']}")
        start, end = clock, clock + entry["duration"]
        clock = end
        if entry["caption"] not in captions:
            captions.append(entry["caption"])
        spans.append((captions.index(entry["caption"]), start, end))
    concat.append(f"file 'frames/{timeline[-1]['file']}'")
    (run_dir / "concat.txt").write_text("\n".join(concat) + "\n")

    for index, caption in enumerate(captions):
        render_caption(caption, run_dir / f"caption-{index}.png")

    chain = ["[0:v]fps=30,scale=1920:-2[v0]"]
    last = "v0"
    for index, start, end in spans:
        out = f"v{index + 1}_{int(start * 1000)}"
        chain.append(
            f"[{last}][{index + 1}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[{out}]")
        last = out
    (run_dir / "filter.txt").write_text(";\n".join(chain))
    filter_text = ";\n".join(chain)

    command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
               "-i", str(run_dir / "concat.txt")]
    for index in range(len(captions)):
        command += ["-i", str(run_dir / f"caption-{index}.png")]
    command += ["-filter_complex", filter_text,
                "-map", f"[{last}]", "-c:v", "libx264", "-crf", "20",
                "-preset", "medium", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(run_dir / "demo.mp4")]
    subprocess.run(command, check=True, cwd=str(frames_dir))
    print(json.dumps({"视频": str(run_dir / "demo.mp4"), "总时长": round(clock, 1)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
