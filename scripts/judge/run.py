"""Execute fixed, randomized study requests. Evaluation truth is loaded only by scoring."""

import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import time
from collections import deque
from datetime import datetime, timezone
from uuid import uuid4

from app.identity.appearance import Calibration, ColorGrid
from app.identity.config import Config
from app.identity.providers import provider_config
from app.identity.vlm import ProviderFailure
from .data import fresh, read, save, sha, verified
from .methods import Inputs, JudgeAPI, PROMPT, validate


def resident():
    with open("/proc/self/status") as f:
        return {
            k: int(v.split()[0]) / 1024
            for k, v in (
                s.split(":", 1) for s in f if s.startswith(("VmRSS:", "VmHWM:"))
            )
        }


def jobs(cases, arms, variants, repeats, seed):
    tasks = [
        (c, arm, v, n)
        for n in range(1, repeats + 1)
        for c in cases
        for arm in arms
        for v in (
            variants
            if arm in ("review", "temporal", "duplicate", "stale", "gap")
            else ["genuine"]
        )
    ]
    random.Random(seed).shuffle(tasks)
    return tasks


def apply(decision, elapsed, deadline):
    if deadline is not None and elapsed >= deadline:
        return {"action": "clear", "alias": None, "status": "late"}
    action = decision["action"]
    return {
        "action": action,
        "alias": decision["alias"] if action in ("show", "keep", "move") else None,
        "status": "ready",
    }


class Review:
    def __init__(self, args, cfg):
        self.kind, self.limit, self.out = args.provider, args.max_calls, args.out
        self.calls = 0
        self.cfg = cfg
        self.queue = deque()
        self.adapter = JudgeAPI(cfg) if self.kind in ("local-api", "frontier") else None

    async def respond(self, request, rid):
        if self.calls >= self.limit:
            raise ProviderFailure("call_budget")
        if self.adapter:
            now = time.monotonic()
            while self.queue and now - self.queue[0] >= 60:
                self.queue.popleft()
            if len(self.queue) >= self.cfg.requests_per_minute:
                await asyncio.sleep(max(0, 60 - (now - self.queue[0])))
                self.queue.popleft()
            self.queue.append(time.monotonic())
        self.calls += 1
        if self.kind == "interactive":
            card = self.out / (rid + ".jpg")
            card.write_bytes(request["jpeg"])
            print(
                json.dumps(
                    {
                        "id": rid,
                        "card": str(card.resolve()),
                        "prompt": request["prompt"],
                    }
                ),
                flush=True,
            )
            line = input()
            return {"response": line, "usage": {}}
        if self.kind == "mock":
            return {
                "response": {
                    "request_id": rid,
                    "alias": None,
                    "support": "none",
                    "action": "request_view",
                    "cue": "Synthetic interface check.",
                    "source": "current",
                },
                "usage": {},
            }
        return await asyncio.wait_for(
            self.adapter.match(request), timeout=self.cfg.timeout_s
        )


