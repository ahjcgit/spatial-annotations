"""Observed-frame metrics. Logs exclude note text, VLM evidence and credentials."""

import csv
import json
import statistics
from collections import Counter
from pathlib import Path

from .tracker import iou


def percentile(values, q):
    if not values:
        return None
    a = sorted(values)
    p = (len(a) - 1) * q
    i = int(p)
    return a[i] + (a[min(i + 1, len(a) - 1)] - a[i]) * (p - i)


def latency(values):
    return {
        "samples": len(values),
        "mean_ms": statistics.mean(values) if values else None,
        "median_ms": statistics.median(values) if values else None,
        "p95_ms": percentile(values, 0.95) if len(values) >= 20 else None,
    }


class Metrics:
    def __init__(self):
        self.rows = []
        self.previous = {}
        self.pending = {}
        self.recoveries = []
        self.initial_acquisitions = []
        self.seen_ever = set()
        self.last_visible = set()
        self.censored = 0

    def frame(
        self,
        sequence,
        index,
        timestamp,
        gt,
        predictions,
        local_ms,
        retrieval=None,
        session=0,
    ):
        if gt is None:
            return
        assigned = {}
        used = set()
        edges = sorted(
            [
                (iou(g["bbox"], p["bbox"]), j, k)
                for j, g in enumerate(gt)
                for k, p in enumerate(predictions)
            ],
            reverse=True,
        )
        for overlap, j, k in edges:
            if overlap >= 0.5 and j not in assigned and k not in used:
                assigned[j] = k
                used.add(k)
        visible = set()
        pairs = [
            (g, predictions[assigned[j]] if j in assigned else None)
            for j, g in enumerate(gt)
        ]
        pairs.extend(
            ({"object_id": None, "instance_id": None}, p)
            for k, p in enumerate(predictions)
            if k not in used
        )
        for g, pred in pairs:
            oid = (
                pred.get("object_id")
                if pred and pred["identity_state"] == "matched"
                else None
            )
            expected = g["object_id"]
            key = (sequence, session, g["instance_id"])
            correct = oid is not None and oid == expected
            switch = False
            if g["instance_id"] is not None:
                visible.add(key)
                switch = (
                    oid is not None
                    and key in self.previous
                    and self.previous[key] != oid
                )
                if oid is not None:
                    self.previous[key] = oid
                if expected is not None:
                    if key not in self.last_visible or not correct:
                        kind = "initial" if key not in self.seen_ever else "recovery"
                        self.pending.setdefault(key, (timestamp, kind))
                    if correct and key in self.pending:
                        start, kind = self.pending.pop(key)
                        destination = (
                            self.initial_acquisitions
                            if kind == "initial"
                            else self.recoveries
                        )
                        destination.append((timestamp - start) * 1000)
            self.seen_ever.add(key)
            r = (retrieval or {}).get(pred["track_id"]) if pred else None
            proposal = pred.get("vlm_proposal") if pred else None
            proposed = proposal["object_id"] if proposal else None
            self.rows.append(
                {
                    "sequence": sequence,
                    "frame_index": index,
                    "timestamp_s": timestamp,
                    "instance_id": g["instance_id"],
                    "expected_object_id": expected,
                    "object_id": oid,
                    "track_id": pred["track_id"] if pred else None,
                    "identity_state": pred["identity_state"] if pred else "unknown",
                    "correct": correct,
                    "incorrect": oid is not None and oid != expected,
                    "unknown": oid is None,
                    "correct_rejection": oid is None and expected is None,
                    "proposal_returned": proposal is not None,
                    "proposed_object_id": proposed,
                    "proposal_correct": proposed is not None and proposed == expected,
                    "proposal_incorrect": proposed is not None and proposed != expected,
                    "proposal_unknown": proposal is not None and proposed is None,
                    "identity_switch": bool(switch),
                    "detection_miss": pred is None,
                    "local_ms": local_ms,
                    "retrieval_success": r.get("success", False) if r else None,
                    "annotation_count": r.get("count") if r else None,
                    "retrieval_failure": r.get("failure") if r else None,
                }
            )
        for key in list(self.pending):
            if key not in visible:
                self.pending.pop(key)
                self.censored += 1
        self.last_visible = visible

    def summary(self, events, duration_s, frame_latencies, backend_enabled):
        r = self.rows
        n = len(r)
        known = sum(x["expected_object_id"] is not None for x in r)
        count = lambda k: sum(bool(x[k]) for x in r)
        failure = Counter(
            e["failure_category"] for e in events if e["failure_category"]
        )
        usage = Counter()
        for e in events:
            usage.update(e["usage"])
        costs = [
            e["estimated_cost_usd"]
            for e in events
            if e["estimated_cost_usd"] is not None
        ]
        return {
            "total_evaluated_observations": n,
            "known_object_observations": known,
            "correct_assignments": count("correct"),
            "incorrect_assignments": count("incorrect"),
            "unknown_observations": count("unknown"),
            "correct_rejections": count("correct_rejection"),
            "proposal_observations": count("proposal_returned"),
            "correct_proposals": count("proposal_correct"),
            "incorrect_proposals": count("proposal_incorrect"),
            "unknown_proposals": count("proposal_unknown"),
            "identity_switches": count("identity_switch"),
            "detector_misses": count("detection_miss"),
            "correct_identity_coverage": count("correct") / known if known else None,
            "wrong_identity_assignment_rate": count("incorrect") / n if n else None,
            "correct_retrieval_coverage": sum(
                x["correct"] and x["retrieval_success"] is True for x in r
            )
            / known
            if backend_enabled and known
            else None,
            "wrong_object_label_rate": sum(
                x["incorrect"]
                and x["retrieval_success"] is True
                and (x["annotation_count"] or 0) > 0
                for x in r
            )
            / n
            if backend_enabled and n
            else None,
            "initial_acquisition": latency(self.initial_acquisitions),
            "recovery": {
                **latency(self.recoveries),
                "unrecovered_or_censored": self.censored + len(self.pending),
            },
            "vlm_requests": len(events),
            "vlm_requests_per_minute": len(events) * 60 / duration_s
            if duration_s > 0
            else None,
            "vlm_latency": latency(
                [e["latency_ms"] for e in events if e["latency_ms"] is not None]
            ),
            "local_latency": latency(frame_latencies),
            "failures": dict(failure),
            "retrieval_failures": dict(
                Counter(x["retrieval_failure"] for x in r if x["retrieval_failure"])
            ),
            "token_usage": dict(usage) if usage else None,
            "estimated_cost_usd": sum(costs) if costs else None,
            "cost_metadata_complete": bool(events) and len(costs) == len(events),
            "observed_duration_s": duration_s,
        }


