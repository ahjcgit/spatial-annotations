"""Score the recorded visual reads. Re-running this does not perform inference."""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rows(name):
    with (HERE / name).open(newline="") as f:
        rows_by_id = {}
        for row in csv.DictReader(f):
            if row["probe"] in rows_by_id:
                raise ValueError(f"Repeated probe in {name}: {row['probe']}")
            rows_by_id[row["probe"]] = row
        return rows_by_id


def evaluate(key, responses):
    if key.keys() != responses.keys():
        raise ValueError("Key and decisions must cover the same probes")
    totals = dict(target_correct=0, target_wrong=0, target_abstain=0,
                  distractor_rejected=0, distractor_falsely_labeled=0)
    for probe, row in key.items():
        truth = row["source_identity"]
        choice = responses[probe]["decision"]
        if truth not in {"A", "B", "none"} or choice not in {"A", "B", "unknown"}:
            raise ValueError(f"Unexpected label for {probe}")
        if truth == "none":
            metric = "distractor_rejected" if choice == "unknown" else "distractor_falsely_labeled"
        elif truth == choice:
            metric = "target_correct"
        else:
            metric = "target_abstain" if choice == "unknown" else "target_wrong"
        totals[metric] += 1
    return totals


if __name__ == "__main__":
    key = rows("key.csv")
    crop = rows("decisions.csv")
    context = rows("context-decisions.csv")
    result = {
        "distinct_test_photos": len({row["source"] for row in key.values()}),
        "probe_count": len(key),
        "crop_only": evaluate(key, crop),
        "current_scene": evaluate(key, context),
        "changed_choices": {p: [crop[p]["decision"], context[p]["decision"]]
                            for p in key if crop[p]["decision"] != context[p]["decision"]},
    }
    print(json.dumps(result, indent=2))
