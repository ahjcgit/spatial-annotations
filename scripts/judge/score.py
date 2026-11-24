"""Join a sealed operator key only after inference. Score misses, abstentions and stale returns."""

import csv
import json
from collections import defaultdict, Counter
from statistics import median

from app.identity.evaluation import latency
from .data import fresh, number, read, save, sha, truth_key, verified
from .run import jobs


def classify(row, key):
    label = row["applied"]["alias"]
    eligible = key["body"] in ("A", "B") and key["identifiable"]
    right = eligible and label == key["body"]
    if label is None:
        outcome = "abstain" if eligible else "justified_withhold"
    elif label != key["body"]:
        outcome = "wrong_body"
    else:
        outcome = "correct" if right else "unsupported_show"
    hint = row["hint"]
    change = None
    if hint and not row.get("error"):
        proposed_label = (
            row["proposed"]["alias"]
            if row["proposed"]["action"] in ("show", "keep", "move")
            else None
        )
        if eligible and hint == key["body"]:
            change = (
                "correct_hint_accepted"
                if proposed_label == hint
                else (
                    "correct_hint_withheld"
                    if proposed_label is None
                    else "incorrect_override"
                )
            )
        elif row["proposed"]["alias"] == hint and row["proposed"]["action"] in (
            "show",
            "keep",
            "move",
        ):
            change = "unsafe_hint_endorsed"
        else:
            change = (
                "bad_hint_corrected"
                if eligible and proposed_label == key["body"]
                else "bad_hint_withheld"
                if proposed_label is None
                else "other_wrong"
            )
    return outcome, change


def wearer_rows(path, events):
    if not path:
        return {}
    with path.open(newline="") as f:
        values = list(csv.DictReader(f))
    result = {}
    for r in values:
        rid = r["request_id"]
        if (
            rid not in events
            or rid in result
            or r["selection"] not in ("A", "B", "C", "none", "unreadable")
        ):
            raise ValueError("Invalid or duplicate wearer row")
        committed = float(r["capture_to_commit_ms"])
        if (
            not number(committed)
            or committed < 0
            or r["displayed_alias"] not in ("A", "B", "none")
        ):
            raise ValueError("Invalid display observation")
        selection_ms = (
            float(r["capture_to_selection_ms"])
            if r.get("capture_to_selection_ms")
            else None
        )
        if selection_ms is not None and (
            not number(selection_ms) or selection_ms < committed
        ):
            raise ValueError("Wearer response cannot precede frame commit")
        result[rid] = (committed, selection_ms, r["selection"], r["displayed_alias"])
    return result


