#!/usr/bin/env python3
"""H0-H4 recorded-frame experiments; reuses the opt-in identity pipeline."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import resource
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.identity.annotations import AnnotationClient
from app.identity.appearance import Calibration, GeometryDescriptor
from app.identity.config import Config
from app.identity.controller import IdentityPipeline
from app.identity.evaluation import Metrics, latency, write_results
from app.identity.gallery import Gallery, save_json
from app.identity.providers import ProviderHub, configured_providers
from app.identity.study import (
    CONDITIONS,
    apply_initializations,
    gallery_fingerprint,
    inspect_dataset,
    recovery_metrics,
)
from app.identity.vlm import MockVLM
from identity_experiment import A, B, encoder, fresh, mock_adapter, register
from PIL import Image

METHODS = ["H0", "H1", "H2", "H3", "H4"]


def fixture(args):
    out = fresh(args.out)
    for oid, color in [(A, "red"), (B, "blue")]:
        path = out / (color + ".png")
        Image.new("RGB", (40, 30), color).save(path)
        register(
            out / "gallery.json", {"id": oid, "name": "Synthetic " + color}, [path]
        )
    sequences = []
    seeds = []
    for condition in CONDITIONS:
        frames = []
        for i in range(8):
            boxes = [[12, 24, 52, 54], [108, 24, 148, 54]]
            entries = [(A, "red", boxes[0]), (B, "blue", boxes[1])]
            if condition == "C2":
                entries = [
                    (oid, color, [b[0] + i, b[1] - i, b[2] + i, b[3] + i])
                    for oid, color, b in entries
                ]
            if condition == "C3":
                entries = [
                    (A, "red", [12 + 14 * i, 24, 52 + 14 * i, 54]),
                    (B, "blue", [108 - 14 * i, 24, 148 - 14 * i, 54]),
                ]
            if condition == "C4" and i in (2, 3, 4):
                entries = entries[:1]
            if condition in ("C5", "C6") and i in (2, 3):
                entries = []
            if condition == "C6" and i >= 4:
                entries = [(B, "blue", boxes[0]), (A, "red", boxes[1])]
            if condition == "CX":
                entries = [(oid, "gray", box) for oid, _, box in entries]
            image = Image.new("RGB", (172, 90), "#202020")
            for _, color, box in entries:
                image.paste(color, box)
            name = f"frames/{condition}/{i:04d}.png"
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            image.save(out / name)
            frames.append(
                {
                    "image": name,
                    "timestamp_s": i * 0.5,
                    "reasoning_probe": i in (1, 5),
                    "reset_session": condition in ("C5", "C6") and i == 4,
                    "ground_truth": [
                        {"instance_id": oid, "object_id": oid, "bbox": box}
                        for oid, _, box in entries
                    ],
                }
            )
        seq = {
            "id": condition + "-fixture",
            "recording_id": condition + "-generated-fixture",
            "condition": condition,
            "ground_truth_verified": False,
            "frames": frames,
            "recovery_events": [],
        }
        if condition in ("C4", "C5", "C6"):
            for oid in [B] if condition == "C4" else [A, B]:
                seq["recovery_events"].append(
                    {
                        "kind": {"C4": "occlusion", "C5": "return", "C6": "swap"}[
                            condition
                        ],
                        "instance_id": oid,
                        "start_frame": 5 if condition == "C4" else 4,
                        "deadline_frame": 7,
                    }
                )
        sequences.append(seq)
        if condition != "CX":
            for gt in frames[0]["ground_truth"]:
                seeds.append(
                    {
                        "sequence": seq["id"],
                        "frame_index": 0,
                        "bbox": gt["bbox"],
                        "object_id": gt["object_id"],
                        "verification": "operator_confirmed",
                    }
                )
    save_json(
        out / "dataset.json",
        {
            "version": 1,
            "protocol_version": 2,
            "split": "test",
            "evidence_kind": "deterministic_fixture",
            "description": "Generated colored rectangles. No real laptop or model accuracy evidence.",
            "sequences": sequences,
        },
    )
    save_json(out / "initializations.json", seeds)
    save_json(
        out / "calibration.json",
        {
            "embedding_model": "color-grid-v1",
            "development_set": "synthetic software fixture only",
            "synthetic_only": True,
            "appearance_min": 0.98,
            "appearance_margin": 0.1,
            "vlm_min": 0.9,
            "vlm_margin": 0.05,
            "vlm_development_set": "synthetic software fixture only",
        },
    )
    print("Synthetic study fixture:", out)


def plan(args):
    out = fresh(args.out)
    rows = []
    for condition, label in CONDITIONS.items():
        for n in range(1, 6):
            rows.append(
                {
                    "recording_id": f"{condition}-{n:02d}",
                    "condition": condition,
                    "description": label,
                    "status": "not_recorded",
                    "split": "test",
                    "independent_recording": True,
                }
            )
    save_json(
        out / "collection-plan.json",
        {
            "version": 1,
            "reference_session": "separate from development and test recordings",
            "development_session": "collect independently; do not tune on test recordings",
            "recordings": rows,
        },
    )
    print("35 planned recordings (30 required + 5 ambiguous); none collected:", out)


def prepare(dataset_path, pass_name, detector_name, out):
    data = inspect_dataset(dataset_path, pass_name, "events")
    cache = []
    detector = None
    if pass_name == "B":
        from eval_models import EvaluationModel

        detector = EvaluationModel(detector_name)
    for s in data.data["sequences"]:
        for i, f in enumerate(s["frames"]):
            image = data.image(f)
            gt = data.validate_gt(f, image)
            if detector:
                raw = io.BytesIO()
                image.save(raw, format="PNG")
                response = detector.infer(raw.getvalue())
                boxes = [
                    [d["box"][j] * image.size[j % 2] for j in range(4)]
                    for d in response["detections"]
                    if d["label"] == "laptop"
                ]
                ms = response["total_ms"]
            else:
                boxes = [g["bbox"] for g in gt]
                ms = None
            cache.append(
                {
                    "sequence": s["id"],
                    "frame_index": i,
                    "boxes": boxes,
                    "detector_ms": ms,
                }
            )
    result = {
        "dataset_sha256": data.fingerprint(),
        "pass": pass_name,
        "detector": detector.metadata
        if detector
        else {"name": "verified_ground_truth_boxes"},
        "frames": cache,
    }
    save_json(out, result)
    return result


def providers_for(args, common, gallery):
    if args.method in ("H0", "H1"):
        return [], []
    if not args.mock:
        providers = configured_providers(args.method, common)
        return providers, [
            {"name": n, "config": c.public(), "kind": "configured_endpoint"}
            for n, _, c in providers
        ]
    # Explicit test doubles only; H4 local abstention exercises frontier escalation.
    c = replace(
        common,
        vlm_enabled=True,
        endpoint="http://mock.invalid/v1",
        model="deterministic-mock",
    )
    local = MockVLM(delay=0.004) if args.method == "H4" else mock_adapter(gallery)
    candidates = {
        "H2": [("local", local, c)],
        "H3": [("frontier", mock_adapter(gallery), c)],
        "H4": [("local", local, c), ("frontier", mock_adapter(gallery), c)],
    }[args.method]
    return candidates, [
        {"name": n, "config": cfg.public(), "kind": "deterministic_mock"}
        for n, _, cfg in candidates
    ]


async def run(args):
    source_hash = hashlib.sha256()
    for source in sorted((ROOT / "backend/app/identity").glob("*.py")) + [
        Path(__file__),
        ROOT / "scripts/identity_experiment.py",
    ]:
        source_hash.update(source.read_bytes())
    common = Config.from_env()
    if not common.enabled:
        raise ValueError("Set IDENTITY_EXPERIMENT_ENABLED=true")
    if args.pace < 0 or not __import__("math").isfinite(args.pace):
        raise ValueError("Invalid replay pace")
    data = inspect_dataset(args.dataset, args.pass_name, args.protocol)
    fingerprint = data.fingerprint()
    if args.mock and data.data["evidence_kind"] != "deterministic_fixture":
        raise ValueError("Mock runs require explicitly synthetic fixtures")
    gallery = Gallery(
        args.gallery, GeometryDescriptor() if args.method == "H0" else encoder(args)
    )
    if args.method != "H0":
        gallery.cache_embeddings()
    calibration = (
        Calibration.load(args.calibration, gallery.encoder.name)
        if args.calibration and args.method != "H0"
        else None
    )
    if calibration:
        if calibration.data.get("development_sha256") == fingerprint:
            raise ValueError("Development/test leakage: use held-out sequences")
        if (
            calibration.data.get("synthetic_only")
            and data.data["evidence_kind"] != "deterministic_fixture"
        ):
            raise ValueError("Synthetic gates cannot evaluate real recordings")
    if calibration and calibration.data.get("development_image_sha256"):
        development_images = set(calibration.data["development_image_sha256"])
        if any(
            hashlib.sha256((data.root / f["image"]).read_bytes()).hexdigest()
            in development_images
            for seq in data.data["sequences"]
            for f in seq["frames"]
        ):
            raise ValueError("Development/test image overlap: use held-out recordings")
    cache = json.loads(Path(args.detections).read_text())
    if cache["dataset_sha256"] != fingerprint or cache["pass"] != args.pass_name:
        raise ValueError("Detection cache does not match study inputs")
    detection_map = {(r["sequence"], r["frame_index"]): r for r in cache["frames"]}
    seeds = (
        json.loads(Path(args.initializations).read_text())
        if args.initializations
        else []
    )
    candidates, provider_metadata = providers_for(args, common, gallery)
    config = replace(
        common,
        vlm_enabled=bool(candidates),
        endpoint=candidates[0][2].endpoint if candidates else "",
        model="provider-hub" if candidates else "",
        timeout_s=sum(c.timeout_s for _, _, c in candidates) + 1
        if candidates
        else common.timeout_s,
        acceptance="manual" if args.method in ("H0", "H1") else common.acceptance,
    )
    hub = (
        ProviderHub(candidates, config, escalate=args.method == "H4")
        if candidates
        else None
    )
    mode = (
        "heuristic"
        if args.method == "H0"
        else "baseline"
        if args.method == "H1"
        else "vlm"
        if args.protocol == "probes"
        else "hybrid"
    )
    p = IdentityPipeline(gallery, config, calibration, hub, mode=mode)
    # Same geometric tracker in every ablation; only recognition varies.
    p.tracker.geometry_only = True
    if hub:
        hub.current = p._current

        def supported(request, matches):
            return bool(calibration) and all(
                m["object_id"] is not None
                and calibration.accept(
                    p.tracker.tracks[m["track_id"]].scores, m["object_id"], vlm=True
                )
                for m in matches
            )

        hub.supported = supported
    api = AnnotationClient(args.backend, p) if args.backend else None
    if api:
        token = os.getenv("IDENTITY_API_TOKEN")
        if not token:
            raise ValueError("IDENTITY_API_TOKEN is required for annotation retrieval")
        api.set_token(token)
    out = fresh(args.out)
    all_rows = []
    frame_rows = []
    summaries = []
    started = time.perf_counter()
    cpu_start = time.process_time()
    for sequence in data.data["sequences"]:
        await p.close()
        seq_start = time.perf_counter()
        session = 0
        metrics = Metrics()
        local = []
        label_times = []
        cpu = []
        event_start = len(hub.events) if hub else 0
        detector_times = []
        processing = []
        for index, frame in enumerate(sequence["frames"]):
            target = (
                seq_start
                + (frame["timestamp_s"] - sequence["frames"][0]["timestamp_s"])
                * args.pace
            )
            await asyncio.sleep(max(0, target - time.perf_counter()))
            if hub:
                for event in hub.events[event_start:]:
                    event.setdefault("available_from_frame", index)
            frame_start = time.perf_counter()
            frame_cpu = time.process_time()
            if frame.get("reset_session"):
                await p.close()
                session += 1
            image = data.image(frame)
            gt = data.validate_gt(frame, image)
            cached = detection_map[(sequence["id"], index)]
            if cached["detector_ms"] is not None:
                detector_times.append(cached["detector_ms"])
            selected = args.protocol == "events" or frame.get("reasoning_probe", False)
            if args.protocol == "probes":
                await p.close()
            if selected:
                await p.step(image, cached["boxes"], frame["timestamp_s"])
                local.append(p.last_local_ms)
                if args.protocol == "probes":
                    await p.settle()
                    if hub:
                        for event in hub.events[event_start:]:
                            event.setdefault("available_from_frame", index)
                apply_initializations(p, seeds, sequence["id"], index)
                rows = p.snapshot()
            else:
                rows = []
            retrieved = {}
            if api:

                async def lookup(row):
                    if row["identity_state"] != "matched":
                        return
                    try:
                        notes = await api.retrieve(row)
                        retrieved[row["track_id"]] = {
                            "success": True,
                            "count": len(notes),
                            "failure": None,
                        }
                    except Exception as exc:
                        retrieved[row["track_id"]] = {
                            "success": False,
                            "count": 0,
                            "failure": type(exc).__name__,
                        }

                await asyncio.gather(*(lookup(row) for row in rows))
                current = {r["track_id"]: r for r in p.snapshot()}
                for row in rows:
                    if (
                        row["object_id"]
                        and current.get(row["track_id"], {}).get("object_id")
                        != row["object_id"]
                    ):
                        row.update(
                            object_id=None,
                            identity_state="unknown",
                            match_source=None,
                            match_score=None,
                        )
            elapsed = (time.perf_counter() - frame_start) * 1000
            processing.append(elapsed)
            cpu.append((time.process_time() - frame_cpu) * 1000)
            if any(r["object_id"] for r in rows):
                label_times.append(elapsed)
            metrics.frame(
                sequence["id"],
                index,
                frame["timestamp_s"],
                gt if selected else None,
                rows,
                p.last_local_ms if selected else None,
                retrieved,
                session,
            )
            safe = []
            for row in rows:
                proposal = row.get("vlm_proposal")
                row = {k: v for k, v in row.items() if k != "vlm_proposal"}
                row["proposed_object_id"] = proposal["object_id"] if proposal else None
                oid = row["object_id"]
                result = retrieved.get(row["track_id"])
                row["object_name"] = gallery.objects[oid]["name"] if oid else None
                row["annotation_label"] = (
                    (str(result["count"]) + " authorized notes")
                    if result and result["success"]
                    else ("Lookup failed" if result else None)
                )
                safe.append(row)
            frame_rows.append(
                {
                    "sequence": sequence["id"],
                    "frame_index": index,
                    "timestamp_s": frame["timestamp_s"],
                    "selected": selected,
                    "predictions": safe,
                    "replay_processing_ms": elapsed,
                    "cpu_processing_ms": cpu[-1],
                }
            )
        await p.close()
        provider_events = hub.events[event_start:] if hub else []
        for e in provider_events:
            e["sequence"] = sequence["id"]
            e.setdefault("available_from_frame", len(sequence["frames"]) - 1)
        duration = (
            sequence["frames"][-1]["timestamp_s"] - sequence["frames"][0]["timestamp_s"]
        )
        summary = metrics.summary(provider_events, duration, local, api is not None)
        n = summary["total_evaluated_observations"]
        known = summary["known_object_observations"]
        summary.update(
            correct_label_coverage=summary["correct_assignments"] / known
            if known
            else None,
            wrong_object_label_rate=summary["incorrect_assignments"] / n if n else None,
            unknown_rate=summary["unknown_observations"] / n if n else None,
            annotation_wrong_object_label_rate=metrics.summary(
                provider_events, duration, local, api is not None
            )["wrong_object_label_rate"],
            recovery_events=recovery_metrics(sequence, metrics.rows),
            tracking_update_hz=len(local) / (time.perf_counter() - seq_start),
            replay_processing=latency(processing),
            cpu_processing=latency(cpu),
            shared_detector_latency=latency(detector_times),
            replay_label_latency=latency(label_times),
            sensor_to_display_latency_ms=None,
            gpu_latency_ms=None,
        )
        summaries.append(
            {
                "id": sequence["id"],
                "recording_id": sequence["recording_id"],
                "condition": sequence["condition"],
                "metrics": summary,
            }
        )
        all_rows.extend(metrics.rows)
    await p.close()
    versions = {
        name: importlib.metadata.version(name)
        for name in ("numpy", "Pillow", "httpx", "pydantic")
    }
    result = {
        "version": 2,
        "method": args.method,
        "mode": args.method,
        "pass": args.pass_name,
        "protocol": args.protocol,
        "trial": args.trial,
        "dataset_sha256": fingerprint,
        "gallery_sha256": gallery_fingerprint(gallery),
        "detections_sha256": hashlib.sha256(
            Path(args.detections).read_bytes()
        ).hexdigest(),
        "initializations_sha256": hashlib.sha256(
            Path(args.initializations).read_bytes()
        ).hexdigest()
        if args.initializations
        else None,
        "evidence_kind": data.data["evidence_kind"],
        "provider_kind": "mock"
        if args.mock
        else "configured"
        if candidates
        else "disabled",
        "providers": provider_metadata,
        "configuration": config.public(),
        "descriptor": gallery.encoder.metadata(),
        "calibration": calibration.data if calibration else None,
        "detector": cache["detector"],
        "versions": {"python": platform.python_version(), **versions},
        "source_sha256": source_hash.hexdigest(),
        "collection_coverage": {
            c: {
                "required": 5,
                "genuine_recordings": sum(
                    s["condition"] == c for s in data.data["sequences"]
                )
                if data.data["evidence_kind"] == "real_recording"
                else 0,
            }
            for c in CONDITIONS
        },
        "pace": args.pace,
        "sequences": summaries,
        "peak_runner_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        / 1024,
        "remote_provider_peak_memory_mib": None,
        "wall_s": time.perf_counter() - started,
        "cpu_s": time.process_time() - cpu_start,
        "independent_real_recordings": len(summaries)
        if data.data["evidence_kind"] == "real_recording"
        else 0,
    }
    write_results(out, result, all_rows, hub.events if hub else [])
    (out / "frames.jsonl").write_text("".join(json.dumps(f) + "\n" for f in frame_rows))
    (out / "recovery-events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in p.events)
    )
    print(
        json.dumps(
            {
                "method": args.method,
                "pass": args.pass_name,
                "protocol": args.protocol,
                "out": str(out),
                "observations": len(all_rows),
                "provider_calls": len(hub.events) if hub else 0,
            }
        )
    )


def suite(args):
    if args.trials < 1:
        raise ValueError("--trials must be positive")
    out = fresh(args.out)
    for pass_name in args.passes:
        cache = out / f"detections-{pass_name}.json"
        prepare(args.dataset, pass_name, args.detector, cache)
        for trial in range(1, args.trials + 1):
            for method in args.methods:
                if not args.mock and method in ("H2", "H3", "H4"):
                    try:
                        configured_providers(method, Config.from_env())
                    except ValueError as error:
                        save_json(
                            out
                            / f"{pass_name}-{args.protocol}-{method}-r{trial}"
                            / "unavailable.json",
                            {
                                "method": method,
                                "pass": pass_name,
                                "protocol": args.protocol,
                                "trial": trial,
                                "status": "not_run",
                                "reason": str(error),
                            },
                        )
                        print(
                            method + ": not run (provider configuration unavailable)",
                            flush=True,
                        )
                        continue
                command = [
                    sys.executable,
                    __file__,
                    "run",
                    "--dataset",
                    args.dataset,
                    "--gallery",
                    args.gallery,
                    "--detections",
                    str(cache),
                    "--pass",
                    pass_name,
                    "--method",
                    method,
                    "--protocol",
                    args.protocol,
                    "--out",
                    str(out / f"{pass_name}-{args.protocol}-{method}-r{trial}"),
                    "--pace",
                    str(args.pace),
                    "--trial",
                    str(trial),
                    "--descriptor",
                    args.descriptor,
                ]
                for name in (
                    "calibration",
                    "initializations",
                    "backend",
                    "dino_repo",
                    "dino_weights",
                ):
                    if getattr(args, name, None):
                        command += [
                            "--" + name.replace("_", "-"),
                            str(getattr(args, name)),
                        ]
                if args.mock:
                    command += ["--mock"]
                subprocess.run(command, check=True)
    from identity_study_report import report

    report(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fixture", "plan"):
        s = sub.add_parser(name)
        s.add_argument("--out", required=True)
    for name in ("run", "suite"):
        s = sub.add_parser(name)
        s.add_argument("--dataset", required=True)
        s.add_argument("--gallery", required=True)
        s.add_argument("--out", required=True)
        s.add_argument("--calibration")
        s.add_argument("--initializations")
        s.add_argument("--backend")
        s.add_argument("--mock", action="store_true")
        s.add_argument("--protocol", choices=["events", "probes"], default="events")
        s.add_argument("--pace", type=float, default=1)
        s.add_argument(
            "--descriptor", choices=["color-grid", "dinov2"], default="color-grid"
        )
        s.add_argument("--dino-repo")
        s.add_argument("--dino-weights")
        if name == "run":
            s.add_argument("--method", choices=METHODS, required=True)
            s.add_argument(
                "--pass", dest="pass_name", choices=["A", "B"], required=True
            )
            s.add_argument("--detections", required=True)
            s.add_argument("--trial", type=int, default=1)
        else:
            s.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
            s.add_argument("--passes", nargs="+", choices=["A", "B"], default=["A"])
            s.add_argument(
                "--detector", choices=["nanodet", "yolox_s"], default="nanodet"
            )
            s.add_argument("--trials", type=int, default=1)
    r = sub.add_parser("report")
    r.add_argument("--root", required=True)
    v = sub.add_parser("serve")
    v.add_argument("--dataset", required=True)
    v.add_argument("--results", required=True)
    v.add_argument("--backend")
    v.add_argument("--port", type=int, default=8026)
    args = parser.parse_args()
    try:
        if args.command == "fixture":
            fixture(args)
        elif args.command == "plan":
            plan(args)
        elif args.command == "run":
            asyncio.run(run(args))
        elif args.command == "suite":
            suite(args)
        elif args.command == "report":
            from identity_study_report import report

            report(args.root)
        else:
            from identity_viewer import serve

            serve(args.dataset, args.results, args.port, args.backend)
    except Exception as error:
        # Do not include provider response bodies, keys, or URL credentials in terminal output.
        import httpx

        parser.exit(
            1,
            (type(error).__name__ if isinstance(error, httpx.HTTPError) else str(error))
            + "\n",
        )


if __name__ == "__main__":
    main()
