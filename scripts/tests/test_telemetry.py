"""Reporter correctness using unit fixtures, never included in measured presentation samples."""
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('summary',Path(__file__).parents[1]/'summarize_telemetry.py')
summary=importlib.util.module_from_spec(spec);spec.loader.exec_module(summary)


def test_summary_separates_simulation_negatives_and_camera_environments():
    rows=[dict(environment='synthetic',identification_method='offline_qr_replay',recognition_success=False,
               expected_marker=None,expectation_match=True,failure_category=None,total_latency_ms=2),
          dict(environment='synthetic',identification_method='offline_qr_replay',recognition_success=True,
               expected_marker='marker',expectation_match=True,failure_category=None,total_latency_ms=4),
          dict(environment='android_emulator',identification_method='simulated_lookup',recognition_success=None,
               backend_success=False,failure_category='network',total_latency_ms=10)]
    groups=summary.summarize(rows)
    assert len(groups)==2
    simulated,synthetic=groups
    assert 'recognition_success' not in simulated
    assert simulated['failures']=={'network':1}
    assert synthetic['recognition_success']['rate']==.5
    assert synthetic['expectation_match']['rate']==1
    assert synthetic['positive_target_success']=={'samples':1,'passed':1}
    assert synthetic['total_latency_ms']=={'samples':2,'mean':3,'median':3,'p95':None}


def test_p95_is_nearest_rank_only_when_twenty_samples_exist():
    rows=[dict(environment='unit',identification_method='unit',total_latency_ms=x) for x in range(1,21)]
    assert summary.summarize(rows)[0]['total_latency_ms']['p95']==19
    assert summary.summarize(rows[:-1])[0]['total_latency_ms']['p95'] is None
