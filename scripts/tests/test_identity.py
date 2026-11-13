"""Deterministic software tests. Colored blocks/vectors are not laptop accuracy evidence."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.identity.appearance import Calibration, ColorGrid
from app.identity.config import Config
from app.identity.controller import IdentityPipeline
from app.identity.gallery import Gallery, register
from app.identity.vlm import (
    InvalidResponse,
    MockVLM,
    OpenAICompatible,
    validate,
)

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
BOXES = [[0, 0, 30, 30], [50, 0, 80, 30]]


def scene(colors=("red", "blue")):
    im = Image.new("RGB", (80, 40), "black")
    for box, color in zip(BOXES, colors):
        im.paste(color, tuple(box))
    return im


@pytest.fixture
def gallery(tmp_path):
    path = tmp_path / "gallery.json"
    for oid, color in [(A, "red"), (B, "blue")]:
        p = tmp_path / (color + ".png")
        Image.new("RGB", (30, 30), color).save(p)
        register(path, {"id": oid, "name": "Test " + color}, [p, p])
    return Gallery(path, ColorGrid())


def cal(gallery, vlm=True):
    # These thresholds belong only to the deterministic colored-block test fixture.
    return Calibration(
        {
            "embedding_model": gallery.encoder.name,
            "development_set": "synthetic-software-fixture",
            "appearance_min": 0.98,
            "appearance_margin": 0.1,
            "vlm_min": 0.9 if vlm else None,
            "vlm_margin": 0.05,
            "vlm_development_set": "synthetic-software-fixture",
        },
        gallery.encoder.name,
    )


def config(**kw):
    return Config(enabled=True, **kw)


def proposed(req):
    return {
        "matches": [
            {
                "track_id": o["track_id"],
                "object_id": A if o["crop"].getpixel((1, 1))[0] > 100 else B,
                "evidence": "mock color",
                "status": "proposed",
            }
            for o in req["observations"]
        ]
    }


def run(fn):
    return asyncio.run(fn())


def test_gallery_persistent_uuid_and_references(gallery):
    assert len(gallery.objects) == 2 and all(
        len(o["references"]) == 1 for o in gallery.objects.values()
    )
    gallery.verified(A, [1, 2, 3, 4])
    again = Gallery(gallery.path, ColorGrid())
    assert again.objects[A]["last_verified_identity_at"]
    assert again.objects[A]["last_known_position"]["bbox"] == [1, 2, 3, 4]


def test_known_unknown_swap_and_no_provider(gallery):
    async def case():
        p = IdentityPipeline(gallery, config(), cal(gallery), mode="baseline")
        rows = await p.step(scene(), BOXES, 0)
        assert [r["object_id"] for r in rows] == [A, B]
        assert all(
            isinstance(r["track_id"], int) and isinstance(r["object_id"], str)
            for r in rows
        )
        p.reset()
        rows = await p.step(scene(("blue", "red")), BOXES, 0)
        assert [r["object_id"] for r in rows] == [B, A]
        rows = await p.step(scene(("green", "green")), BOXES, 0.1)
        assert all(r["object_id"] is None for r in rows)
        assert not p.events

    run(case)


def test_uncalibrated_never_assigns_and_ambiguous_duplicates(gallery):
    async def case():
        p = IdentityPipeline(gallery, config(), mode="baseline")
        assert all(r["object_id"] is None for r in await p.step(scene(), BOXES, 0))
        p = IdentityPipeline(gallery, config(), cal(gallery), mode="baseline")
        rows = await p.step(scene(("red", "red")), BOXES, 0)
        assert all(
            r["object_id"] is None and r["reason"] == "duplicate_identity" for r in rows
        )
        gallery.features[B] = gallery.features[A]
        p.reset()
        rows = await p.step(scene(("red", "red")), BOXES, 0)
        assert all(r["object_id"] is None for r in rows)

    run(case)


def test_vlm_is_async_proposal_only_and_event_dedup(gallery):
    async def case():
        m = MockVLM(proposed, delay=0.03)
        p = IdentityPipeline(
            gallery,
            config(vlm_enabled=True, endpoint="http://local/v1", model="mock"),
            adapter=m,
        )
        rows = await p.step(scene(), BOXES, 0)
        assert (
            all(r["identity_state"] == "pending_verification" for r in rows)
            and len(m.calls) == 0
        )
        for i in range(1, 6):
            await p.step(scene(), BOXES, i / 100)
        await p.settle()
        rows = p.snapshot()
        assert all(
            r["object_id"] is None and r["vlm_proposal"]["status"] == "proposed"
            for r in rows
        )
        assert len(m.calls) == 1
        await p.step(scene(), BOXES, 0.1)
        await p.settle()
        assert len(m.calls) == 1
        r = p.snapshot()[0]
        assert r["vlm_proposal"]["object_id"] == A
        assert p.confirm(r["track_id"], r["generation"], A)
        assert p.snapshot()[0]["match_source"] == "human_confirmation"

    run(case)


def test_correlated_policy_can_accept_but_no_duplicate_ownership(gallery):
    async def case():
        p = IdentityPipeline(
            gallery,
            config(
                vlm_enabled=True,
                endpoint="http://local",
                model="mock",
                acceptance="corroborated",
            ),
            cal(gallery),
            MockVLM(proposed),
            mode="vlm",
        )
        await p.step(scene(), BOXES, 0)
        await p.settle()
        assert [r["object_id"] for r in p.snapshot()] == [A, B]
        assert all(r["match_source"] == "vlm_corroborated" for r in p.snapshot())
        assert not p.confirm(
            p.snapshot()[1]["track_id"], p.snapshot()[1]["generation"], A
        )

    run(case)


def test_stale_changed_crops_missing_tracks_and_session_reset(gallery):
    async def case():
        for action in ["crop", "missing", "reset"]:
            m = MockVLM(proposed, delay=0.03)
            p = IdentityPipeline(
                gallery,
                config(vlm_enabled=True, endpoint="http://local", model="mock"),
                adapter=m,
            )
            await p.step(scene(), BOXES, 0)
            await asyncio.sleep(0.005)
            if action == "crop":
                await p.step(scene(("blue", "red")), BOXES, 0.1)
            if action == "missing":
                await p.step(scene(), [], 0.1)
            if action == "reset":
                p.reset()
            await p.settle()
            assert all(
                r["object_id"] is None and r["vlm_proposal"] is None
                for r in p.snapshot()
            )
            assert p.counters["stale_result"] + p.counters["cancelled"] >= 1

    run(case)


def test_timeout_cooldown_retry_and_global_limits(gallery):
    async def case():
        now = [100.0]
        m = MockVLM(delay=0.05)
        cfg = config(
            vlm_enabled=True,
            endpoint="http://local",
            model="mock",
            timeout_s=0.01,
            cooldown_s=5,
            requests_per_minute=2,
            max_tracks_per_request=1,
            concurrency=1,
        )
        p = IdentityPipeline(gallery, cfg, adapter=m, clock=lambda: now[0])
        await p.step(scene(), BOXES, 0)
        await p.settle()
        assert p.counters["timeout"] == 1
        await p.step(scene(), BOXES, 0.1)
        await p.settle()
        assert p.counters["requests"] == 2  # other unresolved track
        now[0] += 6
        await p.step(scene(), BOXES, 0.2)
        await p.settle()
        assert p.counters["requests"] == 2  # global rate cap
        now[0] += 60
        await p.step(scene(), BOXES, 0.3)
        await p.settle()
        assert p.counters["requests"] == 3
        assert all(r["object_id"] is None for r in p.snapshot())

    run(case)


def test_multiple_simultaneous_requests_are_bounded(gallery):
    async def case():
        p = IdentityPipeline(
            gallery,
            config(
                vlm_enabled=True,
                endpoint="http://local",
                model="mock",
                max_tracks_per_request=1,
                concurrency=2,
            ),
            adapter=MockVLM(delay=0.03),
        )
        await p.step(scene(), BOXES, 0)
        await p.step(scene(), BOXES, 0.01)
        await p.step(scene(), BOXES, 0.02)
        assert len(p.tasks) == 2 and p.counters["requests"] == 2
        await p.settle()

    run(case)


def test_response_validator():
    req = {
        "observations": [{"track_id": 1}, {"track_id": 2}],
        "references": {A: [], B: []},
    }
    good = {
        "matches": [
            {
                "track_id": 1,
                "object_id": A,
                "status": "proposed",
                "evidence": "sticker",
            },
            {
                "track_id": 2,
                "object_id": None,
                "status": "unknown",
                "evidence": "unclear",
            },
        ]
    }
    assert len(validate(good, req)) == 2
    for raw in [
        "not JSON",
        "```json\n{}\n```",
        {"matches": []},
        {"matches": [dict(good["matches"][0], track_id=9), good["matches"][1]]},
        {
            "matches": [
                dict(good["matches"][0], object_id=str(uuid4())),
                good["matches"][1],
            ]
        },
        {"matches": [good["matches"][0], dict(good["matches"][0], track_id=2)]},
        {"matches": [dict(good["matches"][0], confidence=0.99), good["matches"][1]]},
        {"matches": [dict(good["matches"][0], track_id=True), good["matches"][1]]},
    ]:
        with pytest.raises(InvalidResponse):
            validate(raw, req)


def test_missing_config_and_bad_calibration(gallery, monkeypatch):
    with pytest.raises(ValueError):
        Config(vlm_enabled=True)
    with pytest.raises(ValueError):
        IdentityPipeline(gallery, Config())
    with pytest.raises(ValueError):
        IdentityPipeline(gallery, config(acceptance="corroborated"))
    with pytest.raises(ValueError):
        Config(timeout_s=float("nan"))
    monkeypatch.setenv("IDENTITY_EXPERIMENT_ENABLED", "true")
    assert Config.from_env().enabled


def test_invalid_response_falls_back_without_logging_payload(gallery):
    async def case():
        p = IdentityPipeline(
            gallery,
            config(vlm_enabled=True, endpoint="http://local", model="mock"),
            adapter=MockVLM("PRIVATE_SECRET invalid json"),
        )
        await p.step(scene(), BOXES, 0)
        await p.settle()
        assert p.counters["invalid_response"] == 1 and all(
            r["object_id"] is None for r in p.snapshot()
        )
        assert "PRIVATE_SECRET" not in json.dumps(p.events)

    run(case)


def test_transport_limits_images_and_validates_usage(gallery):
    import httpx

    async def case():
        def reply(request):
            body = json.loads(request.content)
            assert body["model"] == "test"
            content = body["messages"][0]["content"]
            assert not any("private note" in str(x) for x in content)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "matches": [
                                            {
                                                "track_id": 1,
                                                "object_id": None,
                                                "status": "unknown",
                                                "evidence": "unclear",
                                            }
                                        ]
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            )

        cfg = config(vlm_enabled=True, endpoint="http://local/v1", model="test")
        a = OpenAICompatible(cfg, httpx.MockTransport(reply))
        request = {
            "references": gallery.images,
            "observations": [
                {
                    "track_id": 1,
                    "generation": 0,
                    "reason": "new",
                    "previous_object_id": None,
                    "crop": scene(),
                }
            ],
        }
        result = await a.match(request)
        assert result["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}
        assert validate(result["response"], request)[0]["status"] == "unknown"

    run(case)


def test_overlap_and_old_response_cannot_restore_identity(gallery):
    async def case():
        cfg = config(vlm_enabled=True, endpoint="http://local", model="mock")
        p = IdentityPipeline(gallery, cfg, cal(gallery), MockVLM(proposed, delay=0.01))
        await p.step(scene(), BOXES, 0)
        rows = await p.step(scene(), [[0, 0, 30, 30], [5, 0, 35, 30]], 0.1)
        assert all(
            r["object_id"] is None and r["reason"] == "overlapping_tracks" for r in rows
        )
        await p.settle()
        assert all(r["object_id"] is None for r in p.snapshot())

    run(case)


def test_response_expiry_and_occupied_identity(gallery):
    async def case():
        now = [0.0]
        p = IdentityPipeline(
            gallery,
            config(vlm_enabled=True, endpoint="http://local", model="mock"),
            adapter=MockVLM(proposed, delay=0.02),
            clock=lambda: now[0],
        )
        await p.step(scene(), BOXES, 0)
        await asyncio.sleep(0.005)
        now[0] = 10
        await p.settle()
        assert p.counters["stale_result"] == 1
        p = IdentityPipeline(
            gallery,
            config(
                vlm_enabled=True,
                endpoint="http://local",
                model="mock",
                max_tracks_per_request=1,
            ),
            adapter=MockVLM(proposed, delay=0.02),
        )
        rows = await p.step(scene(), BOXES, 0)
        assert p.confirm(rows[1]["track_id"], rows[1]["generation"], A)
        await p.settle()
        assert p.counters["invalid_response"] == 1
        assert p.snapshot()[0]["object_id"] is None

    run(case)


def test_cancellation_before_dispatch_is_recorded_without_fake_latency(gallery):
    async def case():
        adapter = MockVLM()
        p = IdentityPipeline(
            gallery,
            config(vlm_enabled=True, endpoint="http://local", model="mock"),
            adapter=adapter,
        )
        await p.step(scene(), BOXES, 0)
        await p.close()
        assert not adapter.calls
        assert (
            len(p.events) == 1
            and p.events[0]["failure_category"] == "cancelled_before_dispatch"
        )
        assert p.events[0]["latency_ms"] is None

    run(case)
