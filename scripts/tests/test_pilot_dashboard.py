"""Use the real immutable archive to check derived results and evidence safeguards."""

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_pilot_dashboard import DEFAULT, build, build_data, clocks, sha


def test_archived_inventory_timings_and_relocated_references(tmp_path):
    data = build_data(DEFAULT, tmp_path)
    assert data["integrity"]["ok"]
    assert data["integrity"]["archive_files"] == 81
    assert data["inventory"] == {
        "completed": 6,
        "failed": 3,
        "qualitative": 4,
        "qualitative_retries": 1,
        "expiry_observed": 5,
    }
    assert len(data["trials"]) == 13
    assert len(data["relocated_references"]) == 4
    assert data["review_fraction"] == pytest.approx(0.8196981289198332)
    assert data["totals"]["host_capture_to_commit_observed_ms"][
        "median"
    ] == pytest.approx(13432.4098265)
    assert data["totals"]["host_submit_to_commit_observed_ms"][
        "median"
    ] == pytest.approx(184.3694015)
    assert all(s["p95"] is None for s in data["totals"].values())
    assert (
        next(t for t in data["trials"] if t["id"] == "large-text/trial-02")[
            "expiry_observed"
        ]
        is False
    )
    q = [t for t in data["trials"] if t["status"] == "review_only"]
    assert all(
        t["display"] is None
        and t["metrics"]["codex_assisted_review_turnaround_ms"] is None
        for t in q
    )


def test_clocks_never_mix_host_device_or_sensor():
    record = {
        "host": {
            "captureStartNs": 1_000_000,
            "handoffReadyNs": 2_000_000,
            "submitReceivedNs": 9_000_000,
            "commitObservedNs": 10_000_000,
        },
        "device": {
            "applyReceivedNs": 800_000_000,
            "frameCommittedNs": 802_000_000,
            "frameCallbackReceivedNs": 798_000_000,
            "sourceSensorTimestampNs": 7,
        },
    }
    values = clocks(record)
    assert values["host_capture_to_commit_observed_ms"] == 9
    assert values["device_apply_to_frame_commit_ms"] == 2
    assert values["device_frame_to_frame_commit_ms"] == 4
    assert clocks({})["host_capture_to_commit_observed_ms"] is None


@pytest.fixture
def archive(tmp_path):
    target = tmp_path / "archive"
    shutil.copytree(DEFAULT, target, ignore=shutil.ignore_patterns("dashboard"))
    return target


def test_missing_expected_image_is_reported_not_a_pass(archive, tmp_path):
    (archive / "large-text/trial-04/display.png").unlink()
    data = build_data(archive, tmp_path / "out")
    assert not data["integrity"]["ok"]
    assert any(
        not c["passed"] and c["name"] == "Completed trial evidence"
        for c in data["integrity"]["checks"]
    )


def test_tampered_derived_metrics_do_not_replace_raw_clocks(archive, tmp_path):
    path = archive / "large-text/trial-04/result.json"
    record = json.loads(path.read_text())
    record["metrics"]["host_capture_to_commit_observed_ms"] = 1
    path.write_text(json.dumps(record))
    data = build_data(archive, tmp_path / "out")
    assert not data["integrity"]["ok"]
    trial = next(t for t in data["trials"] if t["id"] == "large-text/trial-04")
    assert trial["metrics"]["host_capture_to_commit_observed_ms"] == pytest.approx(
        10187.213285
    )
    assert any(
        c["name"] == "Raw clock recomputation" and not c["passed"]
        for c in data["integrity"]["checks"]
    )


def test_static_build_preserves_original_bytes_and_includes_failures(archive):
    manifest = json.loads((archive / "manifest.json").read_text())
    data = build(archive)
    assert data["integrity"]["ok"]
    assert all(sha(archive / p) == digest for p, digest in manifest["files"].items())
    assert (
        (archive / "dashboard/data.js").read_text().startswith("window.PILOT_DATA = ")
    )
    assert (
        "setup-diagnostics/trial-01,failed"
        in (archive / "dashboard/trials.csv").read_text()
    )
    assert "Referenced, absent" in (archive / "dashboard/index.html").read_text()


def test_cannot_overwrite_archived_report(archive):
    with pytest.raises(ValueError, match="overwrite archived"):
        build(archive, archive / "report")
