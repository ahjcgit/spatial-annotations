"""Identity resolution remains separate from annotation authorization."""

import asyncio
from uuid import uuid4

import pytest

pytest.importorskip("numpy")
import httpx
from app.identity.annotations import AnnotationClient
from app.identity.appearance import Calibration, ColorGrid
from app.identity.config import Config
from app.identity.controller import IdentityPipeline
from app.identity.gallery import Gallery, register
from app.identity.vlm import MockVLM
from PIL import Image


def setup(client, users, tmp_path):
    ids = []
    path = tmp_path / "gallery.json"
    for color in ("red", "blue"):
        obj = client.post(
            "/objects",
            headers=users["alice"]["headers"],
            json={"marker_id": str(uuid4()), "name": "Laptop " + color},
        ).json()
        ids.append(obj["id"])
        im = tmp_path / (color + ".png")
        Image.new("RGB", (30, 30), color).save(im)
        register(path, obj, [im])
        assert (
            client.post(
                "/annotations",
                headers=users["alice"]["headers"],
                json={
                    "object_id": obj["id"],
                    "visibility": "private",
                    "content": color + " PRIVATE",
                },
            ).status_code
            == 201
        )
    g = Gallery(path, ColorGrid())
    c = Calibration(
        {
            "embedding_model": g.encoder.name,
            "development_set": "synthetic test only",
            "appearance_min": 0.98,
            "appearance_margin": 0.1,
        },
        g.encoder.name,
    )
    return IdentityPipeline(g, Config(enabled=True), c), ids


def test_resolved_identity_permissions_and_revocation(client, users, tmp_path):
    async def case():
        p, ids = setup(client, users, tmp_path)
        group = client.post(
            "/groups", headers=users["alice"]["headers"], json={"name": "Lab"}
        ).json()
        client.post(
            f"/groups/{group['id']}/members",
            headers=users["alice"]["headers"],
            json={"username": "bob"},
        )
        client.post(
            "/annotations",
            headers=users["alice"]["headers"],
            json={
                "object_id": ids[0],
                "visibility": "group",
                "group_id": group["id"],
                "content": "GROUP ONLY",
            },
        )
        api = AnnotationClient(
            "http://test", p, transport=httpx.ASGITransport(app=client.app)
        )
        api.set_token(users["alice"]["headers"]["Authorization"].split()[1])
        rows = await p.step(Image.new("RGB", (30, 30), "red"), [[0, 0, 30, 30]], 0)
        notes = await api.retrieve(rows[0])
        assert len(notes) == 2 and all(n["object_id"] == ids[0] for n in notes)
        private = next(n for n in notes if n["visibility"] == "private")
        api.set_token(users["bob"]["headers"]["Authorization"].split()[1])
        assert p.snapshot() == []
        rows = await p.step(Image.new("RGB", (30, 30), "red"), [[0, 0, 30, 30]], 0)
        assert [n["content"] for n in await api.retrieve(rows[0])] == ["GROUP ONLY"]
        assert (
            client.get(
                "/annotations/" + private["id"], headers=users["bob"]["headers"]
            ).status_code
            == 404
        )
        client.delete(
            f"/groups/{group['id']}/members/{users['bob']['id']}",
            headers=users["alice"]["headers"],
        )
        assert await api.retrieve(rows[0]) == []
        api.set_token("expired")
        rows = await p.step(Image.new("RGB", (30, 30), "red"), [[0, 0, 30, 30]], 0)
        with pytest.raises(httpx.HTTPStatusError):
            await api.retrieve(rows[0])
        assert api._token is None and p.snapshot() == []

    asyncio.run(case())


def test_switch_user_discards_pending_notes_and_reasoning(client, users, tmp_path):
    async def case():
        p, ids = setup(client, users, tmp_path)
        started = asyncio.Event()
        release = asyncio.Event()

        async def transport(req):
            if req.url.path == "/users/me":
                return httpx.Response(200, json={"id": "alice"})
            started.set()
            await release.wait()
            return httpx.Response(
                200, json=[{"object_id": ids[0], "content": "ALICE PRIVATE"}]
            )

        api = AnnotationClient("http://test", p, httpx.MockTransport(transport))
        api.set_token("alice")
        row = (await p.step(Image.new("RGB", (30, 30), "red"), [[0, 0, 30, 30]], 0))[0]
        task = asyncio.create_task(api.retrieve(row))
        await started.wait()
        api.set_token("bob")
        release.set()
        assert await task == []
        api.transport = httpx.MockTransport(
            lambda _: pytest.fail("Unknown must not issue HTTP")
        )
        row = (await p.step(Image.new("RGB", (30, 30), "green"), [[0, 0, 30, 30]], 0))[
            0
        ]
        assert await api.retrieve(row) == []
        p.config = Config(
            enabled=True, vlm_enabled=True, endpoint="http://local", model="mock"
        )
        p.adapter = MockVLM(delay=0.04)
        await p.step(Image.new("RGB", (30, 30), "green"), [[0, 0, 30, 30]], 0.1)
        await asyncio.sleep(0.005)
        api.set_token("carol")
        await p.settle()
        assert p.snapshot() == [] and p.counters["cancelled"] == 1

    asyncio.run(case())


