"""Time one real review at a time on Linux. Supply one observed decision per input."""
import argparse
import csv
import hashlib
import json
import platform
import random
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, __version__ as pillow_version

HERE = Path(__file__).resolve().parent
PILOT = HERE.parent
ARCHIVE = PILOT.parents[1] / "codex-glasses/2026-11-19"


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def schedule():
    cases = rows(PILOT / "key.csv")
    rng = random.Random(2411)
    rng.shuffle(cases)
    # Exactly six crop-first and six scene-first pairs. Separate the paired views.
    first = [(case, "crop" if i % 2 else "scene") for i, case in enumerate(cases)]
    second = [(case, "scene" if mode == "crop" else "crop") for case, mode in first]
    rng.shuffle(second)
    return first + second


def prepare(case, mode, references, path):
    box = tuple(map(int, case["xyxy"].split()))
    with Image.open(ARCHIVE / case["source"] / "source.jpg") as frame:
        gray = ImageOps.grayscale(frame)
        if mode == "crop":
            target = ImageOps.contain(gray.crop(box), (180, 180), Image.Resampling.LANCZOS)
        else:
            target = gray.convert("RGB")
            left, top, right, bottom = box
            ImageDraw.Draw(target).rectangle((left-2, top-2, right+1, bottom+1),
                                              outline="red", width=2)
    card = Image.new("RGB", (references.width + target.width, max(references.height, target.height)), "white")
    card.paste(references)
    card.paste(target, (references.width, 0))
    card.save(path, quality=90)


def ms(ns):
    return ns / 1e6


def memory():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    raise RuntimeError("Linux VmRSS unavailable")


def review(out):
    out.mkdir(parents=True, exist_ok=False)
    path = out / "input.jpg"
    metadata = {"started_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
                "python": platform.python_version(), "pillow": pillow_version, "seed": 2411,
                "provider": "current Codex conversational image review", "standalone_inference_ms": None,
                "provider_cpu_gpu_memory": None, "provider_token_usage": None, "api_cost": None}
    (out / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
    with Image.open(PILOT / "references.png") as img:
        references = img.convert("RGB")
    with (out / "reviews.csv").open("x", newline="") as log:
        writer = csv.writer(log, lineterminator="\n")
        writer.writerow(["trial", "probe", "mode", "decision", "start_ns", "ready_ns", "receipt_ns",
                         "prepare_ms", "review_ms", "total_ms", "prep_cpu_ms", "worker_cpu_ms",
                         "rss_before_mib", "rss_ready_mib", "os_ru_maxrss_mib", "jpeg_bytes", "sha256"])
        for trial, (case, mode) in enumerate(schedule(), 1):
            before = memory()
            cpu_start = time.process_time_ns()
            start = time.monotonic_ns()
            prepare(case, mode, references, path)
            jpeg = path.read_bytes()
            digest = hashlib.sha256(jpeg).hexdigest()
            cpu_ready = time.process_time_ns()
            ready = time.monotonic_ns()
            rss_ready = memory()
            print(json.dumps({"trial": trial, "path": str(path.resolve())}), flush=True)
            line = sys.stdin.readline()
            receipt = time.monotonic_ns()
            cpu_end = time.process_time_ns()
            if not line:
                raise SystemExit("Incomplete review")
            serial, choice = line.split()
            if int(serial) != trial or choice not in ("A", "B", "unknown"):
                raise ValueError("Expected current trial number and A, B or unknown")
            writer.writerow([trial, case["probe"], mode, choice, start, ready, receipt,
                             ms(ready-start), ms(receipt-ready), ms(receipt-start),
                             ms(cpu_ready-cpu_start), ms(cpu_end-cpu_start), before, rss_ready,
                             resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, len(jpeg), digest])
            log.flush()
    print("Complete", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    review(parser.parse_args().out)
