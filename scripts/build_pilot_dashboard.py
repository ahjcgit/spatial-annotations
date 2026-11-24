#!/usr/bin/env python3
"""Audit the November 19 archive and build a static, source-linked results dashboard.

No inference, device access or third-party dependencies. Original evidence is read-only.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import statistics
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "experiments/codex-glasses/2026-11-19"
RUNS = ("setup-diagnostics", "small-text", "large-text", "qualitative-baseline")
BOUNDARIES = {
    "host_capture_to_image_ready_ms": ("host", "handoffReadyNs", "captureStartNs"),
    "codex_assisted_review_turnaround_ms": (
        "host",
        "submitReceivedNs",
        "handoffReadyNs",
    ),
    "host_submit_to_commit_observed_ms": (
        "host",
        "commitObservedNs",
        "submitReceivedNs",
    ),
    "host_capture_to_commit_observed_ms": (
        "host",
        "commitObservedNs",
        "captureStartNs",
    ),
    "device_apply_to_frame_commit_ms": (
        "device",
        "frameCommittedNs",
        "applyReceivedNs",
    ),
    "device_frame_to_frame_commit_ms": (
        "device",
        "frameCommittedNs",
        "frameCallbackReceivedNs",
    ),
}


def read(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else default


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(values):
    values = [v for v in values if v is not None]
    return {
        "n": len(values),
        "median": statistics.median(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "p95": None,
    }  # This archived pilot is too small for tail estimates.


def clocks(record):
    result = {}
    for key, (domain, end, start) in BOUNDARIES.items():
        values = record.get(domain, {})
        a, b = values.get(end), values.get(start)
        result[key] = (a - b) / 1e6 if a is not None and b is not None else None
    return result


def build_data(archive, out, repo=ROOT):
    archive, out, repo = (
        Path(archive).resolve(),
        Path(out).resolve(),
        Path(repo).resolve(),
    )
    checks, trials, references = [], [], []

    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    def link(path):
        return quote(os.path.relpath(path, out), safe="/")

    manifest = read(archive / "manifest.json")
    if not manifest:
        raise ValueError("The archive must contain manifest.json")
    for name, digest in manifest["files"].items():
        path = (archive / name).resolve()
        contained = path.is_relative_to(archive)
        check(
            "Archive SHA-256",
            contained and path.is_file() and sha(path) == digest,
            name,
        )
    for name, digest in manifest["final_source_sha256"].items():
        path = (repo / name).resolve()
        check(
            "Recorded source SHA-256",
            path.is_relative_to(repo) and path.is_file() and sha(path) == digest,
            name,
        )

    qualitative = read(archive / "qualitative-baseline/trial-summary.json", {})
    conditions = {r["trial_id"]: r["condition"] for r in qualitative.get("trials", [])}
    for r in qualitative.get("trials", []):
        archived = (
            archive / "qualitative-baseline" / r["trial_id"] / "codex-result.json"
        )
        references.append(
            {
                "original": r["result_file"],
                "status": "Relocated, present",
                "archived": link(archived),
            }
        )
        check("Relocated result reference", archived.is_file(), r["result_file"])
    feedback, metadata = [], []
    for run in RUNS:
        meta = read(archive / run / "run-metadata.json", {})
        if meta:
            metadata.append(
                {
                    "run": run,
                    "data": meta,
                    "url": link(archive / run / "run-metadata.json"),
                }
            )
        report = read(archive / run / "operator-feedback.json")
        if report:
            feedback.append(
                {
                    "run": run,
                    **report,
                    "url": link(archive / run / "operator-feedback.json"),
                }
            )
        for folder in sorted((archive / run).glob("trial-*")):
            if not folder.is_dir():
                continue
            result = read(folder / "result.json")
            failure = read(folder / "failure.json")
            capture = read(folder / "capture.json", {})
            q = read(folder / "codex-result.json", {})
            proposal = read(folder / "codex-proposal.json", {})
            is_qual = run == "qualitative-baseline"
            record = result or failure or {}
            labels = (
                q.get("result", {}).get("objects", [])
                if is_qual
                else proposal.get("labels", [])
            )
            normalized_labels = [
                {
                    "identity": l.get("identity", l["label"].split(":")[0]),
                    "label": l["label"],
                    "box": l["box"],
                    "uncertain": l["uncertain"],
                    "evidence": l["evidence"],
                }
                for l in labels
            ]
            status = (
                "review_only"
                if is_qual
                else "failed"
                if failure
                else "completed"
                if result
                else "incomplete"
            )
            computed = clocks(record)
            key = f"{run}/{folder.name}"
            source = folder / "source.jpg"
            if source.exists():
                expected = capture.get("device", capture).get(
                    "sourceSha256", capture.get("source_sha256")
                )
                check("Capture image association", sha(source) == expected, key)
                reviewed_hash = (
                    q.get("source", {}).get("source_sha256")
                    if is_qual
                    else proposal.get("sourceSha256")
                )
                check("Reviewed image association", sha(source) == reviewed_hash, key)
            if result:
                check(
                    "Commit request association",
                    result["requestId"]
                    == proposal.get("requestId")
                    == result["device"].get("requestId"),
                    key,
                )
                check(
                    "Commit image association",
                    result["device"].get("sourceSha256")
                    == proposal.get("sourceSha256"),
                    key,
                )
                check(
                    "Frame commit recorded",
                    bool(result["device"].get("frameCommittedNs")),
                    key,
                )
                for metric, actual in computed.items():
                    archived_value = result["metrics"].get(metric)
                    check(
                        "Raw clock recomputation",
                        actual is not None
                        and actual >= 0
                        and isinstance(archived_value, (float, int))
                        and math.isclose(actual, archived_value, abs_tol=0.00001),
                        key + ": " + metric,
                    )
                parts = [computed[k] for k in list(BOUNDARIES)[:3]]
                check(
                    "Host stages sum to total",
                    all(v is not None for v in parts)
                    and math.isclose(
                        sum(parts),
                        computed["host_capture_to_commit_observed_ms"],
                        abs_tol=0.00001,
                    ),
                    key,
                )
                check(
                    "Unmeasured quantities remain null",
                    result["metrics"].get("isolated_model_inference_ms") is None
                    and result["metrics"].get("optical_display_latency_ms") is None,
                    key,
                )
                for filename in (
                    "capture.json",
                    "source.jpg",
                    "display.png",
                    "codex-proposal.json",
                    "resources.jsonl",
                ):
                    check(
                        "Completed trial evidence",
                        (folder / filename).is_file(),
                        key + ": " + filename,
                    )
                check(
                    "Acknowledged labels match proposal",
                    [l["identity"] for l in result["device"].get("labels", [])]
                    == [l["identity"] for l in proposal.get("labels", [])],
                    key,
                )
            retries = [read(p) for p in sorted(folder.glob("capture-attempt-*.json"))]
            files = [
                {"name": p.name, "url": link(p)}
                for p in sorted(folder.iterdir())
                if p.suffix in (".json", ".jsonl", ".jpg", ".png")
            ]
            trials.append(
                {
                    "id": key,
                    "run": run,
                    "trial": folder.name,
                    "status": status,
                    "condition": conditions.get(folder.name)
                    if is_qual
                    else "two_labels"
                    if len(labels) == 2
                    else "no_labels"
                    if proposal
                    else "no_review",
                    "labels": normalized_labels,
                    "metrics": computed,
                    "failure": failure,
                    "review": q.get(
                        "reasoning_summary", proposal.get("reasoning_summary")
                    ),
                    "captured_at": capture.get("captured_at"),
                    "files": files,
                    "source": link(source) if source.is_file() else None,
                    "display": link(folder / "display.png")
                    if (folder / "display.png").is_file()
                    else None,
                    "expiry_observed": bool(result["device"].get("labelsClearedNs"))
                    if result
                    else None,
                    "source_age_at_apply_ms": record.get("device", {}).get(
                        "sourceAgeAtApplyMs"
                    ),
                    "resources": result.get("resource_summary") if result else None,
                    "hold_status_saved": "display_hold" in record,
                    "retries": retries,
                }
            )

    completed = [t for t in trials if t["status"] == "completed"]
    failed = [t for t in trials if t["status"] == "failed"]
    reviews = [t for t in trials if t["status"] == "review_only"]
    for key, value in (
        ("completed_timed_trials", len(completed)),
        ("failed_attempts", len(failed)),
        ("qualitative_snapshot_trials", len(reviews)),
    ):
        check("Manifest inventory", manifest.get(key) == value, key)
    # Compare stored aggregate tables against raw-clock recomputation, not just each other.
    with (archive / "report/trials.csv").open(newline="") as f:
        stored = list(csv.DictReader(f))
    indexed = {t["id"]: t for t in completed}
    check(
        "Archived CSV inventory",
        {r["run"] + "/" + r["trial"] for r in stored} == set(indexed)
        and len(stored) == len(indexed),
        "report/trials.csv",
    )
    for row in stored:
        trial = indexed.get(row["run"] + "/" + row["trial"])
        if trial:
            for name, value in trial["metrics"].items():
                try:
                    equal = math.isclose(float(row[name]), value, abs_tol=0.00001)
                except (ValueError, KeyError, TypeError):
                    equal = False
                check("Archived CSV timing", equal, trial["id"] + ": " + name)
    groups = []
    for run, condition in sorted({(t["run"], t["condition"]) for t in completed}):
        selected = [
            t for t in completed if (t["run"], t["condition"]) == (run, condition)
        ]
        groups.append(
            {
                "run": run,
                "condition": condition,
                "n": len(selected),
                "metrics": {
                    k: stats([t["metrics"][k] for t in selected]) for k in BOUNDARIES
                },
            }
        )
    totals = {k: stats([t["metrics"][k] for t in completed]) for k in BOUNDARIES}
    review_ms = sum(
        t["metrics"]["codex_assisted_review_turnaround_ms"] for t in completed
    )
    total_ms = sum(
        t["metrics"]["host_capture_to_commit_observed_ms"] for t in completed
    )
    resource_ranges = {}
    for process in ("device", "host"):
        resource_ranges[process] = stats(
            [t["resources"].get(process, {}).get("peak_rss_mib") for t in completed]
        )
    return {
        "schema_version": 1,
        "archive": archive.name,
        "evidence_commit": "33666abf62b4e67117bedf75745c93e8c48b45a6",
        "integrity": {
            "ok": all(c["passed"] for c in checks),
            "checks": checks,
            "archive_files": len(manifest["files"]),
            "source_files": len(manifest["final_source_sha256"]),
        },
        "inventory": {
            "completed": len(completed),
            "failed": len(failed),
            "qualitative": len(reviews),
            "qualitative_retries": sum(len(t["retries"]) for t in reviews),
            "expiry_observed": sum(t["expiry_observed"] for t in completed),
        },
        "totals": totals,
        "review_fraction": review_ms / total_ms if total_ms else None,
        "groups": groups,
        "trials": trials,
        "feedback": feedback,
        "metadata": metadata,
        "resource_ranges": resource_ranges,
        "relocated_references": references,
        "links": {
            "original_report": link(archive / "report/index.html"),
            "manifest": link(archive / "manifest.json"),
            "methodology": link(archive / "README.md"),
            "resource_csv": link(archive / "report/phase-resources.csv"),
            "validation": link(archive / "validation.json"),
        },
    }


def build(archive=DEFAULT, out=None, repo=ROOT):
    archive = Path(archive).resolve()
    out = Path(out).resolve() if out else archive / "dashboard"
    # Never replace the original report or raw archive directories, including via symlinks.
    protected = read(archive / "manifest.json", {}).get("files", {})
    targets = [
        out / n
        for n in (
            "index.html",
            "dashboard.css",
            "dashboard.js",
            "data.js",
            "analysis.json",
            "trials.csv",
        )
    ]
    if any(
        p.resolve() == (archive / name).resolve() for p in targets for name in protected
    ):
        raise ValueError(
            "Output would overwrite archived evidence; choose a new directory"
        )
    data = build_data(archive, out, repo)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "dashboard.css", "dashboard.js"):
        shutil.copyfile(ROOT / "demo/pilot-results" / name, out / name)
    serialized = json.dumps(data, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    (out / "analysis.json").write_text(serialized)
    (out / "data.js").write_text("window.PILOT_DATA = " + serialized.rstrip() + ";\n")
    with (out / "trials.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "status", "condition", "expiry_observed", *BOUNDARIES],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(
            {
                **{k: t[k] for k in ("id", "status", "condition", "expiry_observed")},
                **t["metrics"],
            }
            for t in data["trials"]
        )
    print(
        json.dumps(
            {
                "dashboard": str(out / "index.html"),
                "checks": len(data["integrity"]["checks"]),
                "integrity_ok": data["integrity"]["ok"],
                **data["inventory"],
            }
        )
    )
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = build(args.archive, args.out)
    raise SystemExit(0 if result["integrity"]["ok"] else 1)
