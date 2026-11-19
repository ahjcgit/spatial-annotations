import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('analyze_codex_bench', Path(__file__).parents[1] / 'analyze_codex_bench.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def sample(seconds, phase, cpu):
    return {'hostMonotonicNs': int(seconds * 1e9), 'phase': phase,
            'device': {'cpu_seconds': cpu, 'rss_bytes': 1048576}}


def test_phase_accounting_excludes_transition_interval():
    samples = [sample(0, 'delivery', 0), sample(1, 'display_hold', 0.8),
               sample(3, 'display_hold', 0.9)]
    rows = {r['phase']: r for r in analysis.phase_resources(samples)}
    assert rows['delivery']['cpu_seconds'] is None  # Sub-sampling-duration stage is unmeasured.
    assert rows['display_hold']['cpu_seconds'] == pytest.approx(0.1)
    assert rows['display_hold']['observed_interval_s'] == 2
    assert rows['display_hold']['mean_cpu_percent_one_core'] == pytest.approx(5)


def test_missing_process_sample_does_not_bridge_cpu_interval():
    samples = [sample(0, 'display_hold', 0),
               {'hostMonotonicNs': 1_000_000_000, 'phase': 'display_hold'},
               sample(2, 'display_hold', 1)]
    assert analysis.phase_resources(samples)[0]['cpu_seconds'] is None
