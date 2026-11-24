import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
from app.identity.config import Config
from judge import data
from judge.collect import collect
from judge.methods import Inputs, JudgeAPI, validate
from judge.run import apply, run
from judge.score import analyze


@pytest.fixture
def study(tmp_path):
    d = tmp_path / "study"
    data.archive(d)
    return d


def args(study, out, **changes):
    defaults = dict(
        study=study,
        out=out,
        provider="mock",
        arms=["direct", "adaptive", "fixed-look"],
        variants=["genuine"],
        cases=["p03"],
        repeats=1,
        seed=4,
        max_calls=20,
        calibration=None,
        cache=None,
    )
    return SimpleNamespace(**(defaults | changes))


def test_collection_and_seal(tmp_path):
    d = tmp_path / "field"
    data.init(d)
    cases = data.read(d / "observations.json")["cases"]
    assert len(cases) == 90 and len({c["take"] for c in cases}) == 30
    source = tmp_path / "frame.png"
    Image.new("RGB", (48, 48), "red").save(source)
    a = SimpleNamespace(
        study=d,
        case=cases[0]["id"],
        time_ms=0,
        deadline_ms=1000,
        image=source,
        video=None,
        box=[0, 0, 30, 40],
        continuous=False,
        prior=None,
        second=None,
        body="C",
        identifiable=True,
    )
    collect(a)
    assert data.read(d / "truth.json")[a.case]["body"] == "C"
    assert "body" not in data.read(d / "observations.json")["cases"][0]
    with pytest.raises(FileExistsError):
        collect(a)
    with pytest.raises(ValueError):
        data.seal(d)


def test_blinding_and_noncausal_input(study):
    public = data.read(study / "observations.json")
    c = public["cases"][2]
    x = Inputs(study, public, Config())
    genuine = x.render(c, "review", "genuine", "opaque", 512)
    flip = x.render(c, "review", "flipped", "opaque", 512)
    assert genuine["jpeg"] == flip["jpeg"] and genuine["hint"] != flip["hint"]
    assert (
        "tracker_candidate"
        not in x.render(c, "direct", "genuine", "opaque", 512)["prompt"]
    )
    for secret in [c["image"], c["id"], c["take"], "occlusion", "flipped"]:
        assert secret not in flip["prompt"]
    c["prior"] = public["cases"][3]["id"]
    data.save(study / "observations.json", public)
    with pytest.raises(ValueError, match="Noncausal"):
        data.seal(study)


def test_calibration_and_routine_gate(study, tmp_path):
    d = data.read(study / "observations.json")
    d["split"] = "development"
    data.save(study / "observations.json", d)
    data.seal(study)
    # Even a valid development file cannot authorize disclosure on reused captures.
    f = tmp_path / "gates.json"
    data.save(
        f,
        {
            "synthetic_only": False,
            "development_image_sha256": [data.sha(study / d["cases"][0]["image"])],
        },
    )
    with pytest.raises(ValueError, match="independent"):
        asyncio.run(run(args(study, tmp_path / "out", calibration=f)))
    only = d["cases"][:2]
    only[1].update(image=only[0]["image"], box=only[0]["box"], gap=False, time_ms=200)

    class Gate:
        def accept(self, scores, alias):
            return True

    x = Inputs(study, dict(d, cases=only), Config(), Gate())
    assert not x.local[only[0]["id"]]["routine"] and x.local[only[1]["id"]]["routine"]


def test_model_validation_and_deadlines():
    base = dict(
        request_id="r",
        alias="A",
        action="show",
        support="body",
        cue="worn base",
        source="current",
    )
    assert validate(base, "r", False) == base
    for bad in [
        dict(base, request_id="old"),
        dict(base, alias="invented"),
        dict(base, support="part"),
        dict(base, source="both"),
        dict(base, hidden="truth"),
        dict(base, cue=" "),
    ]:
        with pytest.raises(ValueError):
            validate(bad, "r", False)
    with pytest.raises(ValueError):
        validate(dict(base, support="continuity", source="both"), "r", True, False)
    assert apply(base, 100, 100) == {"action": "clear", "alias": None, "status": "late"}


def test_followups_budget_and_truth_separation(study, tmp_path):
    d = data.read(study / "observations.json")
    d["cases"][2]["second"] = "p04"
    data.save(study / "observations.json", d)
    data.seal(study)
    original = (study / "truth.json").read_bytes()
    (study / "truth.json").unlink()
    out = tmp_path / "out"
    asyncio.run(run(args(study, out)))
    rows = [json.loads(s) for s in (out / "events.jsonl").read_text().splitlines()]
    assert {r["arm"] for r in rows if "second_look" in r} == {"fixed-look", "adaptive"}
    assert all(r["case"] == "p03" and r["applied"]["alias"] is None for r in rows)
    assert all(r["second_look"]["case"] == "p04" for r in rows if "second_look" in r)
    (study / "truth.json").write_bytes(original)
    report = tmp_path / "report"
    analyze(SimpleNamespace(study=study, run=out, out=report, wearer=None))
    assert (report / "summary.json").is_file()
    limited = tmp_path / "limited"
    asyncio.run(run(args(study, limited, max_calls=1)))
    events = [
        json.loads(s) for s in (limited / "events.jsonl").read_text().splitlines()
    ]
    assert (
        sum(r["calls"] + r.get("second_look", {}).get("calls", 0) for r in events) == 1
    )
    (study / "truth.json").write_text("{}")
    with pytest.raises(ValueError, match="truth"):
        analyze(
            SimpleNamespace(
                study=study, run=out, out=tmp_path / "tampered", wearer=None
            )
        )


