"""Verify the localhost dashboard cannot be used for cross-origin device control."""
import importlib.util
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location('present_demo', Path(__file__).parents[1] / 'present_demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_control_requires_same_origin_and_allowed_command(monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, b'')
    monkeypatch.setattr(demo.subprocess, 'run', run)
    client = TestClient(demo.create_app('adb', 'chosen-device', 'org.spatial.annotations.branchdemo'))
    assert client.post('/api/action/run', headers={'origin': 'https://elsewhere.example'}).status_code == 403
    assert client.post('/api/action/run').status_code == 403
    assert client.post('/api/action/uninstall', headers={'origin': 'http://testserver'}).status_code == 404
    assert not calls
    assert client.post('/api/action/mug-a', headers={'origin': 'http://testserver'}).status_code == 200
    assert len(calls) == 1 and calls[0][:3] == ['adb', '-s', 'chosen-device']
    assert calls[0][-2:] == ['command', 'mug-a']


def test_disconnected_device_does_not_report_success(monkeypatch):
    def offline(*args, **kwargs):
        raise subprocess.TimeoutExpired('adb', 12)
    monkeypatch.setattr(demo.subprocess, 'run', offline)
    client = TestClient(demo.create_app('adb', 'chosen-device', 'org.spatial.annotations.branchdemo'))
    assert client.get('/api/status').json()['deviceConnected'] is False
    assert client.get('/api/frame').status_code == 404
    assert client.post('/api/action/run', headers={'origin': 'http://testserver'}).status_code == 503
