"""Sequence-level comparison and standalone plots; never infer unavailable results."""

import csv
import json
import statistics
from pathlib import Path

from app.identity.evaluation import latency
from app.identity.study import flat_metrics


def report(root):
    root = Path(root)
    results = [json.loads(p.read_text()) for p in sorted(root.glob("*/summary.json"))]
    unavailable = [
        json.loads(p.read_text()) for p in sorted(root.glob("*/unavailable.json"))
    ]
    if not results:
        if not unavailable:
            raise ValueError("No completed study runs")
        (root / "comparison.json").write_text(
            json.dumps({"runs": [], "unavailable": unavailable}, indent=2)
        )
        print(
            "No configured methods ran; see comparison.json (not a passed benchmark)."
        )
        return
    # Hold references, data, masks, and initial evidence fixed. Context/provider budgets remain explicit in summaries.
    for key in (
        "dataset_sha256",
        "gallery_sha256",
        "initializations_sha256",
        "pace",
        "source_sha256",
    ):
        if len({json.dumps(r.get(key), sort_keys=True) for r in results}) != 1:
            raise ValueError("Incomparable runs: " + key)
    appearance_runs = [r for r in results if r["method"] != "H0"]
    for key in ("calibration", "descriptor"):
        if len({json.dumps(r.get(key), sort_keys=True) for r in appearance_runs}) > 1:
            raise ValueError("Incomparable appearance settings: " + key)
    for key in (
        "max_image_dimension",
        "max_references",
        "max_objects",
        "requests_per_minute",
        "acceptance",
    ):
        relevant = [r for r in results if r["method"] in ("H2", "H3", "H4")]
        if len({r["configuration"][key] for r in relevant}) > 1:
            raise ValueError("Incomparable reasoning budget/policy: " + key)
    for pass_name in {r["pass"] for r in results}:
        if (
            len({r["detections_sha256"] for r in results if r["pass"] == pass_name})
            != 1
        ):
            raise ValueError("Detection outputs differ within pass")
    rows = []
    for r in results:
        for sequence in r["sequences"]:
            rows.append(
                {
                    "method": r["method"],
                    "pass": r["pass"],
                    "protocol": r["protocol"],
                    "trial": r["trial"],
                    "sequence": sequence["id"],
                    "recording_id": sequence["recording_id"],
                    "condition": sequence["condition"],
                    "evidence_kind": r["evidence_kind"],
                    "provider_kind": r["provider_kind"],
                    "peak_runner_rss_mib": r["peak_runner_rss_mib"],
                    **flat_metrics(sequence["metrics"]),
                }
            )
    with (root / "comparison.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(dict.fromkeys(k for row in rows for k in row))
        )
        writer.writeheader()
        writer.writerows(rows)
    unavailable = [
        json.loads(p.read_text()) for p in sorted(root.glob("*/unavailable.json"))
    ]
    (root / "comparison.json").write_text(
        json.dumps({"runs": results, "unavailable": unavailable}, indent=2) + "\n"
    )
    method_rows = []
    for pass_name, protocol, method in sorted(
        {(r["pass"], r["protocol"], r["method"]) for r in results}
    ):
        selected = [
            r
            for r in results
            if (r["pass"], r["protocol"], r["method"]) == (pass_name, protocol, method)
        ]
        stats = [s["metrics"] for r in selected for s in r["sequences"]]
        events = []
        for path in root.glob("*/summary.json"):
            value = json.loads(path.read_text())
            if (value["pass"], value["protocol"], value["method"]) == (
                pass_name,
                protocol,
                method,
            ):
                events.extend(
                    json.loads(line)
                    for line in (path.parent / "vlm-events.jsonl")
                    .read_text()
                    .splitlines()
                )
        count = lambda key: sum(s[key] for s in stats)
        known = count("known_object_observations")
        total = count("total_evaluated_observations")
        method_rows.append(
            {
                "method": method,
                "pass": pass_name,
                "protocol": protocol,
                "status": "executed",
                "evidence_kind": selected[0]["evidence_kind"],
                "provider_kind": selected[0]["provider_kind"],
                "trials": len(selected),
                "observations": total,
                "correct": count("correct_assignments"),
                "incorrect": count("incorrect_assignments"),
                "unknown": count("unknown_observations"),
                "correct_label_coverage": count("correct_assignments") / known
                if known
                else None,
                "wrong_object_label_rate": count("incorrect_assignments") / total
                if total
                else None,
                "provider_calls": len(events),
                "provider_latency_median_ms": latency(
                    [e["latency_ms"] for e in events]
                )["median_ms"],
                "provider_latency_p95_ms": latency([e["latency_ms"] for e in events])[
                    "p95_ms"
                ],
                "max_runner_peak_rss_mib": max(
                    r["peak_runner_rss_mib"] for r in selected
                ),
            }
        )
    method_rows.extend(
        {k: u[k] for k in ("method", "pass", "protocol", "status", "reason")}
        for u in unavailable
    )
    with (root / "method-summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(dict.fromkeys(k for row in method_rows for k in row))
        )
        writer.writeheader()
        writer.writerows(method_rows)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for pass_name, protocol in sorted({(r["pass"], r["protocol"]) for r in results}):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.7))
        legend = []
        for method_index, method in enumerate(("H0", "H1", "H2", "H3", "H4")):
            selected = [
                r
                for r in results
                if r["pass"] == pass_name
                and r["protocol"] == protocol
                and r["method"] == method
            ]
            if not selected:
                continue
            sequences = [s["metrics"] for r in selected for s in r["sequences"]]
            coverage = [
                s["correct_label_coverage"]
                for s in sequences
                if s["correct_label_coverage"] is not None
            ]
            wrong = [
                s["wrong_object_label_rate"]
                for s in sequences
                if s["wrong_object_label_rate"] is not None
            ]
            if not coverage:
                continue
            c = statistics.mean(coverage)
            w = statistics.mean(wrong)
            calls = sum(s["vlm_requests"] for s in sequences)
            timings = [
                s["vlm_latency"]["mean_ms"]
                for s in sequences
                if s["vlm_latency"]["mean_ms"] is not None
            ]
            mean_latency = statistics.mean(timings) if timings else 0
            for axis, x in [(axes[0], w), (axes[1], mean_latency)]:
                axis.scatter(
                    x,
                    c,
                    s=85,
                    label=method,
                    marker=("o", "s", "^", "v", "x")[method_index],
                    facecolors="none" if method_index < 4 else None,
                    edgecolors=f"C{method_index}" if method_index < 4 else None,
                    color=f"C{method_index}",
                )
            legend.append(f"{method}: {calls} calls")
        axes[0].set_xlabel("Wrong-object label rate (sequence mean)")
        axes[1].set_xlabel(
            "Provider latency: mean of sequence means (ms; 0 = no calls)"
        )
        for axis in axes:
            axis.set_ylabel("Correct-label coverage (sequence mean)")
            axis.set_ylim(-0.05, 1.1)
            axis.spines[["top", "right"]].set_visible(False)
            axis.legend(loc="lower right", fontsize=8)
        axes[0].set_xlim(-0.003, max(0.05, axes[0].get_xlim()[1]))
        fig.suptitle(
            f"Pass {pass_name} / {protocol} — {results[0]['evidence_kind']}",
            x=0.02,
            ha="left",
        )
        fig.text(
            0.02,
            0.02,
            "; ".join(legend)
            + " (coincident markers overlap)\nMock/synthetic timings are software checks. Frames and repeated inference trials are not independent recordings.",
            fontsize=8,
        )
        fig.tight_layout(rect=(0, 0.12, 1, 0.95))
        fig.savefig(root / f"tradeoff-{pass_name}-{protocol}.png", dpi=140)
        fig.savefig(root / f"tradeoff-{pass_name}-{protocol}.svg")
        plt.close(fig)
    print("Comparison JSON/CSV and correctness/latency plots:", root)
