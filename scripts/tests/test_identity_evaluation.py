"""Dataset/metric tests use generated blocks, never experimental laptop imagery."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from app.identity.appearance import Calibration, ColorGrid
from app.identity.config import Config
from app.identity.controller import IdentityPipeline
from app.identity.dataset import Dataset
from app.identity.evaluation import Metrics, comparison
from app.identity.gallery import Gallery
from app.identity.vlm import MockVLM
from identity_experiment import (
    calibrate,
    fixture,
    import_video,
    run_experiment,
)

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"


def test_metric_denominators_switches_misses_and_recovery():
    m = Metrics()
    box = [0, 0, 10, 10]
    gt = [{"instance_id": "a", "object_id": A, "bbox": box}]

    def row(oid):
        return {
            "track_id": 1,
            "bbox": box,
            "object_id": oid,
            "identity_state": "matched" if oid else "unknown",
        }

    m.frame("s", 0, 0, gt, [row(A)], 1, {1: {"success": True, "count": 1}})
    m.frame("s", 1, 1, gt, [row(B)], 1, {1: {"success": True, "count": 1}})
    m.frame("s", 2, 2, gt, [], 1)
    m.frame("s", 3, 3, gt, [row(A)], 1, {1: {"success": True, "count": 0}})
    s = m.summary([], 3, [1] * 4, True)
    assert s["total_evaluated_observations"] == 4
    assert (
        s["correct_assignments"],
        s["incorrect_assignments"],
        s["unknown_observations"],
    ) == (2, 1, 1)
    assert s["identity_switches"] == 2 and s["detector_misses"] == 1
    assert (
        s["correct_retrieval_coverage"] == 0.5 and s["wrong_object_label_rate"] == 0.25
    )
    assert s["recovery"]["samples"] == 1 and s["recovery"]["median_ms"] == 2000
    assert s["vlm_latency"]["p95_ms"] is None and s["estimated_cost_usd"] is None
    assert m.summary([], 3, [1], False)["correct_retrieval_coverage"] is None


def test_fixture_runner_all_modes_and_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("IDENTITY_EXPERIMENT_ENABLED", "true")
    monkeypatch.setenv("IDENTITY_VLM_REQUESTS_PER_MINUTE", "100")
    folder = tmp_path / "input"
    fixture(SimpleNamespace(out=folder))
    data = Dataset(folder / "dataset.json")
    assert len(data.data["sequences"]) == 6
    outputs = []
    for mode in ("baseline", "vlm", "hybrid"):
        out = tmp_path / mode
        outputs.append(out)
        args = SimpleNamespace(
            dataset=folder / "dataset.json",
            gallery=None,
            out=out,
            mode=mode,
            calibration=folder / "calibration.json",
            descriptor="color-grid",
            dino_repo=None,
            dino_weights=None,
            mock=mode != "baseline",
            detector="manual",
            backend=None,
            pace=0.02,
            vlm_stride=4,
            max_frames=None,
            preview=True,
        )
        asyncio.run(run_experiment(args))
        result = json.loads((out / "summary.json").read_text())
        assert result["evidence_kind"] == "deterministic_fixture"
        assert (
            sum(
                s["metrics"]["total_evaluated_observations"]
                for s in result["sequences"]
            )
            == 93
        )
        assert (out / "tracks.jsonl").exists() and list((out / "preview").glob("*.png"))
        assert all(
            s["metrics"]["incorrect_assignments"] == 0 for s in result["sequences"]
        )
        if mode == "baseline":
            assert sum(s["metrics"]["vlm_requests"] for s in result["sequences"]) == 0
        if mode == "vlm":
            assert (
                sum(s["metrics"]["correct_proposals"] for s in result["sequences"]) > 0
            )
            assert (
                sum(s["metrics"]["correct_assignments"] for s in result["sequences"])
                == 0
            )
    comparison(outputs, tmp_path / "comparison")
    assert (tmp_path / "comparison/comparison.svg").exists()
    with pytest.raises(ValueError):
        fixture(SimpleNamespace(out=folder))


def test_dataset_rejects_paths_timestamps_and_invalid_boxes(tmp_path):
    folder = tmp_path / "fixture"
    fixture(SimpleNamespace(out=folder))
    path = folder / "dataset.json"
    original = json.loads(path.read_text())
    for change in ("path", "timestamp"):
        data = json.loads(json.dumps(original))
        if change == "path":
            data["sequences"][0]["frames"][0]["image"] = "../../outside.png"
        else:
            data["sequences"][0]["frames"][1]["timestamp_s"] = 0
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            Dataset(path)
    path.write_text(json.dumps(original))
    dataset = Dataset(path)
    frame = original["sequences"][0]["frames"][0]
    frame["detections"][0]["bbox"] = [-1, 0, 10, 10]
    with pytest.raises(ValueError):
        dataset.boxes(frame, dataset.image(frame))


def test_development_calibration_and_synthetic_guard(tmp_path, monkeypatch):
    folder = tmp_path / "fixture"
    fixture(SimpleNamespace(out=folder))
    original = json.loads((folder / "dataset.json").read_text())
    original["sequences"] = original["sequences"][:1]
    path = folder / "dev.json"
    path.write_text(json.dumps(original))
    out = folder / "derived.json"
    args = SimpleNamespace(
        dataset=path, gallery=folder / "gallery.json", out=out, descriptor="color-grid"
    )
    calibrate(args)
    c = Calibration.load(out, ColorGrid.name)
    assert c.data["observations"] == 16 and c.data["vlm_min"] is None
    monkeypatch.setenv("IDENTITY_EXPERIMENT_ENABLED", "true")
    args = SimpleNamespace(
        dataset=path,
        gallery=folder / "gallery.json",
        calibration=out,
        descriptor="color-grid",
        pace=0,
        vlm_stride=4,
    )
    with pytest.raises(ValueError, match="held-out"):
        asyncio.run(run_experiment(args))


def test_import_decoded_video(tmp_path):
    import cv2
    import numpy as np

    path = tmp_path / "input.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    assert writer.isOpened()
    for _ in range(10):
        writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    writer.release()
    import_video(
        SimpleNamespace(
            video=path,
            out=tmp_path / "decoded",
            sample_fps=2,
            sequence="test",
            condition="stationary",
        )
    )
    dataset = Dataset(tmp_path / "decoded/dataset.json")
    assert [f["timestamp_s"] for f in dataset.data["sequences"][0]["frames"]] == [
        0,
        0.5,
    ]
    assert dataset.image(dataset.data["sequences"][0]["frames"][0]).size == (64, 48)


def test_short_miss_preserves_identity_long_gap_requires_recovery(tmp_path):
    async def case():
        folder = tmp_path / "fixture"
        fixture(SimpleNamespace(out=folder))
        gallery = Gallery(folder / "gallery.json", ColorGrid())
        c = Calibration.load(folder / "calibration.json", ColorGrid.name)
        p = IdentityPipeline(
            gallery,
            Config(
                enabled=True, vlm_enabled=True, endpoint="http://mock", model="mock"
            ),
            c,
            MockVLM(delay=0.01),
        )
        image = Image.new("RGB", (32, 32), "red")
        box = [[0, 0, 32, 32]]
        assert (await p.step(image, box, 0))[0]["object_id"] == A
        await p.step(image, [], 0.1)
        assert (await p.step(image, box, 0.2))[0]["object_id"] == A
        assert not p.tasks
        await p.step(image, [], 0.4)
        row = (await p.step(image, box, 1.5))[0]
        assert (
            row["object_id"] is None and row["identity_state"] == "pending_verification"
        )
        await p.close()

    asyncio.run(case())
