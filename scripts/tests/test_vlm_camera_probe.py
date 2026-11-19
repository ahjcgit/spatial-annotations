import importlib.util
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

spec = importlib.util.spec_from_file_location("vlm_camera_probe", Path(__file__).parents[1] / "vlm_camera_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize("box", [[200, 0, 100, 100], [0, -1, 10, 10], [0, 0, 1001, 10], [False, 0, 10, 10]])
def test_rejects_invalid_box(box):
    with pytest.raises(ValidationError):
        probe.ObjectProposal(label="cup", box=box, evidence="visible handle", uncertain=False)


def test_rejects_identity_claim_field():
    with pytest.raises(ValidationError):
        probe.ObjectProposal(label="cup", box=[0, 0, 10, 10], evidence="handle", uncertain=False, object_id="alice-cup")


def test_stopped_camera_cannot_reuse_old_image():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"phase":"stopped", "image":"old frame"}))
    with httpx.Client(transport=transport) as client, pytest.raises(ValueError, match="not live"):
        probe.camera_snapshot(client, "http://camera")


def test_requires_new_frame(monkeypatch):
    packets = iter([
        {"phase":"no_match", "runId":"a", "frameId":4, "image":"data:image/jpeg;base64,b2xk"},
        {"phase":"no_match", "runId":"a", "frameId":4, "image":"data:image/jpeg;base64,b2xk"},
        {"phase":"no_match", "runId":"a", "frameId":5, "image":"data:image/jpeg;base64,bmV3"},
    ])
    monkeypatch.setattr(probe.time, "sleep", lambda _: None)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=next(packets)))
    with httpx.Client(transport=transport) as client:
        raw, metadata = probe.camera_snapshot(client, "http://camera")
    assert raw == b"new"
    assert metadata["frameId"] == 5


def test_capture_only_never_calls_model(tmp_path, monkeypatch):
    import json
    from PIL import Image
    source = tmp_path / "source.png"
    Image.new("RGB", (32, 32), "white").save(source)
    out = tmp_path / "review"
    monkeypatch.setattr("sys.argv", ["probe", "--image", str(source), "--out", str(out), "--capture-only"])
    def forbidden(*args, **kwargs):
        raise AssertionError("Capture-only mode must not call an inference endpoint")
    monkeypatch.setattr(httpx.Client, "post", forbidden)
    probe.main()
    result = json.loads((out / "result.json").read_text())
    assert result["status"] == "awaiting_codex_review"
    assert result["model"] is None
    assert not (out / "response.json").exists()
