"""Read-only study viewer. Serves only enumerated frames and sanitized run results."""

import json
import socket
from pathlib import Path

from app.identity.dataset import Dataset, contained
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[1]


def create_app(dataset_path, results, backend=None, backend_transport=None):
    dataset = Dataset(dataset_path)
    fingerprint = dataset.fingerprint()
    root = Path(results).resolve()
    runs = {}
    for path in sorted(root.glob("*/summary.json")):
        summary = json.loads(path.read_text())
        if summary.get("version") != 2 or summary["dataset_sha256"] != fingerprint:
            continue
        frames = [
            json.loads(line)
            for line in (path.parent / "frames.jsonl").read_text().splitlines()
        ]
        events = [
            json.loads(line)
            for line in (path.parent / "vlm-events.jsonl").read_text().splitlines()
        ]
        runs[path.parent.name] = {
            "summary": summary,
            "frames": {(r["sequence"], r["frame_index"]): r for r in frames},
            "events": events,
        }
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.get("/")
    def home():
        return FileResponse(ROOT / "demo/identity-review.html")

    @app.get("/identity-review.js")
    def js():
        return FileResponse(ROOT / "demo/identity-review.js")

    @app.get("/identity-review.css")
    def css():
        return FileResponse(ROOT / "demo/identity-review.css")

    @app.get("/api/study")
    def study():
        return {
            "evidence_kind": dataset.data["evidence_kind"],
            "annotations_enabled": backend is not None,
            "sequences": [
                {
                    "index": i,
                    "id": s["id"],
                    "condition": s["condition"],
                    "frames": len(s["frames"]),
                }
                for i, s in enumerate(dataset.data["sequences"])
            ],
            "runs": [
                {
                    "id": key,
                    **{
                        k: r["summary"][k]
                        for k in (
                            "method",
                            "pass",
                            "protocol",
                            "trial",
                            "provider_kind",
                        )
                    },
                }
                for key, r in runs.items()
            ],
        }

    def frame_at(sequence, index):
        if not 0 <= sequence < len(dataset.data["sequences"]):
            raise HTTPException(404, "Unknown sequence")
        s = dataset.data["sequences"][sequence]
        if not 0 <= index < len(s["frames"]):
            raise HTTPException(404, "Unknown frame")
        return s, s["frames"][index]

    @app.get("/api/frame/{sequence}/{index}")
    def frame(sequence: int, index: int, run: str, evaluation: bool = False):
        s, f = frame_at(sequence, index)
        if run not in runs:
            raise HTTPException(404, "Unknown run")
        selected = runs[run]
        row = selected["frames"].get((s["id"], index))
        if row is None:
            raise HTTPException(404, "Run has no result for this frame")
        events = [
            e
            for e in selected["events"]
            if e.get("sequence") == s["id"]
            and e.get("available_from_frame", len(s["frames"])) <= index
        ]
        result = {
            "image_url": f"/api/image/{sequence}/{index}",
            "timestamp_s": f["timestamp_s"],
            "next_delta_s": s["frames"][index + 1]["timestamp_s"] - f["timestamp_s"]
            if index + 1 < len(s["frames"])
            else None,
            "predictions": row["predictions"],
            "selected": row["selected"],
            "events": events,
            "replay_processing_ms": row["replay_processing_ms"],
        }
        if evaluation:
            result["ground_truth"] = f.get("ground_truth")
        return result

    @app.post("/api/session")
    async def login(request: Request):
        if not backend:
            raise HTTPException(404, "Annotation backend not configured")
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Sign in from this viewer")
        from app.schemas import Credentials
        from pydantic import ValidationError

        try:
            credentials = Credentials.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(422, "Invalid credentials format") from None
        import httpx

        try:
            async with httpx.AsyncClient(
                base_url=backend,
                transport=backend_transport,
                timeout=10,
                trust_env=False,
            ) as client:
                response = await client.post(
                    "/auth/login", json=credentials.model_dump()
                )
                if response.status_code != 200:
                    raise HTTPException(401, "Sign-in failed")
                return {"access_token": response.json()["access_token"]}
        except httpx.HTTPError:
            raise HTTPException(502, "Annotation backend unavailable") from None

    @app.get("/api/notes/{sequence}/{index}/{track}")
    async def notes(sequence: int, index: int, track: int, run: str, request: Request):
        s, _ = frame_at(sequence, index)
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Sign in to retrieve annotations")
        if not backend or run not in runs:
            raise HTTPException(404, "Annotations unavailable")
        rows = runs[run]["frames"].get((s["id"], index), {}).get("predictions", [])
        row = next(
            (
                r
                for r in rows
                if r["track_id"] == track
                and r["identity_state"] == "matched"
                and r["object_id"]
            ),
            None,
        )
        if row is None:
            raise HTTPException(404, "Track has no accepted identity")
        import httpx

        try:
            async with httpx.AsyncClient(
                base_url=backend,
                transport=backend_transport,
                timeout=10,
                trust_env=False,
            ) as client:
                headers = {"Authorization": authorization}
                me = await client.get("/users/me", headers=headers)
                if me.status_code != 200:
                    raise HTTPException(401, "Session expired; sign in again")
                response = await client.get(
                    f"/objects/{row['object_id']}/annotations",
                    params={"limit": 100},
                    headers=headers,
                )
                if response.status_code != 200:
                    raise HTTPException(
                        response.status_code, "Annotation retrieval failed"
                    )
                values = response.json()
                if any(n.get("object_id") != row["object_id"] for n in values):
                    raise HTTPException(502, "Invalid annotation response")
                # Read permissions remain exclusively the existing backend's decision.
                return {
                    "notes": [
                        {k: n.get(k) for k in ("content", "visibility", "author_id")}
                        for n in values
                    ],
                    "limit": 100,
                }
        except httpx.HTTPError:
            raise HTTPException(502, "Annotation backend unavailable") from None

    @app.get("/api/image/{sequence}/{index}")
    def image(sequence: int, index: int):
        _, f = frame_at(sequence, index)
        return FileResponse(contained(dataset.root, f["image"]))

    return app


def serve(dataset, results, port, backend=None):
    if port == 5173:
        raise ValueError("Port 5173 is reserved")
    with socket.socket() as probe:
        try:
            probe.bind(("0.0.0.0", port))
        except OSError as exc:
            raise ValueError("Port occupied; choose another --port") from exc
    import uvicorn

    print(
        f"Viewer: http://<computer-LAN-IP>:{port} (read-only; configured dataset only)",
        flush=True,
    )
    uvicorn.run(create_app(dataset, results, backend), host="0.0.0.0", port=port)