async def run(args):
    data = verified(args.study)
    if not 1 <= args.repeats <= 3 or args.max_calls < 0:
        raise ValueError("Use 1–3 repeats and a nonnegative call cap")
    cfg = Config.from_env()
    if args.provider in ("frontier", "local-api"):
        cfg = provider_config(
            "frontier" if args.provider == "frontier" else "local", cfg
        )
        if cfg is None or not cfg.vlm_enabled or args.max_calls == 0:
            raise ValueError(
                "Explicitly enable the provider and set a positive --max-calls"
            )
    cache = read(args.cache) if args.cache else None
    seal = read(args.study / "seal.json")
    if cache and cache["seal"] != seal["observations"]:
        raise ValueError("Detector cache belongs to different inputs")
    calibration = None
    if args.calibration:
        meta = read(args.calibration)
        hashes = {sha(args.study / c["image"]) for c in data["cases"]}
        development = set(meta["development_image_sha256"])
        if meta["synthetic_only"] or not development or hashes & development:
            raise ValueError("Require independent real development calibration")
        if meta.get("gallery_hashes") and meta["gallery_hashes"] != {
            a: [sha(args.study / f) for f in files]
            for a, files in data["references"].items()
        }:
            raise ValueError("Development gallery differs from evaluation gallery")
        calibration = Calibration(meta, ColorGrid.name)
    inputs = Inputs(args.study, data, cfg, calibration, cache)
    cases = [c for c in data["cases"] if not args.cases or c["id"] in args.cases]
    if not cases or (args.cases and set(args.cases) != {c["id"] for c in cases}):
        raise ValueError("Unknown or empty case selection")
    tasks = jobs(cases, args.arms, args.variants, args.repeats, args.seed)
    fresh(args.out)
    reviewer = Review(args, cfg)
    save(
        args.out / "run.json",
        {
            "seal": seal,
            "provider": args.provider,
            "config": cfg.public(),
            "model": cfg.model
            if args.provider in ("frontier", "local-api")
            else args.provider,
            "max_calls": args.max_calls,
            "seed": args.seed,
            "repeats": args.repeats,
            "arms": args.arms,
            "variants": args.variants,
            "cases": [c["id"] for c in cases],
            "planned": len(tasks),
            "pass": "detector" if cache else "manual",
            "cache_sha256": sha(args.cache) if cache else None,
            "calibration_sha256": sha(args.calibration) if args.calibration else None,
            "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
            "platform": platform.platform(),
            "versions": {
                p: importlib.metadata.version(p) for p in ("pillow", "numpy", "httpx")
            },
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        },
    )

    async def decide(c, arm, variant, sequence):
        local = inputs.local[c["id"]]
        rid = uuid4().hex
        cpu = time.process_time_ns()
        start = time.monotonic_ns()
        row = {
            "id": rid,
            "case": c["id"],
            "take": c["take"],
            "arm": arm,
            "variant": variant,
            "repeat": sequence,
            "candidate": local["candidate"],
            "accepted_local": local["accepted"],
            "track": local["track"],
            "hint": None,
            "raw": None,
            "calls": 0,
            "usage": {},
            "cost_usd": None,
            "error": None,
            "input_bytes": 0,
            "request_ms": None,
            "detector_ms": local["detector_ms"],
            "local_ms": local["local_ms"],
        }
        if (
            not local["box"]
            or arm == "local"
            or (arm == "adaptive" and local["routine"])
        ):
            alias = local["accepted"]
            decision = {"alias": alias, "action": "show" if alias else "verify"}
            if not local["box"]:
                row["error"] = "detector_miss"
                decision["action"] = "clear"
        else:
            request = inputs.render(c, arm, variant, rid, cfg.max_image_dimension)
            row.update(
                hint=request["hint"],
                input_bytes=len(request["jpeg"]),
                image_sha256=hashlib.sha256(request["jpeg"]).hexdigest(),
            )
            sent = time.monotonic_ns()
            initial = reviewer.calls
            try:
                answer = await reviewer.respond(request, rid)
                row.update(raw=answer["response"], usage=answer["usage"])
                u = row["usage"]
                if (
                    "prompt_tokens" in u
                    and "completion_tokens" in u
                    and cfg.input_usd_per_million is not None
                    and cfg.output_usd_per_million is not None
                ):
                    row["cost_usd"] = (
                        u["prompt_tokens"] * cfg.input_usd_per_million
                        + u["completion_tokens"] * cfg.output_usd_per_million
                    ) / 1e6
                decision = validate(
                    row["raw"], rid, request["has_prior"], request["continuity"]
                )
            except (ValueError, TypeError, ProviderFailure, TimeoutError) as exc:
                row["error"] = (
                    str(exc) if isinstance(exc, ProviderFailure) else type(exc).__name__
                )
                decision = {"alias": None, "action": "verify"}
            row.update(
                request_ms=(time.monotonic_ns() - sent) / 1e6,
                calls=reviewer.calls - initial,
            )
        elapsed = (
            (time.monotonic_ns() - start) / 1e6
            + local["local_ms"]
            + local["detector_ms"]
        )
        row.update(
            proposed=decision,
            applied=apply(decision, elapsed, c["deadline_ms"]),
            elapsed_ms=elapsed,
            cpu_ms=(time.process_time_ns() - cpu) / 1e6 + local["local_cpu_ms"],
            memory_mib=resident(),
        )
        return row

    with (args.out / "events.jsonl").open("x") as f:
        for c, arm, variant, sequence in tasks:
            row = await decide(c, arm, variant, sequence)
            if c.get("second") and (
                arm == "fixed-look"
                or (arm == "adaptive" and row["applied"]["action"] == "request_view")
            ):
                follow = inputs.cases[c["second"]]
                extra = await decide(follow, arm, "genuine", sequence)
                extra["from_original_ms"] = (
                    max(row["elapsed_ms"], follow["time_ms"] - c["time_ms"])
                    + extra["elapsed_ms"]
                )
                if follow["deadline_ms"] is not None:
                    remaining_age = extra["from_original_ms"] - (
                        follow["time_ms"] - c["time_ms"]
                    )
                    extra["applied"] = apply(
                        extra["proposed"], remaining_age, follow["deadline_ms"]
                    )
                row["second_look"] = extra
            f.write(json.dumps(row, allow_nan=False) + "\n")
            f.flush()
    print(f"{len(tasks)} decisions, {reviewer.calls} reviewer calls, {args.out}")