def analyze(args):
    data = verified(args.study)
    meta = read(args.run / "run.json")
    if meta["seal"] != read(args.study / "seal.json") or meta["seal"]["truth"] != sha(
        args.study / "truth.json"
    ):
        raise ValueError("Run or truth key does not match the seal")
    cases = {c["id"]: c for c in data["cases"]}
    key = truth_key(args.study, data["cases"])
    events = [
        json.loads(s) for s in (args.run / "events.jsonl").read_text().splitlines()
    ]
    planned = jobs(
        [cases[k] for k in meta["cases"]],
        meta["arms"],
        meta["variants"],
        meta["repeats"],
        meta["seed"],
    )
    if [(e["case"], e["arm"], e["variant"], e["repeat"]) for e in events] != [
        (c["id"], a, v, n) for c, a, v, n in planned
    ]:
        raise ValueError("Incomplete or changed schedule")
    all_events = [
        x
        for r in events
        for x in ([r, r["second_look"]] if "second_look" in r else [r])
    ]
    device = wearer_rows(args.wearer, {e["id"] for e in all_events})
    out = fresh(args.out)
    scored = []
    groups = defaultdict(list)

    def score(e, phase, parent):
        truth = key[e["case"]]
        deadline = cases[e["case"]]["deadline_ms"]
        outcome, change = classify(e, truth)
        physically_on_time = None
        if (
            e["id"] in device
            and deadline is not None
            and device[e["id"]][1] is not None
        ):
            commit, selection_ms, selection, shown = device[e["id"]]
            physically_on_time = (
                truth["identifiable"]
                and truth["body"] in ("A", "B")
                and shown == selection == truth["body"]
                and commit <= selection_ms < deadline
            )
        record = {
            "request_id": e["id"],
            "parent": parent,
            "phase": phase,
            "case": e["case"],
            "take": e["take"],
            "condition": truth["condition"],
            "repeat": e["repeat"],
            "arm": e["arm"],
            "variant": e["variant"],
            "truth": truth["body"],
            "identifiable": truth["identifiable"],
            "candidate": e["candidate"],
            "hint": e["hint"],
            "proposed": e["proposed"]["alias"],
            "action": e["applied"]["action"],
            "label": e["applied"]["alias"],
            "outcome": outcome,
            "hint_result": change,
            "cue": e["proposed"].get("cue"),
            "error": e["error"],
            "late": e["applied"]["status"] == "late",
            "elapsed_ms": e["elapsed_ms"],
            "cpu_ms": e["cpu_ms"],
            "rss_mib": e["memory_mib"]["VmRSS"],
            "input_bytes": e["input_bytes"],
            "calls": e["calls"],
            "usage_tokens": e["usage"].get("total_tokens"),
            "cost_usd": e["cost_usd"],
            "offline_correct_by_deadline": outcome == "correct"
            if deadline is not None
            else None,
            "observed_wearer_correct_on_time": physically_on_time,
            "from_original_ms": e.get("from_original_ms"),
        }
        scored.append(record)
        groups[e["arm"], e["variant"], phase].append(record)

    for r in events:
        score(r, "initial", None)
        if "second_look" in r:
            score(r["second_look"], "second", r["id"])

    def writecsv(name, records):
        with (out / name).open("w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=records[0].keys(), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(records)

    writecsv("decisions.csv", scored)
    aggregates = []
    stratified = []

    def counts(items):
        outcomes = Counter(r["outcome"] for r in items)
        return {
            "n": len(items),
            **{
                k: outcomes[k]
                for k in (
                    "correct",
                    "wrong_body",
                    "unsupported_show",
                    "abstain",
                    "justified_withhold",
                )
            },
            "late": sum(r["late"] for r in items),
            "failures": sum(bool(r["error"]) for r in items),
            "calls": sum(r["calls"] for r in items),
        }

    for (arm, v, phase), items in groups.items():
        eligible = [r for r in items if r["identifiable"] and r["truth"] in ("A", "B")]
        negative = [r for r in items if r["truth"] in ("none", "C")]
        row = {
            "eligible_targets": len(eligible),
            "decoy_or_empty": len(negative),
            "false_labels_on_decoy_or_empty": sum(
                r["label"] is not None for r in negative
            ),
            "raw_candidate_correct_on_eligible": sum(
                r["candidate"] == r["truth"] for r in eligible
            ),
            "arm": arm,
            "variant": v,
            "phase": phase,
            **counts(items),
            "hint_outcomes": dict(
                Counter(r["hint_result"] for r in items if r["hint_result"])
            ),
            "latency": latency([r["elapsed_ms"] for r in items]),
            "median_cpu_ms": median(r["cpu_ms"] for r in items),
            "max_sampled_rss_mib": max(r["rss_mib"] for r in items),
            "total_input_bytes": sum(r["input_bytes"] for r in items),
        }
        for metric in ("usage_tokens", "cost_usd"):
            called = [r for r in items if r["calls"]]
            row[metric] = (
                sum(r[metric] for r in called)
                if called and all(r[metric] is not None for r in called)
                else None
            )
        for metric in (
            "offline_correct_by_deadline",
            "observed_wearer_correct_on_time",
        ):
            available = [r[metric] for r in items if r[metric] is not None]
            row[metric] = (
                {"measured": len(available), "correct": sum(available)}
                if available
                else None
            )
        aggregates.append(row)
        for dimension in ("take", "condition"):
            for value in sorted({r[dimension] for r in items}):
                stratified.append(
                    {
                        "arm": arm,
                        "variant": v,
                        "phase": phase,
                        "group": dimension,
                        "value": value,
                        **counts([r for r in items if r[dimension] == value]),
                    }
                )
    writecsv("by-take-and-condition.csv", stratified)
    save(
        out / "summary.json",
        {"provider": meta["provider"], "pass": meta["pass"], "groups": aggregates},
    )
    lines = [
        "# Label judge results",
        "",
        f"Provider: {meta['provider']}. Boxes: {meta['pass']}. "
        f"{len(events)} initial judgments. Takes represented: {len(set(r['take'] for r in events))}. "
        "A follow-up view is scored against its own target and timestamp.",
        "",
        "| Arm / suggestion / view | Opportunities | Correct shows | Wrong body | Unsupported shows | Abstain | Justified withhold | Calls | Median ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in aggregates:
        lines.append(
            f"| {r['arm']} / {r['variant']} / {r['phase']} | {r['n']} | {r['correct']} | {r['wrong_body']} | "
            f"{r['unsupported_show']} | {r['abstain']} | {r['justified_withhold']} | {r['calls']} | {r['latency']['median_ms']:.2f} |"
        )
    lines += [
        "",
        "Inspect [each cue and action](decisions.csv), [per-take and per-condition counts](by-take-and-condition.csv), "
        "and [cost, latency and suggestion acceptance](summary.json).",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")
