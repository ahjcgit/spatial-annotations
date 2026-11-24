"""Rebuild the readable log and statistics and verify each measured image and time boundary."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory

from replay import DATA, GALLERY, HERE, card, digest, policy, schedule


def archive_actions(frame):
    proposal = frame.parent / "codex-proposal.json"
    if proposal.exists():
        labels = json.loads(proposal.read_text())["labels"]
    else:
        labels = json.loads((frame.parent / "codex-result.json").read_text())["result"]["objects"]
    actions = {a: {"action": "CLEAR", "side": "none"} for a in ("A", "B")}
    ordered = sorted(labels, key=lambda x: x["box"][0] + x["box"][2])
    if len(ordered) not in (0, 2):
        raise ValueError("Single-object left/right needs a reviewed reference")
    for side, item in zip(("left", "right"), ordered):
        alias = item["identity"] if "identity" in item else item["label"][0]
        actions[alias] = {"action": "VERIFY" if item["uncertain"] else "SHOW", "side": side}
    return actions


def stats(values):
    return dict(n=len(values), median=median(values), min=min(values), max=max(values))


def report(run, out):
    env = json.loads((run / "environment.json").read_text())
    if env["protocol_sha256"] != digest((HERE / "protocol.md").read_bytes()) or env["gallery_sha256"] != digest(GALLERY.read_bytes()):
        raise ValueError("Gallery or decision protocol changed")
    rows = list(map(json.loads, (run / "events.jsonl").read_text().splitlines()))
    pairs = {}
    logs = ["# Trial-by-trial decision log", "",
            "Each trial contains two proposed identities. The action names describe what the offline policy would display. Side is relative to the bottle pair. Times cover the entire scene decision.", ""]
    agreement = Counter()
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "card.jpg"
        for i, ((frame, previous, mode), row) in enumerate(zip(schedule(), rows, strict=True), 1):
            name = str(frame.parent.relative_to(DATA))
            prior = str(previous.parent.relative_to(DATA)) if previous else None
            card(frame, previous, path)
            payload = path.read_bytes()
            if (row["trial"], row["frame"], row["previous"], row["mode"], row["card_sha256"], row["bytes"]) != (i, name, prior, mode, digest(payload), len(payload)):
                raise ValueError(f"Input verification failed on trial {i}")
            for col, end, start in [("total_ms","end_ns","start_ns"), ("review_ms","received_ns","ready_ns"),
                                    ("prep_ms","ready_ns","start_ns"), ("policy_ms","end_ns","received_ns")]:
                actual = (row[end]-row[start])/1e6
                if actual < 0 or not math.isclose(row[col], actual):
                    raise ValueError(f"Invalid boundary {col} on trial {i}")
            source = f"../../codex-glasses/2026-11-19/{name}/source.jpg"
            logs.extend([f"### {i:02d} · {name} · {mode}", "", f"[Current photograph]({source})" +
                         (f" · [Earlier photograph](../../codex-glasses/2026-11-19/{prior}/source.jpg)" if prior else ""), ""])
            if row["status"] != "ok":
                logs.extend([f"Failed — {row['error']}", ""])
                continue
            actions = row["actions"]
            if actions != policy(row["proposals"]):
                raise ValueError(f"Policy mismatch on trial {i}")
            if mode != "start":
                pairs.setdefault(name, {})[mode] = row
            expected = archive_actions(frame)
            for alias, (support, side, cue) in row["proposals"].items():
                if actions[alias] == expected[alias]:
                    agreement[mode] += 1
                logs.append(f"- **{alias} · {actions[alias]['action']}** ({side}, {support}). {cue}")
            logs.extend(["", row["context"], "",
                         f"Total {row['total_ms']/1000:.2f} s · review {row['review_ms']/1000:.2f} s · preparation {row['prep_ms']:.2f} ms · local CPU {row['cpu_ms']:.2f} ms · resident memory {row['rss_after_mib']:.2f} MiB · JPEG {row['bytes']/1024:.1f} KiB.", ""])
    summary = {"attempts": len(rows), "failed": sum(r["status"] != "ok" for r in rows), "modes": {}}
    for mode in ("start", "current", "history"):
        group = [r for r in rows if r["mode"] == mode and r["status"] == "ok"]
        if group:
            summary["modes"][mode] = {"trials": len(group), "agreement_with_archived_calls": agreement[mode],
                "actions": dict(Counter(a["action"] for r in group for a in r["actions"].values())),
                **{k:stats([r[k] for r in group]) for k in ("total_ms","prep_ms","review_ms","policy_ms","cpu_ms","rss_after_mib","bytes")}}
    comparable = [p for p in pairs.values() if "current" in p and "history" in p]
    summary["paired_frames"] = len(comparable)
    summary["changed_frames"] = sum(p["current"]["actions"] != p["history"]["actions"] for p in comparable)
    if comparable:
        summary["paired_added_ms"] = stats([p["history"]["total_ms"]-p["current"]["total_ms"] for p in comparable])
    summary["worker_process_max_hwm_mib"] = max(r["process_hwm_mib"] for r in rows)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "decision-log.md").write_text("\n".join(logs).rstrip() + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=HERE)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report(args.run, args.out)
