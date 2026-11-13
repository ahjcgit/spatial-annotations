#!/usr/bin/env python3
"""Opt-in recorded-image identity experiment. Never imported by the live demo."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import sys
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.identity.annotations import AnnotationClient
from app.identity.appearance import Calibration, ColorGrid, DinoLocal
from app.identity.config import Config
from app.identity.controller import IdentityPipeline
from app.identity.dataset import Dataset
from app.identity.evaluation import Metrics, comparison, write_results
from app.identity.gallery import Gallery, register, save_json
from app.identity.vlm import MockVLM, OpenAICompatible
from PIL import Image, ImageDraw

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"


def encoder(args):
    if args.descriptor == "dinov2":
        if not args.dino_repo or not args.dino_weights:
            raise ValueError(
                "DINO requires --dino-repo and --dino-weights; no automatic downloads"
            )
        return DinoLocal(args.dino_repo, args.dino_weights)
    return ColorGrid()


def fresh(directory):
    p = Path(directory)
    if p.exists() and any(p.iterdir()):
        raise ValueError(
            "Output directory must be empty; existing data will not be overwritten"
        )
    p.mkdir(parents=True, exist_ok=True)
    return p


def fixture(args):
    """Abstract colored blocks, deliberately not fabricated experimental laptop images."""
    out = fresh(args.out)
    for oid, color in [(A, "red"), (B, "blue")]:
        source = out / (color + ".png")
        Image.new("RGB", (32, 32), color).save(source)
        register(
            out / "gallery.json", {"id": oid, "name": "Fixture " + color}, [source]
        )
    sequences = []
    for condition in [
        "stationary",
        "position_swap",
        "moving",
        "disappearance",
        "new_session",
        "ambiguous",
    ]:
        frames = []
        for i in range(8):
            entries = [(A, "red", [8, 12, 40, 44]), (B, "blue", [90, 12, 122, 44])]
            if condition == "position_swap" and i >= 4:
                entries = [(B, "blue", entries[0][2]), (A, "red", entries[1][2])]
            if condition == "moving":
                entries = [
                    (oid, color, [b[0] + i, b[1], b[2] + i, b[3]])
                    for oid, color, b in entries
                ]
            if condition == "disappearance" and i in (2, 3, 4):
                entries = entries[:1]
            if condition == "ambiguous":
                entries = [(oid, "gray", box) for oid, _, box in entries]
            im = Image.new("RGB", (144, 64), "#202020")
            for _, color, box in entries:
                im.paste(color, box)
            name = f"frames/{condition}/{i:04d}.png"
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            im.save(out / name)
            frames.append(
                {
                    "image": name,
                    "timestamp_s": i * 0.5,
                    "reset_session": condition == "new_session" and i == 4,
                    "detections": [
                        {"bbox": box, "label": "laptop"} for _, _, box in entries
                    ],
                    "ground_truth": [
                        {"instance_id": oid, "object_id": oid, "bbox": box}
                        for oid, _, box in entries
                    ],
                }
            )
        sequences.append({"id": condition, "condition": condition, "frames": frames})
    save_json(
        out / "dataset.json",
        {
            "version": 1,
            "evidence_kind": "deterministic_fixture",
            "description": "Abstract colored blocks; software checks, not laptop or VLM accuracy evidence.",
            "gallery": "gallery.json",
            "sequences": sequences,
        },
    )
    save_json(
        out / "calibration.json",
        {
            "embedding_model": ColorGrid.name,
            "development_set": "deterministic-colored-block-software-fixture",
            "synthetic_only": True,
            "appearance_min": 0.98,
            "appearance_margin": 0.1,
            "vlm_min": 0.9,
            "vlm_margin": 0.05,
            "vlm_development_set": "deterministic-colored-block-software-fixture",
        },
    )
    print("Created synthetic software fixture:", out / "dataset.json")


def register_cli(args):
    import httpx

    if not Config.from_env().enabled:
        raise ValueError("Set IDENTITY_EXPERIMENT_ENABLED=true")
    token = os.environ.get("IDENTITY_API_TOKEN")
    if not token:
        raise ValueError(
            "Set IDENTITY_API_TOKEN using an existing authenticated account"
        )
    with httpx.Client(
        base_url=args.backend.rstrip("/"),
        headers={"Authorization": "Bearer " + token},
        timeout=15,
        follow_redirects=False,
    ) as client:
        client.get("/users/me").raise_for_status()
        if args.object_id:
            response = client.get("/objects/" + args.object_id)
        else:
            response = client.post(
                "/objects",
                json={
                    "marker_id": str(uuid4()),
                    "name": args.name,
                    "spatial_metadata": {"detection_label": "laptop"},
                },
            )
        response.raise_for_status()
        record = response.json()
        obj = register(args.gallery, record, args.images)
    print(
        json.dumps(
            {
                "object_id": obj["object_id"],
                "marker_id": record["marker_id"],
                "name": obj["name"],
                "reference_count": len(obj["references"]),
            }
        )
    )


def import_video(args):
    import cv2

    if args.sample_fps <= 0:
        raise ValueError("--sample-fps must be positive")
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise ValueError("Cannot open video")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        raise ValueError(
            "Video has no usable FPS; supply decoded images with explicit timestamps instead"
        )
    out = fresh(args.out)
    (out / "frames").mkdir()
    rows = []
    index = 0
    next_time = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            timestamp = index / fps
            if timestamp >= next_time:
                name = f"frames/{index:08d}.png"
                if not cv2.imwrite(str(out / name), frame):
                    raise ValueError("Could not write decoded frame")
                rows.append(
                    {
                        "image": name,
                        "timestamp_s": timestamp,
                        "width": frame.shape[1],
                        "height": frame.shape[0],
                        "detections": [],
                        "ground_truth": None,
                    }
                )
                next_time += 1 / args.sample_fps
            index += 1
    finally:
        cap.release()
    if not rows:
        raise ValueError("Video contained no decoded frames")
    save_json(
        out / "dataset.json",
        {
            "version": 1,
            "evidence_kind": "real_recording",
            "source": {
                "sha256": hashlib.sha256(Path(args.video).read_bytes()).hexdigest(),
                "timestamp_source": "decoded frame index / container FPS; constant-FPS assumption",
                "fps": fps,
                "orientation": "OpenCV decoded orientation",
                "sample_fps": args.sample_fps,
            },
            "sequences": [
                {"id": args.sequence, "condition": args.condition, "frames": rows}
            ],
        },
    )
    print(
        f"Imported {len(rows)} frames. Add ground_truth and manual detections, or use --detector nanodet."
    )


def calibrate(args):
    data = Dataset(args.dataset)
    enc = encoder(args)
    gallery = Gallery(args.gallery, enc)
    positives = []
    negatives = []
    margins = []
    observations = 0
    for sequence in data.data["sequences"]:
        for frame in sequence["frames"]:
            image = data.image(frame)
            for gt in data.validate_gt(frame, image) or []:
                scores = gallery.scores(enc.encode(image.crop(gt["bbox"])))
                expected = gt["object_id"]
                observations += 1
                if expected is None:
                    negatives.extend(scores.values())
                else:
                    if expected not in scores:
                        raise ValueError("Development identity absent from gallery")
                    other = max(
                        [v for k, v in scores.items() if k != expected], default=0.0
                    )
                    positives.append(scores[expected])
                    negatives.append(other)
                    margins.append(scores[expected] - other)
    if (
        not positives
        or not negatives
        or min(positives) <= max(negatives)
        or min(margins) <= 0
    ):
        raise ValueError(
            "Development scores are not separable. Keep unknown; collect references or replace descriptor."
        )
    path = Path(args.out)
    if path.exists():
        raise ValueError("Calibration output exists")
    value = {
        "embedding_model": enc.name,
        "development_set": str(Path(args.dataset).resolve()),
        "development_sha256": data.fingerprint(),
        "synthetic_only": data.data["evidence_kind"] == "deterministic_fixture",
        "observations": observations,
        "appearance_min": (min(positives) + max(negatives)) / 2,
        "appearance_margin": min(margins) / 2,
        "method": "midpoint separating development genuine/impostor scores; half minimum genuine margin",
        "vlm_min": None,
        "vlm_margin": None,
    }
    save_json(path, value)
    print(
        "Saved development-derived appearance gates; no VLM acceptance calibration:",
        path,
    )


def mock_adapter(gallery):
    def answer(request):
        matches = []
        for obs in request["observations"]:
            scores = gallery.scores(gallery.encoder.encode(obs["crop"]))
            ranked = sorted(scores, key=scores.get, reverse=True)
            oid = (
                ranked[0]
                if ranked
                and scores[ranked[0]] > 0.99
                and (len(ranked) == 1 or scores[ranked[0]] - scores[ranked[1]] > 0.1)
                else None
            )
            matches.append(
                {
                    "track_id": obs["track_id"],
                    "object_id": oid,
                    "status": "proposed" if oid else "unknown",
                    "evidence": "Deterministic descriptor mock, not a VLM",
                }
            )
        return {"matches": matches}

    return MockVLM(answer, delay=0.005)


def preview(image, rows, gallery, retrieval, path):
    im = image.copy()
    draw = ImageDraw.Draw(im)
    for row in rows:
        matched = row["identity_state"] == "matched"
        color = "#00c878" if matched else "#ffd15c"
        draw.rectangle(row["bbox"], outline=color, width=2)
        name = (
            gallery.objects[row["object_id"]]["name"]
            if matched
            else row["identity_state"]
        )
        result = retrieval.get(row["track_id"])
        if result:
            name += (
                f" | {result['count']} notes"
                if result["success"]
                else " | lookup failed"
            )
        # No private note text or VLM explanations are written into preview artifacts.
        draw.text(
            (row["bbox"][0], max(0, row["bbox"][1] - 12)),
            f"T{row['track_id']} {name}",
            fill=color,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


async def run_experiment(args):
    config = Config.from_env()
    if not config.enabled:
        raise ValueError("Set IDENTITY_EXPERIMENT_ENABLED=true")
    if not math.isfinite(args.pace) or args.pace < 0 or args.vlm_stride < 2:
        raise ValueError(
            "--pace must be >=0 and --vlm-stride >=2 (VLM is never run on every video frame)"
        )
    data = Dataset(args.dataset)
    digest = data.fingerprint()
    gallery_path = args.gallery or data.root / data.data.get("gallery", "gallery.json")
    gallery = Gallery(gallery_path, encoder(args))
    calibration = (
        Calibration.load(args.calibration, gallery.encoder.name)
        if args.calibration
        else None
    )
    if calibration:
        if (
            calibration.data.get("synthetic_only")
            and data.data["evidence_kind"] != "deterministic_fixture"
        ):
            raise ValueError("Synthetic calibration cannot be used on real recordings")
        if calibration.data.get("development_sha256") == digest:
            raise ValueError("Use a separate held-out evaluation dataset")
    if args.mock:
        if data.data["evidence_kind"] != "deterministic_fixture":
            raise ValueError("--mock is limited to synthetic software fixtures")
        config = replace(
            config,
            vlm_enabled=True,
            endpoint="http://deterministic-mock.invalid",
            model="deterministic-mock",
        )
        adapter = mock_adapter(gallery)
    else:
        adapter = OpenAICompatible(config) if config.vlm_enabled else None
    if args.mode != "baseline" and adapter is None:
        raise ValueError(
            "VLM/hybrid comparison needs a configured provider or explicit --mock fixture"
        )
    out = fresh(args.out)
    pipeline = IdentityPipeline(gallery, config, calibration, adapter, mode=args.mode)
    client = AnnotationClient(args.backend, pipeline) if args.backend else None
    if client:
        token = os.environ.get("IDENTITY_API_TOKEN")
        if not token:
            raise ValueError("Backend retrieval requires IDENTITY_API_TOKEN")
        client.set_token(token)
    detector = None
    if args.detector != "manual":
        from eval_models import EvaluationModel

        detector = EvaluationModel(args.detector)
    sequences = []
    all_rows = []
    observation_rows = []
    start_wall = time.perf_counter()
    try:
        for sequence in data.data["sequences"]:
            await (
                pipeline.close()
            )  # preserve global rate budget, reset track/session context
            event_start = len(pipeline.events)
            metrics = Metrics()
            times = []
            detector_ms = []
            session = 0
            frames = (
                sequence["frames"][: args.max_frames]
                if args.max_frames
                else sequence["frames"]
            )
            seq_wall = time.perf_counter()
            first_time = frames[0]["timestamp_s"] if frames else 0
            for index, frame in enumerate(frames):
                target = seq_wall + (frame["timestamp_s"] - first_time) * args.pace
                await asyncio.sleep(max(0, target - time.perf_counter()))
                if frame.get("reset_session"):
                    await pipeline.close()
                    session += 1
                image = data.image(frame)
                gt = data.validate_gt(frame, image)
                if detector:
                    raw = io.BytesIO()
                    image.save(raw, format="PNG")
                    detected = await asyncio.to_thread(detector.infer, raw.getvalue())
                    boxes = [
                        [d["box"][j] * image.size[j % 2] for j in range(4)]
                        for d in detected["detections"]
                        if d["label"] == "laptop"
                    ]
                    detector_ms.append(detected["total_ms"])
                else:
                    boxes = data.boxes(frame, image)
                if args.mode == "vlm":
                    await pipeline.close()  # B: independent selected observations, no prior temporal identities
                    if index % args.vlm_stride == 0:
                        await pipeline.step(image, boxes, frame["timestamp_s"])
                        await (
                            pipeline.settle()
                        )  # standalone correspondence experiment only
                        rows = pipeline.snapshot()
                        local_ms = pipeline.last_local_ms
                    else:
                        rows = [
                            {
                                "track_id": -(j + 1),
                                "generation": 0,
                                "bbox": b,
                                "object_id": None,
                                "identity_state": "unknown",
                                "match_source": None,
                                "match_score": None,
                            }
                            for j, b in enumerate(boxes)
                        ]
                        local_ms = None
                else:
                    rows = await pipeline.step(image, boxes, frame["timestamp_s"])
                    local_ms = pipeline.last_local_ms
                if local_ms is not None:
                    times.append(local_ms)
                retrieval = {}
                if client:

                    async def fetch(row):
                        if row["identity_state"] != "matched":
                            return
                        try:
                            notes = await client.retrieve(row)
                            retrieval[row["track_id"]] = {
                                "success": notes is not None,
                                "count": len(notes or []),
                                "failure": None if notes is not None else "invalidated",
                            }
                        except Exception as exc:
                            retrieval[row["track_id"]] = {
                                "success": False,
                                "count": 0,
                                "failure": type(exc).__name__,
                            }

                    await asyncio.gather(*(fetch(row) for row in rows))
                    # An expired session must also invalidate labels in this frame.
                    live = {r["track_id"]: r for r in pipeline.snapshot()}
                    for row in rows:
                        if row["object_id"] and (
                            row["track_id"] not in live
                            or live[row["track_id"]]["object_id"] != row["object_id"]
                        ):
                            row.update(
                                object_id=None,
                                identity_state="unknown",
                                match_source=None,
                                match_score=None,
                            )
                metrics.frame(
                    sequence["id"],
                    index,
                    frame["timestamp_s"],
                    gt,
                    rows,
                    local_ms,
                    retrieval,
                    session,
                )
                for row in rows:
                    safe = {k: v for k, v in row.items() if k != "vlm_proposal"}
                    proposal = row.get("vlm_proposal")
                    safe["proposed_object_id"] = (
                        proposal["object_id"] if proposal else None
                    )
                    observation_rows.append(
                        {
                            "sequence": sequence["id"],
                            "frame_index": index,
                            "timestamp_s": frame["timestamp_s"],
                            **safe,
                        }
                    )
                if args.preview:
                    preview(
                        image,
                        rows,
                        gallery,
                        retrieval,
                        out / "preview" / f"{len(sequences):03d}-{index:06d}.png",
                    )
            await (
                pipeline.close()
            )  # cancel responses that arrived after the last evaluated observation
            events = pipeline.events[event_start:]
            duration = frames[-1]["timestamp_s"] - first_time if len(frames) > 1 else 0
            summary = metrics.summary(events, duration, times, client is not None)
            from app.identity.evaluation import latency

            summary["detector_latency"] = latency(detector_ms)
            summary["evaluated_frames"] = sum(
                f.get("ground_truth") is not None for f in frames
            )
            summary["processed_frames"] = len(frames)
            for event in events:
                event["sequence"] = sequence["id"]
            sequences.append(
                {
                    "id": sequence["id"],
                    "condition": sequence["condition"],
                    "metrics": summary,
                }
            )
            all_rows.extend(metrics.rows)
    finally:
        await pipeline.close()
    versions = {}
    for package in ("numpy", "Pillow", "httpx", "pydantic", "opencv-python", "torch"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    result = {
        "version": 1,
        "evidence_kind": data.data["evidence_kind"],
        "dataset_sha256": digest,
        "gallery_sha256": hashlib.sha256(Path(gallery_path).read_bytes()).hexdigest(),
        "mode": args.mode,
        "provider_kind": "mock"
        if args.mock
        else ("real_endpoint" if adapter else "disabled"),
        "configuration": config.public(),
        "calibration": calibration.data if calibration else None,
        "descriptor": gallery.encoder.metadata(),
        "detector": detector.metadata if detector else {"name": "manual_boxes"},
        "versions": {"python": platform.python_version(), **versions},
        "replay_pace": args.pace,
        "vlm_stride": args.vlm_stride,
        "elapsed_wall_s": time.perf_counter() - start_wall,
        "sequences": sequences,
        "interpretation": "Frame observations are correlated. Synthetic/mock results are software checks. B scores independent proposals separately; accepted identities always require policy validation. No RayNeo test.",
    }
    write_results(out, result, all_rows, pipeline.events)
    (out / "tracks.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in observation_rows)
    )
    print(
        json.dumps(
            {
                "output": str(out),
                "evidence_kind": result["evidence_kind"],
                "provider_kind": result["provider_kind"],
                "sequences": len(sequences),
                "observations": len(all_rows),
                "requests": len(pipeline.events),
            }
        )
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fixture")
    f.add_argument("--out", required=True)
    r = sub.add_parser("register")
    r.add_argument("--gallery", required=True)
    r.add_argument("--backend", required=True)
    identity = r.add_mutually_exclusive_group(required=True)
    identity.add_argument("--object-id")
    identity.add_argument("--name")
    r.add_argument("--images", nargs="+", required=True)
    v = sub.add_parser("import-video")
    v.add_argument("--video", required=True)
    v.add_argument("--out", required=True)
    v.add_argument("--sample-fps", type=float, default=2)
    v.add_argument("--sequence", default="sequence-1")
    v.add_argument("--condition", required=True)
    c = sub.add_parser("calibrate")
    c.add_argument("--dataset", required=True)
    c.add_argument("--gallery", required=True)
    c.add_argument("--out", required=True)
    e = sub.add_parser("run")
    e.add_argument("--dataset", required=True)
    e.add_argument("--gallery")
    e.add_argument("--out", required=True)
    e.add_argument("--mode", choices=["baseline", "vlm", "hybrid"], required=True)
    e.add_argument("--calibration")
    e.add_argument(
        "--detector", choices=["manual", "nanodet", "yolox_s"], default="manual"
    )
    e.add_argument("--mock", action="store_true")
    e.add_argument(
        "--pace",
        type=float,
        default=1,
        help="wall seconds per recorded second; 0 is throughput testing, not live latency",
    )
    e.add_argument("--vlm-stride", type=int, default=4)
    e.add_argument("--max-frames", type=int)
    e.add_argument("--backend")
    e.add_argument("--preview", action="store_true")
    for parser in (e, c):
        parser.add_argument(
            "--descriptor", choices=["color-grid", "dinov2"], default="color-grid"
        )
        parser.add_argument("--dino-repo")
        parser.add_argument("--dino-weights")
    comp = sub.add_parser("compare")
    comp.add_argument("--runs", nargs="+", required=True)
    comp.add_argument("--out", required=True)
    args = p.parse_args()
    try:
        if args.command == "fixture":
            fixture(args)
        elif args.command == "register":
            register_cli(args)
        elif args.command == "import-video":
            import_video(args)
        elif args.command == "calibrate":
            calibrate(args)
        elif args.command == "compare":
            comparison(args.runs, fresh(args.out))
        else:
            asyncio.run(run_experiment(args))
    except Exception as exc:
        # HTTP exceptions can embed URLs; provider bodies and credentials are never printed.
        import httpx

        message = type(exc).__name__ if isinstance(exc, httpx.HTTPError) else str(exc)
        p.exit(1, message + "\n")


if __name__ == "__main__":
    main()
