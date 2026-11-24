"""Collection scaffold, archive importer and byte-level seals for the focal-region study."""

import csv
import hashlib
import json
import math
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image

from app.identity.tracker import valid_box

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "experiments/codex-glasses/2026-11-19"
SHEET = ROOT / "experiments/context-labels/temporal-judge/next-takes.csv"


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fresh(path):
    path.mkdir(parents=True, exist_ok=False)
    return path


def blank(out):
    fresh(out)
    (out / "images").mkdir()
    (out / "refs").mkdir()
    return {
        "references": {a: [f"refs/{a}-{i}.jpg" for i in range(1, 4)] for a in "AB"},
        "cases": [],
    }


def init(out, split="evaluation"):
    data = blank(out)
    truth = {}
    data["split"] = split
    chosen = set()
    with SHEET.open() as f, (out / "operator.csv").open("x", newline="") as plan:
        reader = csv.DictReader(f)
        writer = csv.DictWriter(plan, fieldnames=reader.fieldnames, lineterminator="\n")
        writer.writeheader()
        for take in reader:
            if split == "development" and take["condition"] in chosen:
                continue
            chosen.add(take["condition"])
            writer.writerow(take)
            name = f"s{take['session']}-t{int(take['take']):02}"
            for i, stage in enumerate(("start", "challenge", "reveal")):
                key = f"{name}-{i + 1}"
                data["cases"].append(
                    {
                        "id": key,
                        "take": name,
                        "image": f"images/{key}.jpg",
                        "box": None,
                        "time_ms": None,
                        "prior": None if i == 0 else f"{name}-1",
                        "gap": True,
                        "deadline_ms": None,
                        "second": None,
                    }
                )
                truth[key] = {
                    "condition": take["condition"],
                    "stage": stage,
                    "body": None,
                    "identifiable": None,
                }
    save(out / "observations.json", data)
    save(out / "truth.json", truth)


def archive(out, link_reveal=False):
    data = blank(out)
    truth = {}
    # Fixed crops from qualitative trial 01; copy the archived bytes so field laptops
    # can verify the pilot seal regardless of their Pillow/libpng encoder version.
    for alias in "AB":
        path = f"refs/{alias}.png"
        shutil.copyfile(ROOT / "experiments/context-labels/judge-pilot" / path, out / path)
        data["references"][alias] = [path]
    # Previously reviewed visible extents. Crop-coordinate order never encodes the alias.
    targets = [
        ("qualitative-baseline", 2, "swap", "B", (96, 15, 185, 295), True),
        ("qualitative-baseline", 3, "occlusion", "B", (87, 15, 183, 108), False),
        ("qualitative-baseline", 4, "reveal", "B", (92, 15, 179, 295), True),
        ("large-text", 2, "distractor", "none", (58, 217, 151, 277), False),
        ("large-text", 3, "return", "A", (265, 95, 314, 290), True),
    ]
    for group in ("qualitative-baseline", "large-text"):
        folders = sorted((ARCHIVE / group).glob("trial-*/source.jpg"))
        start = None
        prev_id = None
        for image in folders:
            trial = int(image.parent.name.split("-")[-1])
            found = next((x for x in targets if x[:2] == (group, trial)), None)
            if not found and trial != 1:
                continue
            condition, body, box, identifiable = (
                found[2:]
                if found
                else (
                    "enrollment" if group == "qualitative-baseline" else "visible",
                    "A",
                    (86, 44, 154, 295)
                    if group == "qualitative-baseline"
                    else (298, 95, 356, 290),
                    True,
                )
            )
            key = f"p{len(data['cases']) + 1:02}"
            stamp = (
                datetime.fromisoformat(
                    read(image.parent / "capture.json")["captured_at"]
                ).timestamp()
                * 1000
            )
            if start is None:
                start = stamp
            target = f"images/{key}.jpg"
            shutil.copyfile(image, out / target)
            data["cases"].append(
                {
                    "id": key,
                    "take": group,
                    "time_ms": round(stamp - start),
                    "image": target,
                    "box": box,
                    "prior": prev_id,
                    "gap": True,
                    "second": None,
                    "deadline_ms": None,
                }
            )
            truth[key] = {
                "condition": condition,
                "stage": condition,
                "body": body,
                "identifiable": identifiable,
            }
            prev_id = key
    if link_reveal:
        # Alternative offline acquisition protocol. Each later capture is scored separately.
        for before, after in (("p02", "p03"), ("p03", "p04")):
            next(c for c in data["cases"] if c["id"] == before)["second"] = after
    save(out / "observations.json", data)
    save(out / "truth.json", truth)


