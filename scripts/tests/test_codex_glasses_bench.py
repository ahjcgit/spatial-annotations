import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

spec=importlib.util.spec_from_file_location('codex_glasses_bench',Path(__file__).parents[1]/'codex_glasses_bench.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)


def test_timing_never_subtracts_host_from_device_clock():
    host={'handoffReadyNs':900_000_000_000,'submitReceivedNs':902_000_000_000,'commitObservedNs':903_000_000_000}
    device={'frameCallbackReceivedNs':1_000_000_000,'applyReceivedNs':3_000_000_000,'frameCommittedNs':3_016_000_000}
    result=bench.metrics(host,device)
    assert result['codex_assisted_review_turnaround_ms']==2000
    assert result['device_apply_to_frame_commit_ms']==16
    assert result['device_frame_to_frame_commit_ms']==2016
    assert result['isolated_model_inference_ms'] is None
    assert result['optical_display_latency_ms'] is None


def test_absent_commit_is_not_a_zero_latency():
    assert bench.metrics({}, {})['device_apply_to_frame_commit_ms'] is None


def test_duplicate_identity_rejected():
    label={'identity':'A','label':'Silver bottle','uncertain':False,'box':[0,0,100,100],'evidence':'Silver body'}
    with pytest.raises(ValidationError):
        bench.Submission(requestId='x',sourceSha256='a'*64,labels=[label,label],reasoning_summary='Two objects')


def test_resource_accounting_handles_spaces_in_process_name():
    # Fields 3..24; utime/stime are fields 14/15 and RSS is 24.
    fields=['0']*22;fields[0]='S';fields[11]='150';fields[12]='50';fields[21]='1000'
    parsed=bench.proc_values('42 (a process) '+' '.join(fields),100,4096)
    assert parsed=={'cpu_seconds':2.0,'rss_bytes':4096000}


def test_resource_summary_uses_cpu_delta_not_machine_core_count():
    rows=[{'hostMonotonicNs':0,'device':{'cpu_seconds':1,'rss_bytes':1048576}},
          {'hostMonotonicNs':2_000_000_000,'device':{'cpu_seconds':1.5,'rss_bytes':2097152}}]
    result=bench.resource_summary(rows)['device']
    assert result['mean_cpu_percent_one_core']==25
    assert result['peak_rss_mib']==2


def test_existing_evidence_is_not_overwritten(tmp_path):
    metadata = tmp_path / 'run-metadata.json'
    metadata.write_text('{"original": true}')
    with pytest.raises(ValueError, match='already contains evidence'):
        bench.Bench('unused-adb', 'unused-serial', tmp_path)
    assert metadata.read_text() == '{"original": true}'


def test_custom_enrollment_names_survive_setup(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(bench.Bench, "device", lambda *args: b"100")
    run = bench.Bench("unused", "unused", tmp_path, ("worn base", "scratched handle"))
    metadata = json.loads((tmp_path / "run-metadata.json").read_text())
    assert run.identities == metadata["operator_confirmed_identities"] == {
        "A": "worn base", "B": "scratched handle"
    }
