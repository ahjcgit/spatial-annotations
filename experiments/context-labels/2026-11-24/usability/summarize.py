"""Recompute descriptive summaries from per-decision, local and archived RayNeo logs."""
import json
import math
import statistics
from pathlib import Path

from measure import ARCHIVE, HERE, PILOT, prepare, rows, schedule


def stats(values):
    values = sorted(map(float, values))
    n = len(values)
    return {"n": n, "median": statistics.median(values), "min": min(values), "max": max(values),
            "p95": values[math.ceil(.95 * n)-1] if n >= 20 else None}


def fields(records, names):
    return {name: stats([row[name] for row in records]) for name in names}


def verify_cards(directory):
    import hashlib
    from tempfile import TemporaryDirectory
    from PIL import Image

    recorded = rows(directory / "reviews.csv")
    with TemporaryDirectory() as tmp, Image.open(PILOT / "references.png") as references:
        path = Path(tmp) / "input.jpg"
        for (case, mode), row in zip(schedule(), recorded, strict=True):
            source = ARCHIVE / case["source"] / "source.jpg"
            if hashlib.sha256(source.read_bytes()).hexdigest() != case["source_sha256"]:
                raise ValueError("Archived source hash mismatch")
            prepare(case, mode, references.convert("RGB"), path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"Card hash mismatch on trial {row['trial']}")


def summarize(directory):
    reviews = rows(directory / "reviews.csv")
    expected = [(case["probe"], mode) for case, mode in schedule()]
    if [(r["probe"], r["mode"]) for r in reviews] != expected:
        raise ValueError("Missing, reordered or duplicate reviews")
    key = {r["probe"]: r["source_identity"] for r in rows(PILOT / "key.csv")}
    for i, r in enumerate(reviews, 1):
        if int(r["trial"]) != i or r["decision"] not in ("A", "B", "unknown"):
            raise ValueError("Invalid decision")
        for col, end, start in [("total_ms", "receipt_ns", "start_ns"),
                                ("prepare_ms", "ready_ns", "start_ns"),
                                ("review_ms", "receipt_ns", "ready_ns")]:
            elapsed = (int(r[end]) - int(r[start])) / 1e6
            if elapsed < 0 or not math.isclose(elapsed, float(r[col])):
                raise ValueError(f"Invalid clock boundary for trial {i}")
    results = {}
    for mode in ("crop", "scene"):
        records = [r for r in reviews if r["mode"] == mode]
        targets = [r for r in records if key[r["probe"]] != "none"]
        negative = [r for r in records if key[r["probe"]] == "none"]
        results[mode] = dict(
            fields(records, ["total_ms", "review_ms", "prepare_ms", "worker_cpu_ms", "jpeg_bytes", "rss_ready_mib"]),
            correct=sum(r["decision"] == key[r["probe"]] for r in targets),
            wrong=sum(r["decision"] not in ("unknown", key[r["probe"]]) for r in targets),
            withheld=sum(r["decision"] == "unknown" for r in targets),
            negatives_rejected=sum(r["decision"] == "unknown" for r in negative),
            correct_targets_by_5s=sum(r["decision"] == key[r["probe"]] and float(r["total_ms"]) <= 5000 for r in targets),
        )
    lookup = {(r["probe"], r["mode"]): float(r["total_ms"]) for r in reviews}
    results["paired_scene_minus_crop_ms"] = stats([lookup[p, "scene"]-lookup[p, "crop"] for p in key])
    baseline = rows(directory / "appearance.csv")
    results["local_appearance"] = fields(baseline, ["wall_ms", "cpu_ms", "rss_mib"])
    historical = rows(ARCHIVE / "report/trials.csv")
    results["archived_completed_trials"] = fields(historical, [
        "host_capture_to_commit_observed_ms", "host_submit_to_commit_observed_ms", "device_cpu_seconds",
        "device_peak_rss_mib", "host_peak_rss_mib", "host_cpu_seconds", "device_mean_cpu_percent_one_core"])
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=HERE)
    parser.add_argument("--verify-inputs", action="store_true", help="Rebuild and hash each presented JPEG")
    args = parser.parse_args()
    if args.verify_inputs:
        verify_cards(args.data)
    print(json.dumps(summarize(args.data), indent=2))
