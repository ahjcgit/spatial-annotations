"""Actual annotation API permissions behind the optional read-only study viewer."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from app.identity.dataset import Dataset
from identity_suite import fixture
from identity_viewer import create_app


def test_viewer_notes_require_login_and_accepted_identity(client, users, tmp_path):
    source = tmp_path / "data"
    fixture(SimpleNamespace(out=source))
    dataset = Dataset(source / "dataset.json")
    obj = client.post(
        "/objects",
        headers=users["alice"]["headers"],
        json={"name": "Laptop A", "marker_id": str(uuid4())},
    ).json()
    for visibility in ("public", "private"):
        client.post(
            "/annotations",
            headers=users["alice"]["headers"],
            json={
                "object_id": obj["id"],
                "visibility": visibility,
                "content": visibility + " test note",
            },
        )
    root = tmp_path / "results" / "H1"
    root.mkdir(parents=True)
    summary = {
        "version": 2,
        "dataset_sha256": dataset.fingerprint(),
        "method": "H1",
        "pass": "A",
        "protocol": "events",
        "trial": 1,
        "provider_kind": "disabled",
    }
    (root / "summary.json").write_text(json.dumps(summary))
    (root / "vlm-events.jsonl").write_text("")
    frames = [
        {
            "sequence": "C1-fixture",
            "frame_index": i,
            "selected": True,
            "replay_processing_ms": 1,
            "predictions": [
                {
                    "track_id": 1,
                    "object_id": obj["id"] if i == 0 else None,
                    "identity_state": "matched" if i == 0 else "unknown",
                }
            ],
        }
        for i in (0, 1)
    ]
    (root / "frames.jsonl").write_text("".join(json.dumps(f) + "\n" for f in frames))
    app = create_app(
        dataset.path,
        root.parent,
        backend="http://backend",
        backend_transport=httpx.ASGITransport(app=client.app),
    )
    with TestClient(app) as viewer:
        route = "/api/notes/0/0/1?run=H1"
        assert viewer.get(route).status_code == 401
        alice = viewer.get(route, headers=users["alice"]["headers"]).json()["notes"]
        bob = viewer.get(route, headers=users["bob"]["headers"]).json()["notes"]
        assert len(alice) == 2 and [n["visibility"] for n in bob] == ["public"]
        assert (
            viewer.get(
                "/api/notes/0/1/1?run=H1", headers=users["alice"]["headers"]
            ).status_code
            == 404
        )
        assert (
            viewer.get(route, headers={"Authorization": "Bearer expired"}).status_code
            == 401
        )
        credentials = {"username": "alice", "password": "correct-horse-test"}
        assert viewer.post("/api/session", json=credentials).status_code == 403
        assert (
            viewer.post(
                "/api/session",
                headers={"Origin": "http://testserver"},
                json=credentials,
            ).status_code
            == 200
        )
        packet = viewer.get("/api/frame/0/0?run=H1").json()
        assert "private test note" not in json.dumps(packet)
        assert (
            viewer.get(route, headers=users["alice"]["headers"]).headers[
                "cache-control"
            ]
            == "no-store"
        )