def test_stateless_http_and_usage():
    cfg = Config(vlm_enabled=True, endpoint="http://local.test/v1", model="vision-test")

    def serve(request):
        data = json.loads(request.content)
        assert len(data["messages"]) == 1 and data["model"] == "vision-test"
        assert data["messages"][0]["content"][1]["image_url"]["url"].startswith(
            "data:image/jpeg;base64,"
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 5,
                    "total_tokens": 16,
                },
            },
        )

    result = asyncio.run(
        JudgeAPI(cfg, httpx.MockTransport(serve)).match(
            {"prompt": "blinded", "jpeg": b"x"}
        )
    )
    assert result["usage"]["total_tokens"] == 16


def test_gap_and_duplicate_budget(study):
    data_set = data.read(study / "observations.json")
    pre, c = data_set["cases"][:2]
    c.update(time_ms=400, trail=[{"time_ms": 200, "image": pre["image"]}], gap=False)
    data.save(study / "observations.json", data_set)
    data.seal(study)
    x = Inputs(study, data_set, Config())
    views = {
        a: x.render(c, a, "genuine", "r", 400) for a in ("gap", "temporal", "duplicate")
    }
    import io

    assert views["temporal"]["continuity"] and not views["gap"]["continuity"]
    assert (
        Image.open(io.BytesIO(views["temporal"]["jpeg"])).size
        == Image.open(io.BytesIO(views["duplicate"]["jpeg"])).size
    )
    assert (
        Image.open(io.BytesIO(views["temporal"]["jpeg"])).width
        > Image.open(io.BytesIO(views["gap"]["jpeg"])).width
    )


def test_wearer_observations_and_detector_miss(study, tmp_path):
    from judge.score import wearer_rows

    d = data.read(study / "observations.json")
    d["cases"][1]["deadline_ms"] = 5000
    data.save(study / "observations.json", d)
    data.seal(study)
    cache = tmp_path / "cache.json"
    data.save(
        cache,
        {
            "seal": data.read(study / "seal.json")["observations"],
            "label": "bottle",
            "frames": {
                x["image"]: {"detections": [], "total_ms": 3} for x in d["cases"]
            },
        },
    )
    out = tmp_path / "out"
    asyncio.run(run(args(study, out, cases=["p02"], arms=["direct"], cache=cache)))
    event = json.loads((out / "events.jsonl").read_text())
    assert event["error"] == "detector_miss" and event["calls"] == 0
    rid = event["id"]
    csv = tmp_path / "wearer.csv"
    csv.write_text(
        f"request_id,capture_to_commit_ms,capture_to_selection_ms,displayed_alias,selection\n{rid},4000,5100,B,B\n"
    )
    folder = tmp_path / "report"
    analyze(SimpleNamespace(study=study, run=out, out=folder, wearer=csv))
    assert data.read(folder / "summary.json")["groups"][0][
        "observed_wearer_correct_on_time"
    ] == {"measured": 1, "correct": 0}
    csv.write_text(csv.read_text().replace("5100", "3999"))
    with pytest.raises(ValueError, match="precede"):
        wearer_rows(csv, {rid})


def test_separate_development_calibration(tmp_path):
    from judge.collect import calibrate

    root = tmp_path / "dev"
    public = data.blank(root)
    public["split"] = "development"
    public["references"] = {}
    truth = {}
    for i, (alias, color) in enumerate([("A", "red"), ("B", "blue"), ("C", "green")]):
        name = f"images/{i}.png"
        Image.new("RGB", (32, 32), color).save(root / name)
        if alias in "AB":
            ref = f"refs/{alias}.png"
            Image.new("RGB", (20, 20), color).save(root / ref)
            public["references"][alias] = [ref]
        public["cases"].append(
            dict(
                id=alias,
                take="dev",
                time_ms=i * 100,
                image=name,
                box=[0, 0, 32, 32],
                gap=True,
            )
        )
        truth[alias] = dict(condition="practice", body=alias, identifiable=True)
    data.save(root / "observations.json", public)
    data.save(root / "truth.json", truth)
    data.seal(root)
    gates = tmp_path / "gates.json"
    calibrate(root, gates)
    assert data.read(gates)["appearance_margin"] > 0