def test_registration_cli_uses_existing_object_schema(
    client, users, tmp_path, monkeypatch
):
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from identity_experiment import register_cli

    real_client = httpx.Client

    def route(req):
        return client.request(
            req.method, str(req.url), content=req.content, headers=req.headers
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: real_client(**kw, transport=httpx.MockTransport(route)),
    )
    monkeypatch.setenv("IDENTITY_EXPERIMENT_ENABLED", "true")
    monkeypatch.setenv(
        "IDENTITY_API_TOKEN", users["alice"]["headers"]["Authorization"].split()[1]
    )
    image = tmp_path / "reference.png"
    Image.new("RGB", (32, 32), "red").save(image)
    gallery = tmp_path / "gallery.json"
    args = SimpleNamespace(
        backend="http://testserver",
        object_id=None,
        name="Laptop A",
        gallery=gallery,
        images=[image],
    )
    register_cli(args)
    g = Gallery(gallery, ColorGrid())
    oid = next(iter(g.objects))
    obj = client.get("/objects/" + oid).json()
    assert (
        obj["name"] == "Laptop A"
        and obj["spatial_metadata"]["detection_label"] == "laptop"
    )
    args.object_id = oid
    register_cli(args)
    assert len(Gallery(gallery, ColorGrid()).objects) == 1


def test_vlm_accepted_identity_still_uses_backend_authorization(
    client, users, tmp_path
):
    async def case():
        p, ids = setup(client, users, tmp_path)
        p.config = Config(
            enabled=True,
            vlm_enabled=True,
            endpoint="http://mock",
            model="mock",
            acceptance="corroborated",
        )
        p.calibration = Calibration(
            {
                "embedding_model": p.gallery.encoder.name,
                "development_set": "synthetic integration only",
                "appearance_min": 0.999,
                "appearance_margin": 0.1,
                "vlm_min": 0.9,
                "vlm_margin": 0.05,
                "vlm_development_set": "synthetic integration only",
            },
            p.gallery.encoder.name,
        )

        def answer(request):
            return {
                "matches": [
                    {
                        "track_id": o["track_id"],
                        "object_id": ids[0],
                        "status": "proposed",
                        "evidence": "mock",
                    }
                    for o in request["observations"]
                ]
            }

        p.adapter = MockVLM(answer)
        api = AnnotationClient("http://test", p, httpx.ASGITransport(app=client.app))
        for user, expected_count in [("alice", 1), ("bob", 0)]:
            api.set_token(users[user]["headers"]["Authorization"].split()[1])
            rows = await p.step(
                Image.new("RGB", (30, 30), (255, 60, 60)), [[0, 0, 30, 30]], 0
            )
            assert rows[0]["object_id"] is None
            await p.settle()
            row = p.snapshot()[0]
            assert (
                row["object_id"] == ids[0] and row["match_source"] == "vlm_corroborated"
            )
            assert len(await api.retrieve(row)) == expected_count

    asyncio.run(case())


def test_annotation_network_failure_then_retry(client, users, tmp_path):
    async def case():
        p, ids = setup(client, users, tmp_path)
        calls = 0

        def transport(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("offline", request=request)
            if request.url.path == "/users/me":
                return httpx.Response(200, json={"id": "alice"})
            return httpx.Response(
                200, json=[{"object_id": ids[0], "content": "authorized mock note"}]
            )

        api = AnnotationClient("http://test", p, httpx.MockTransport(transport))
        api.set_token("test")
        row = (await p.step(Image.new("RGB", (30, 30), "red"), [[0, 0, 30, 30]], 0))[0]
        with pytest.raises(httpx.ConnectError):
            await api.retrieve(row)
        assert len(await api.retrieve(row)) == 1

    asyncio.run(case())
