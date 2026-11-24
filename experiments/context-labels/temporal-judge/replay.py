"""Timed, interactive image review. Only the card and opaque trial ID go to the reviewer."""
import argparse
import hashlib
import json
import platform
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, __version__ as pillow_version

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "codex-glasses/2026-11-19"
GALLERY = HERE.parent / "2026-11-24/references.png"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def capture_time(frame):
    doc = json.loads((frame.parent / "capture.json").read_text())
    return datetime.fromisoformat(doc["captured_at"])


def schedule():
    starts, pairs = [], []
    for group in sorted({p.parent.parent for p in DATA.glob("*/*/source.jpg")}):
        frames = sorted(group.glob("*/source.jpg"), key=capture_time)
        starts.append((frames[0], None, "start"))
        pairs.extend(zip(frames[1:], frames))
    rng = random.Random(24112)
    rng.shuffle(pairs)
    early, late = [], []
    for i, (frame, previous) in enumerate(pairs):
        current, history = (frame, None, "current"), (frame, previous, "history")
        first, second = (current, history) if i % 2 else (history, current)
        early.append(first)
        late.append(second)
    rng.shuffle(late)
    return starts + early + late


def card(frame, previous, path):
    with Image.open(GALLERY) as gallery, Image.open(frame) as now:
        width, height = now.size
        image = Image.new("RGB", (gallery.width + width * (2 if previous else 1), height + 32), "white")
        draw = ImageDraw.Draw(image)
        draw.text((8, 8), "ENROLLMENT", fill="black")
        image.paste(gallery, (0, 32))
        draw.text((gallery.width + 8, 8), "CURRENT - decide here", fill="black")
        image.paste(now, (gallery.width, 32))
        if previous:
            delta = (capture_time(frame) - capture_time(previous)).total_seconds()
            draw.text((gallery.width + width + 8, 8), f"EARLIER - {delta:.1f} s ago", fill="black")
            with Image.open(previous) as old:
                image.paste(old, (gallery.width + width, 32))
        image.save(path, quality=90)


def memory():
    with open("/proc/self/status") as status:
        return {k: int(v.split()[0]) / 1024 for k, v in
                (line.split(":", 1) for line in status if line.startswith(("VmRSS:", "VmHWM:")))}


def policy(proposals):
    actions = {}
    for alias, (support, side, cue) in proposals.items():
        if support not in ("body", "part", "absent") or not cue.strip():
            raise ValueError("Invalid support or missing cue")
        if side not in (["none"] if support == "absent" else ["left", "right"]):
            raise ValueError("Invalid side")
        actions[alias] = {"action": {"body": "SHOW", "part": "VERIFY", "absent": "CLEAR"}[support],
                          "side": side}
    if actions["A"]["side"] == actions["B"]["side"] != "none":
        for action in actions.values():
            action["action"] = "VERIFY"
    return actions


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    (out / "environment.json").write_text(json.dumps({
        "start_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
        "python": platform.python_version(), "pillow": pillow_version,
        "cpu": next(line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")), "reviewer": "ongoing Codex vision conversation",
        "provider_revision": None, "inference_ms": None, "provider_resources": None, "billing": None,
        "energy": None, "device_display_ms": None, "gallery_sha256": digest(GALLERY.read_bytes()),
        "protocol_sha256": digest((HERE / "protocol.md").read_bytes())}, indent=2) + "\n")
    with (out / "events.jsonl").open("x") as log:
        for i, (frame, previous, mode) in enumerate(schedule(), 1):
            path = out / f"card-{i:02}.jpg"
            rss = memory()["VmRSS"]
            cpu = time.process_time_ns()
            start = time.monotonic_ns()
            card(frame, previous, path)
            data = path.read_bytes()
            sha = digest(data)
            ready_cpu = time.process_time_ns()
            ready = time.monotonic_ns()
            print(json.dumps({"trial": i, "card": str(path.resolve())}), flush=True)
            line = sys.stdin.readline()
            received = time.monotonic_ns()
            event = {"trial": i, "mode": mode, "frame": str(frame.parent.relative_to(DATA)),
                     "previous": str(previous.parent.relative_to(DATA)) if previous else None,
                     "card_sha256": sha, "bytes": len(data), "start_ns": start, "ready_ns": ready,
                     "received_ns": received}
            try:
                choice = json.loads(line)
                if choice["trial"] != i or set(choice["proposals"]) != {"A", "B"} or not choice["context"]:
                    raise ValueError("Invalid review")
                event["actions"] = policy(choice["proposals"])
                event.update(proposals=choice["proposals"], context=choice["context"], status="ok")
            except (ValueError, KeyError, TypeError) as error:
                event.update(status="failed", error=str(error))
            end = time.monotonic_ns()
            end_cpu = time.process_time_ns()
            mem = memory()
            event.update(end_ns=end, total_ms=(end-start)/1e6, prep_ms=(ready-start)/1e6,
                         review_ms=(received-ready)/1e6, policy_ms=(end-received)/1e6,
                         cpu_ms=(end_cpu-cpu)/1e6, prep_cpu_ms=(ready_cpu-cpu)/1e6,
                         rss_before_mib=rss, rss_after_mib=mem["VmRSS"], process_hwm_mib=mem["VmHWM"])
            log.write(json.dumps(event) + "\n")
            log.flush()
            if not line:
                raise SystemExit("Input closed")
    print("Complete", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    run(parser.parse_args().out)
