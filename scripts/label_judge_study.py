#!/usr/bin/env python3
"""Run the opt-in offline VLM label-judge experiment. See docs/LABEL_JUDGE_RUN.md."""

import argparse
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from judge import data
from judge.collect import collect, calibrate
from judge.methods import ARMS, VARIANTS, detection_cache
from judge.run import run
from judge.score import analyze


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in (
        "init",
        "archive",
        "seal",
        "detect",
        "run",
        "score",
        "collect",
        "calibrate",
    ):
        s = sub.add_parser(name)
        s.add_argument("--study", type=Path, required=True)
        if name in ("run", "score", "detect", "calibrate"):
            s.add_argument("--out", type=Path, required=True)
        if name == "archive":
            s.add_argument("--link-reveal", action="store_true")
        if name == "init":
            s.add_argument(
                "--split", choices=["development", "evaluation"], default="evaluation"
            )
        if name == "collect":
            s.add_argument("--case", required=True)
            files = s.add_mutually_exclusive_group(required=True)
            files.add_argument("--image", type=Path)
            files.add_argument("--video", type=Path)
            s.add_argument("--at-ms", type=int)
            s.add_argument("--time-ms", type=int, required=True)
            s.add_argument("--deadline-ms", type=int)
            s.add_argument("--box", type=int, nargs=4, required=True)
            s.add_argument("--body", choices=["A", "B", "C", "none"], required=True)
            s.add_argument("--identifiable", choices=["yes", "no"], required=True)
            s.add_argument("--continuous", action="store_true")
            s.add_argument("--prior")
            s.add_argument("--second")
        if name == "detect":
            s.add_argument("--model", choices=["nanodet", "yolox_s"], default="nanodet")
            s.add_argument("--label", choices=["bottle", "laptop"], default="bottle")
        if name == "run":
            s.add_argument(
                "--provider",
                choices=["mock", "interactive", "frontier", "local-api"],
                required=True,
            )
            s.add_argument("--arms", choices=ARMS, nargs="+", default=list(ARMS))
            s.add_argument(
                "--variants", choices=VARIANTS, nargs="+", default=list(VARIANTS)
            )
            s.add_argument("--cases", nargs="+")
            s.add_argument("--repeats", type=int, default=1)
            s.add_argument("--seed", type=int, default=241130)
            s.add_argument("--max-calls", type=int, required=True)
            s.add_argument("--cache", type=Path)
            s.add_argument("--calibration", type=Path)
        if name == "score":
            s.add_argument("--run", type=Path, required=True)
            s.add_argument("--wearer", type=Path)
    a = p.parse_args()
    if a.cmd == "init":
        data.init(a.study, a.split)
    elif a.cmd == "collect":
        collect(a)
    elif a.cmd == "calibrate":
        calibrate(a.study, a.out)
    elif a.cmd == "archive":
        data.archive(a.study, a.link_reveal)
    elif a.cmd == "seal":
        data.seal(a.study)
    elif a.cmd == "detect":
        results = detection_cache(a.study, data.verified(a.study), a.model, a.label)
        with a.out.open("x") as f:
            import json

            json.dump(results, f, indent=2)
    elif a.cmd == "run":
        asyncio.run(run(a))
    else:
        analyze(a)


if __name__ == "__main__":
    main()
