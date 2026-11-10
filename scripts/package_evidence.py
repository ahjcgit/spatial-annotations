#!/usr/bin/env python3
"""Copy an explicit allowlist of actual evidence; never package credentials, databases or tokens."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
# Missing optional evidence is reported rather than fabricated.
SOURCES={
 'browser-pagination-results.json':'artifacts/browser-pagination/results.json',
 'model-readiness-after-restart.json':'artifacts/readme-demo/vision-after-restart.json',
 'step-by-step-readme.md':'README.md',
 'browser-model-alice.png':'artifacts/readme-followup/browser-final/alice-model.png',
 'browser-model-bob.png':'artifacts/readme-followup/browser-final/bob-model.png',
 'browser-virtual-camera.png':'artifacts/readme-followup/browser-final/virtual-camera-model.png',
 'browser-model-test-results.json':'artifacts/readme-followup/browser-final/results.json',
 'integrated-model-demo.log':'artifacts/readme-followup/demo-reuse.log',
 'demo-with-bob-and-model.mp4':'artifacts/vision/demo-with-bob-and-model.mp4',
 'alice-bob-demo.mp4':'artifacts/sharing-video/alice-bob-demo.mp4',
 'bob-android.png':'artifacts/sharing-video/02-bob.png',
 'bob-revoked-android.png':'artifacts/sharing-video/03-bob-revoked.png',
 'model-demo.mp4':'artifacts/vision/emulator-final/model-demo.mp4',
 'model-mug-a.png':'artifacts/vision/emulator-final/Mug-A.png',
 'model-camera-results.json':'artifacts/vision/emulator-final/results.json',
 'model-camera-logs.jsonl':'artifacts/vision/emulator-final/model-log.txt',
 'model-backend-tests.txt':'artifacts/vision/backend-tests.txt',
 'model-android-tests.log':'artifacts/vision/final-android.log',
 'model-apk-sha256.txt':'artifacts/vision/apk.sha256',
 'model-setup.md':'docs/MODEL_DETECTION.md',
 'environment.json':'artifacts/environment.json',
 'implementation-status.md':'docs/IMPLEMENTATION_STATUS.md',
 'backend-tests.log':'artifacts/backend-final.log',
 'android-tests-lint-build.log':'artifacts/android-final.log',
 'reporter-tests.log':'artifacts/script-tests.log',
 'reproducible-demo.log':'artifacts/repro-run.log',
 'http-and-replay-summary.json':'artifacts/repro/summary.json',
 'camera-benchmark-summary.json':'artifacts/emulator-final/summary.json',
 'camera-benchmark.jsonl':'artifacts/emulator-final/telemetry.jsonl',
 'camera-benchmark-results.json':'artifacts/emulator-final/results.json',
 'final-apk-camera-results.json':'artifacts/apk-regression/results.json',
 'final-apk-camera.log':'artifacts/apk-regression.log',
 'final-apk-sha256.txt':'artifacts/final-apk.sha256',
 'companion-android.log':'artifacts/companion-final.log',
 'manual-android.log':'artifacts/emulator-manual.log',
 'manual-lookup-telemetry.jsonl':'artifacts/companion-final/manual-telemetry.jsonl',
 'webcam-unavailable.log':'artifacts/webcam-probe.log',
 'mug-a-android.png':'artifacts/apk-regression/0-Mug-A.png',
 'mug-b-android.png':'artifacts/apk-regression/0-Mug-B.png',
 'browser-to-android-refresh.png':'artifacts/companion-final/android-browser-refresh.png',
 'android-network-error.png':'artifacts/companion-final/android-network-error.png',
 'alice-companion.png':'artifacts/companion-final/alice-browser.png',
 'bob-companion.png':'artifacts/companion-final/bob-browser.png',
 'emulator-generated-camera.mp4':'artifacts/emulator-final/demo-recording.mp4',
}

def main():
    output=ROOT/'artifacts/presentation';output.mkdir(parents=True,exist_ok=True)
    files=[];missing=[]
    for name,relative in SOURCES.items():
        source=ROOT/relative
        if not source.is_file(): missing.append(relative);continue
        target=output/name;shutil.copyfile(source,target)
        files.append(dict(file=name,source=relative,size=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    (output/'manifest.json').write_text(json.dumps(dict(files=files,missing_optional=missing),indent=2)+'\n')
    print(f'Packaged {len(files)} evidence files in {output}; {len(missing)} unavailable optional files.')
    for path in missing:print('Unavailable: '+path)

if __name__=='__main__':main()