def asset(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or invalid image: {name}")
    return path


def number(value):
    return type(value) in (float, int) and math.isfinite(value)


def fingerprint(root):
    data = read(root / "observations.json")
    if set(data["references"]) != {"A", "B"} or not data["cases"]:
        raise ValueError("Two reference galleries and observations are required")
    files = {"observations.json": sha(root / "observations.json")}

    def image(name):
        path = asset(root, name)
        files[name] = sha(path)
        with Image.open(path) as im:
            return im.size

    for names in data["references"].values():
        if not names or len(names) > 8:
            raise ValueError("Provide 1–8 cropped references per alias")
        for name in names:
            image(name)
    by_id = {}
    last = {}
    for c in data["cases"]:
        stamp = c["time_ms"]
        if (
            not isinstance(c["id"], str)
            or not c["id"]
            or c["id"] in by_id
            or not number(stamp)
            or stamp < 0
            or stamp <= last.get(c["take"], -1)
        ):
            raise ValueError(
                "Expected unique IDs and increasing capture times within each take"
            )
        last[c["take"]] = stamp
        by_id[c["id"]] = c
        if c["box"] is None:
            raise ValueError(f"Mark the focal region for {c['id']}")
        valid_box(c["box"], image(c["image"]))
        if type(c["gap"]) is not bool:
            raise ValueError("Record whether there was an observation gap")
        if c.get("deadline_ms") is not None and (
            not number(c["deadline_ms"]) or c["deadline_ms"] <= 0
        ):
            raise ValueError(
                "Deadline is elapsed positive milliseconds from this image"
            )
    for c in by_id.values():
        for field in ("prior", "second"):
            if c.get(field) is not None:
                other = by_id.get(c[field])
                if (
                    not other
                    or other["take"] != c["take"]
                    or (other["time_ms"] < c["time_ms"]) != (field == "prior")
                    or other == c
                ):
                    raise ValueError(f"Noncausal or cross-take {field}: {c['id']}")
        trail = c.get("trail", [])
        if not isinstance(trail, list) or len(trail) > 8:
            raise ValueError("Use up to eight intermediate observations")
        if trail:
            if not c.get("prior"):
                raise ValueError("Trail requires an earlier reference observation")
            times = [by_id[c["prior"]]["time_ms"]]
            for entry in trail:
                if not number(entry["time_ms"]):
                    raise ValueError("Invalid trail timestamp")
                image(entry["image"])
                times.append(entry["time_ms"])
            times.append(c["time_ms"])
            if any(b <= a for a, b in zip(times, times[1:])):
                raise ValueError(
                    "Intermediate views must precede the decision in capture order"
                )
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def truth_key(root, cases):
    truth = read(root / "truth.json")
    if set(truth) != {c["id"] for c in cases}:
        raise ValueError("Truth must cover every focal opportunity")
    for row in truth.values():
        if (
            row["body"] not in ("A", "B", "C", "none")
            or type(row["identifiable"]) is not bool
            or not row["condition"]
        ):
            raise ValueError(
                "Complete body, identifiability and condition in truth.json"
            )
    return truth


def seal(root):
    public = fingerprint(root)
    truth_key(root, read(root / "observations.json")["cases"])
    with (root / "seal.json").open("x") as f:
        json.dump(
            {"observations": public, "truth": sha(root / "truth.json")}, f, indent=2
        )


def verified(root):
    if fingerprint(root) != read(root / "seal.json")["observations"]:
        raise ValueError("Observations changed after sealing")
    return read(root / "observations.json")