def write_results(out, result, rows, events):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    summaries = []
    for sequence in result["sequences"]:
        row = {"sequence": sequence["id"], "condition": sequence["condition"]}
        for key, value in sequence["metrics"].items():
            if isinstance(value, dict) and value:
                row.update(
                    {key + "." + subkey: subvalue for subkey, subvalue in value.items()}
                )
            else:
                row[key] = json.dumps(value) if isinstance(value, dict) else value
        summaries.append(row)
    with (out / "sequence-metrics.csv").open("w", newline="") as f:
        if summaries:
            fields = list(dict.fromkeys(key for row in summaries for key in row))
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(summaries)
    for name, values in [("observations", rows), ("vlm-events", events)]:
        (out / (name + ".jsonl")).write_text(
            "".join(json.dumps(r) + "\n" for r in values)
        )
    with (out / "observations.csv").open("w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def comparison(outputs, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    results = [json.loads((Path(p) / "summary.json").read_text()) for p in outputs]
    if len({r["dataset_sha256"] for r in results}) != 1:
        raise ValueError("Comparison requires the same dataset")
    rows = []
    for r in results:
        for s in r["sequences"]:
            rows.append(
                {
                    "configuration": r["mode"],
                    "sequence": s["id"],
                    "condition": s["condition"],
                    "observations": s["metrics"]["total_evaluated_observations"],
                    **{
                        k: s["metrics"][k]
                        for k in (
                            "correct_assignments",
                            "incorrect_assignments",
                            "unknown_observations",
                            "identity_switches",
                            "vlm_requests",
                            "correct_retrieval_coverage",
                            "wrong_object_label_rate",
                            "correct_proposals",
                            "incorrect_proposals",
                            "unknown_proposals",
                        )
                    },
                }
            )
    with (out / "comparison.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    labels = [r["configuration"] + " / " + r["sequence"] for r in rows]
    positions = np.arange(len(rows))
    fig, axes = plt.subplots(1, 2, figsize=(13, max(5, len(rows) * 0.35)), sharey=True)
    groups = [
        (
            "Accepted identities",
            ("correct_assignments", "incorrect_assignments", "unknown_observations"),
        ),
        (
            "VLM proposals (separate from acceptance)",
            ("correct_proposals", "incorrect_proposals", "unknown_proposals"),
        ),
    ]
    for axis, (title, keys) in zip(axes, groups):
        left = np.zeros(len(rows))
        for key, label, color in zip(
            keys,
            ("Correct", "Incorrect", "Unknown / abstained"),
            ("#21735d", "#b84139", "#d3d7db"),
        ):
            values = np.array([row[key] for row in rows])
            axis.barh(positions, values, left=left, label=label, color=color)
            left += values
        axis.set_title(title, loc="left", fontsize=11)
        axis.set_xlabel("Observation count")
        axis.set_xlim(0, max(row["observations"] for row in rows) + 2)
        axis.spines[["top", "right"]].set_visible(False)
        for y, total in zip(positions, left):
            axis.text(total + 0.15, y, str(int(total)), va="center", fontsize=8)
    axes[0].set_yticks(positions, labels, fontsize=8)
    axes[0].invert_yaxis()
    fig.legend(
        *axes[1].get_legend_handles_labels(),
        loc="upper right",
        ncols=3,
        frameon=False,
        fontsize=8,
    )
    fig.suptitle(
        results[0]["evidence_kind"] + " — identity comparison",
        x=0.02,
        ha="left",
        fontsize=13,
    )
    fig.text(
        0.02,
        0.01,
        "Correlated frame observations. Synthetic/mock runs test software, not laptop or VLM accuracy. Pending proposals are not accepted identities.",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(out / "comparison.svg")
    fig.savefig(out / "comparison.png", dpi=140)
    plt.close(fig)
