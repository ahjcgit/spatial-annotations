"""H0-H4 ablations, shared input contracts, escalation, and viewer isolation."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from app.identity.appearance import Calibration, ColorGrid
from app.identity.config import Config
from app.identity.controller import IdentityPipeline
from app.identity.gallery import Gallery
from app.identity.providers import ProviderHub, configured_providers, provider_config
from app.identity.study import inspect_dataset, recovery_metrics
from app.identity.vlm import MockVLM, ProviderFailure, payload
from identity_study_report import report
from identity_suite import A, B, fixture, prepare, run
from identity_viewer import create_app


@pytest.fixture
def study(tmp_path, monkeypatch):
    monkeypatch.setenv("IDENTITY_EXPERIMENT_ENABLED", "true")
    monkeypatch.setenv("IDENTITY_VLM_REQUESTS_PER_MINUTE", "100")
    folder = tmp_path / "input"
    fixture(SimpleNamespace(out=folder))
    gallery = Gallery(folder / "gallery.json", ColorGrid())
    return folder, gallery


def cfg(**kwargs):
    return Config(
        enabled=True, vlm_enabled=True, endpoint="http://mock", model="mock", **kwargs
    )


def request(gallery):
    return {
        "epoch": 0,
        "request_id": 1,
        "references": gallery.images,
        "observations": [
            {
                "track_id": 1,
                "generation": 0,
                "timestamp": 0.0,
                "reason": "ambiguous_appearance",
                "previous_object_id": None,
                "crop": Image.new("RGB", (32, 32), "red"),
            }
        ],
    }


def answer(req):
    return {
        "matches": [
            {
                "track_id": o["track_id"],
                "object_id": A,
                "status": "proposed",
                "evidence": "mock evidence",
            }
            for o in req["observations"]
        ]
    }


def test_h0_never_uses_appearance_and_needs_explicit_seed(study, monkeypatch):
    async def case():
        _, gallery = study
        p = IdentityPipeline(gallery, Config(enabled=True), mode="heuristic")
        monkeypatch.setattr(
            gallery.encoder,
            "encode",
            lambda _: pytest.fail("H0 must not encode observations"),
        )
        row = (await p.step(Image.new("RGB", (60, 40), "red"), [[0, 0, 30, 30]], 0))[0]
        assert row["object_id"] is None
        assert p.confirm(row["track_id"], row["generation"], A, persist=False)
        row = (await p.step(Image.new("RGB", (60, 40), "blue"), [[2, 0, 32, 30]], 0.1))[
            0
        ]
        assert (
            row["object_id"] == A and row["match_source"] == "motion"
        )  # geometry alone cannot detect an appearance replacement
        p.reset()
        row = (await p.step(Image.new("RGB", (60, 40), "red"), [[2, 0, 32, 30]], 0))[0]
        assert row["object_id"] is None and not p.events

    asyncio.run(case())


def test_h1_viewpoint_and_swap(study):
    async def case():
        folder, gallery = study
        cal = Calibration.load(folder / "calibration.json", gallery.encoder.name)
        p = IdentityPipeline(gallery, Config(enabled=True), cal, mode="baseline")
        p.tracker.geometry_only = True
        data = inspect_dataset(folder / "dataset.json", "A", "events")
        for seq in [
            s for s in data.data["sequences"] if s["condition"] in ("C2", "C6")
        ]:
            p.reset()
            for f in seq["frames"]:
                if f["reset_session"]:
                    p.reset()
                rows = await p.step(
                    data.image(f),
                    [g["bbox"] for g in f["ground_truth"]],
                    f["timestamp_s"],
                )
                assert [r["object_id"] for r in rows] == [
                    g["object_id"] for g in f["ground_truth"]
                ]

    asyncio.run(case())


def test_local_unknown_escalates_and_tracking_continues(study):
    async def case():
        _, g = study
        local = MockVLM(delay=0.025)
        frontier = MockVLM(answer, delay=0.025)
        hub = ProviderHub(
            [("local", local, cfg()), ("frontier", frontier, cfg())],
            cfg(),
            escalate=True,
        )
        p = IdentityPipeline(g, cfg(), adapter=hub)
        hub.current = p._current
        for i in range(5):
            rows = await p.step(
                Image.new("RGB", (32, 32), "red"), [[0, 0, 32, 32]], i * 0.01
            )
            assert rows[0]["object_id"] is None
            await asyncio.sleep(0.001)
        assert len(local.calls) == 1 and not frontier.calls
        await p.settle()
        assert (
            len(frontier.calls) == 1
            and p.snapshot()[0]["vlm_proposal"]["object_id"] == A
        )
        assert [e["provider"] for e in hub.events] == ["local", "frontier"]
        assert (
            p.snapshot()[0]["object_id"] is None
        )  # proposal is not automatic acceptance

    asyncio.run(case())


@pytest.mark.parametrize("failure", ["timeout", "malformed"])
def test_provider_failure_can_escalate(study, failure):
    async def case():
        _, g = study
        local = (
            MockVLM(delay=0.03)
            if failure == "timeout"
            else MockVLM("invalid secret response")
        )
        hub = ProviderHub(
            [
                ("local", local, cfg(timeout_s=0.005)),
                ("frontier", MockVLM(answer), cfg()),
            ],
            cfg(),
            escalate=True,
        )
        result = await hub.match(request(g))
        assert result["response"]["matches"][0]["object_id"] == A
        assert hub.events[0]["failure_category"] == (
            "timeout" if failure == "timeout" else "invalid_response"
        )
        assert "secret" not in json.dumps(hub.events)

    asyncio.run(case())


def test_no_escalation_after_session_change(study):
    async def case():
        _, g = study
        local = MockVLM(delay=0.03)
        frontier = MockVLM(answer)
        hub = ProviderHub(
            [("local", local, cfg()), ("frontier", frontier, cfg())],
            cfg(),
            escalate=True,
        )
        p = IdentityPipeline(g, cfg(), adapter=hub)
        hub.current = p._current
        await p.step(Image.new("RGB", (32, 32), "red"), [[0, 0, 32, 32]], 0)
        await asyncio.sleep(0.005)
        p.reset()
        await p.settle()
        assert not frontier.calls and p.snapshot() == []

    asyncio.run(case())


def test_global_budget_counts_both_provider_stages(study):
    async def case():
        _, g = study
        frontier = MockVLM(answer)
        hub = ProviderHub(
            [("local", MockVLM(), cfg()), ("frontier", frontier, cfg())],
            cfg(requests_per_minute=1),
            escalate=True,
        )
        with pytest.raises(ProviderFailure):
            await hub.match(request(g))
        assert len(hub.events) == 1 and not frontier.calls

    asyncio.run(case())


def test_frontier_requires_explicit_authorization(monkeypatch):
    monkeypatch.setenv("IDENTITY_FRONTIER_ENABLED", "true")
    monkeypatch.delenv("IDENTITY_FRONTIER_AUTHORIZED", raising=False)
    monkeypatch.setenv("IDENTITY_FRONTIER_ENDPOINT", "http://local/v1")
    monkeypatch.setenv("IDENTITY_FRONTIER_MODEL", "test")
    with pytest.raises(ValueError, match="AUTHORIZED"):
        provider_config("frontier", Config(enabled=True))
    monkeypatch.setenv("IDENTITY_FRONTIER_AUTHORIZED", "true")
    assert provider_config("frontier", Config(enabled=True)).model == "test"
    monkeypatch.setenv("IDENTITY_LOCAL_ENABLED", "false")
    with pytest.raises(ValueError, match="local"):
        configured_providers("H4", Config(enabled=True))


def test_no_ground_truth_or_filenames_in_provider_input(study):
    _, g = study
    r = request(g)
    r.update(
        ground_truth="GT_SECRET",
        filename="GT_SECRET-laptop-a.jpg",
        annotations=["PRIVATE_CONTENT"],
        access_token="PRIVATE_TOKEN",
    )
    r["observations"][0]["ground_truth"] = "GT_SECRET"
    encoded = json.dumps(payload(r, cfg()))
    for forbidden in ("GT_SECRET", "PRIVATE_CONTENT", "PRIVATE_TOKEN"):
        assert forbidden not in encoded


def test_recovery_metrics_are_hand_checkable():
    sequence = {
        "frames": [
            {"timestamp_s": 0, "ground_truth": [{"instance_id": "a", "object_id": A}]},
            {"timestamp_s": 0.5},
            {"timestamp_s": 1.5},
        ],
        "recovery_events": [
            {"kind": "swap", "instance_id": "a", "start_frame": 0, "deadline_frame": 2}
        ],
    }
    rows = [
        {
            "frame_index": 1,
            "timestamp_s": 0.5,
            "instance_id": "a",
            "object_id": B,
            "correct": False,
        },
        {
            "frame_index": 2,
            "timestamp_s": 1.5,
            "instance_id": "a",
            "object_id": A,
            "correct": True,
        },
    ]
    m = recovery_metrics(sequence, rows)
    assert m["swap"]["recovered"] == 1 and m["swap"]["latency"]["median_ms"] == 1500
    assert recovery_metrics(sequence, rows[:1])["swap"]["recovered"] == 0


def test_registry_embedding_export_and_status(study):
    _, g = study
    path = g.cache_embeddings()
    cache = json.loads(path.read_text())
    assert (
        cache["model"]["name"] == g.encoder.name
        and len(cache["objects"][A][0]["vector"]) == 448
    )
    g.verified(A, [1, 2, 3, 4])
    assert g.objects[A]["verification_status"] == "operator_verified"
    assert "last_known_room_position" in g.objects[A]


def test_five_methods_same_inputs_viewer_and_comparison(study, tmp_path):
    folder, g = study
    cache = tmp_path / "cache.json"
    prepare(folder / "dataset.json", "A", "nanodet", cache)
    outputs = tmp_path / "results"
    for method in ("H0", "H1", "H2", "H3", "H4"):
        args = SimpleNamespace(
            method=method,
            dataset=folder / "dataset.json",
            gallery=g.path,
            calibration=folder / "calibration.json",
            detections=cache,
            pass_name="A",
            protocol="events",
            out=outputs / method,
            pace=0.02,
            trial=1,
            descriptor="color-grid",
            mock=True,
            initializations=folder / "initializations.json",
            backend=None,
        )
        asyncio.run(run(args))
    report(outputs)
    summaries = [json.loads(p.read_text()) for p in outputs.glob("*/summary.json")]
    assert len({s["detections_sha256"] for s in summaries}) == 1
    assert len({s["gallery_sha256"] for s in summaries}) == 1
    assert all(s["independent_real_recordings"] == 0 for s in summaries)
    h4 = next(s for s in summaries if s["method"] == "H4")
    assert sum(s["metrics"]["vlm_requests"] for s in h4["sequences"]) > 0
    with TestClient(create_app(folder / "dataset.json", outputs)) as client:
        assert len(client.get("/api/study").json()["runs"]) == 5
        packet = client.get("/api/frame/0/0", params={"run": "H1"}).json()
        assert "ground_truth" not in packet and "PRIVATE" not in json.dumps(packet)
        assert client.get(
            "/api/frame/0/0", params={"run": "H1", "evaluation": "true"}
        ).json()["ground_truth"]
        assert client.get("/api/image/999/0").status_code == 404
        assert (
            client.get("/api/frame/0/0", params={"run": "../gallery.json"}).status_code
            == 404
        )
        assert client.get("/api/image/0/0").headers["content-type"].startswith("image/")
        assert client.get("/").headers["content-security-policy"]
    assert (outputs / "tradeoff-A-events.png").exists()


def test_probe_masks_and_stale_detection_cache(study, tmp_path):
    async def case():
        folder, g = study
        cache = tmp_path / "cache.json"
        prepare(folder / "dataset.json", "A", "nanodet", cache)
        args = SimpleNamespace(
            method="H3",
            dataset=folder / "dataset.json",
            gallery=g.path,
            calibration=folder / "calibration.json",
            detections=cache,
            pass_name="A",
            protocol="probes",
            out=tmp_path / "H3",
            pace=0,
            trial=1,
            descriptor="color-grid",
            mock=True,
            initializations=None,
            backend=None,
        )
        await run(args)
        summary = json.loads((args.out / "summary.json").read_text())
        assert (
            sum(
                s["metrics"]["total_evaluated_observations"]
                for s in summary["sequences"]
            )
            == 28
        )
        frame_rows = [
            json.loads(line)
            for line in (args.out / "frames.jsonl").read_text().splitlines()
        ]
        assert sum(f["selected"] for f in frame_rows) == 14
        # Renaming a development image must not allow its bytes into held-out evaluation.
        import hashlib

        manifest = json.loads(args.dataset.read_text())
        frame_path = folder / manifest["sequences"][0]["frames"][0]["image"]
        calibration = json.loads(args.calibration.read_text())
        calibration["development_image_sha256"] = [
            hashlib.sha256(frame_path.read_bytes()).hexdigest()
        ]
        args.calibration.write_text(json.dumps(calibration))
        with pytest.raises(ValueError, match="image overlap"):
            await run(args)
        calibration.pop("development_image_sha256")
        args.calibration.write_text(json.dumps(calibration))
        data = json.loads(cache.read_text())
        data["dataset_sha256"] = "different"
        cache.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="cache"):
            await run(args)

    asyncio.run(case())


def test_wrong_visual_proposal_is_rejected_then_supported_frontier_can_recover(study):
    async def case():
        folder, g = study
        cal = Calibration.load(folder / "calibration.json", g.encoder.name)
        wrong = lambda req: {
            "matches": [
                {
                    "track_id": o["track_id"],
                    "object_id": B,
                    "status": "proposed",
                    "evidence": "uncalibrated claim",
                }
                for o in req["observations"]
            ]
        }
        for escalate in (False, True):
            c = cfg(acceptance="corroborated")
            providers = [("local", MockVLM(wrong), c)]
            if escalate:
                providers.append(("frontier", MockVLM(answer), c))
            hub = ProviderHub(providers, c, escalate=escalate)
            p = IdentityPipeline(g, c, cal, hub, mode="vlm")
            hub.current = p._current
            hub.supported = lambda req, matches: all(
                cal.accept(
                    p.tracker.tracks[m["track_id"]].scores, m["object_id"], vlm=True
                )
                for m in matches
            )
            await p.step(Image.new("RGB", (32, 32), "red"), [[0, 0, 32, 32]], 0)
            await p.settle()
            assert p.snapshot()[0]["object_id"] == (A if escalate else None)

    asyncio.run(case())
