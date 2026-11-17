"""Fixed study inputs, sequence-level recovery metrics, and report provenance."""

import hashlib
import json

from .dataset import Dataset
from .evaluation import latency
from .tracker import iou

CONDITIONS = {
    "C1": "Stationary laptops",
    "C2": "Camera viewpoint changes",
    "C3": "Observed crossing",
    "C4": "Temporary occlusion",
    "C5": "Leave and return, positions unchanged",
    "C6": "Unobserved position swap",
    "CX": "Insufficient distinguishing appearance",
}


def gallery_fingerprint(gallery):
    content = {
        oid: [r["sha256"] for r in obj["references"]]
        for oid, obj in gallery.objects.items()
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def inspect_dataset(path, pass_name, protocol):
    dataset = Dataset(path)
    if dataset.data.get("split") != "test":
        raise ValueError(
            "Study evaluation requires split=test (use separate development data)"
        )
    seen = set()
    for sequence in dataset.data["sequences"]:
        if sequence["condition"] not in CONDITIONS:
            raise ValueError("Study conditions must be C1..C6 or CX")
        recording = sequence.get("recording_id")
        if not recording or recording in seen:
            raise ValueError(
                "Each sequence needs a unique recording_id; do not split one recording into independent trials"
            )
        seen.add(recording)
        if dataset.data["evidence_kind"] == "real_recording" and not sequence.get(
            "ground_truth_verified"
        ):
            raise ValueError(
                "Manually verify ground truth before evaluating real recordings"
            )
        if protocol == "probes" and not any(
            f.get("reasoning_probe") for f in sequence["frames"]
        ):
            raise ValueError(
                "Freeze at least one reasoning_probe per sequence before evaluation"
            )
        for frame in sequence["frames"]:
            if frame.get("ground_truth") is None:
                raise ValueError(
                    "Study frames need verified ground_truth; null is unscored, not a negative example"
                )
            if pass_name == "A" and frame.get("ground_truth") is None:
                raise ValueError("Pass A needs manual boxes")
        for event in sequence.get("recovery_events", []):
            start, end = event["start_frame"], event["deadline_frame"]
            if event["kind"] not in (
                "occlusion",
                "return",
                "swap",
            ) or not 0 <= start <= end < len(sequence["frames"]):
                raise ValueError("Invalid recovery event interval")
            frame = sequence["frames"][start]
            if not any(
                g["instance_id"] == event["instance_id"] and g["object_id"]
                for g in frame["ground_truth"]
            ):
                raise ValueError("Recovery starts at a visible registered instance")
    return dataset


def recovery_metrics(sequence, rows):
    episodes = []
    for event in sequence.get("recovery_events", []):
        start = event["start_frame"]
        end = event["deadline_frame"]
        gt = next(
            g
            for g in sequence["frames"][start]["ground_truth"]
            if g["instance_id"] == event["instance_id"]
        )
        eligible = [
            r
            for r in rows
            if start <= r["frame_index"] <= end
            and r["instance_id"] == event["instance_id"]
        ]
        correct = next(
            (r for r in eligible if r["object_id"] == gt["object_id"] and r["correct"]),
            None,
        )
        episodes.append(
            {
                "kind": event["kind"],
                "instance_id": event["instance_id"],
                "start_frame": start,
                "deadline_frame": end,
                "recovered": correct is not None,
                "latency_ms": (
                    correct["timestamp_s"] - sequence["frames"][start]["timestamp_s"]
                )
                * 1000
                if correct
                else None,
            }
        )
    return {
        "episodes": episodes,
        **{
            kind: {
                "eligible": sum(e["kind"] == kind for e in episodes),
                "recovered": sum(
                    e["kind"] == kind and e["recovered"] for e in episodes
                ),
                "latency": latency(
                    [
                        e["latency_ms"]
                        for e in episodes
                        if e["kind"] == kind and e["recovered"]
                    ]
                ),
            }
            for kind in ("occlusion", "return", "swap")
        },
    }


def apply_initializations(pipeline, seeds, sequence, index):
    """Explicit operator evidence, never inferred from evaluation ground truth."""
    for seed in seeds:
        if seed["sequence"] != sequence or seed["frame_index"] != index:
            continue
        if seed.get("verification") != "operator_confirmed":
            raise ValueError("Initializations must be explicitly operator_confirmed")
        matches = [
            t
            for t in pipeline.tracker.tracks.values()
            if t.visible and iou(t.bbox, seed["bbox"]) >= 0.5
        ]
        if len(matches) == 1:
            t = matches[0]
            pipeline.confirm(t.track_id, t.generation, seed["object_id"], persist=False)


def flat_metrics(metrics):
    result = {}
    for key, value in metrics.items():
        if isinstance(value, dict):
            for sub, val in flat_metrics(value).items():
                result[key + "." + sub] = val
        else:
            result[key] = json.dumps(value) if isinstance(value, list) else value
    return result
