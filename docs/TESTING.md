# Testing

Run commands from the experiment root. Use Python 3.11+ and install the development
requirements once:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
(cd backend && ../.venv/bin/python -m pytest -q)
(cd android && ./gradlew testDebugUnitTest lintDebug assembleDebug)
```

Backend tests use temporary SQLite databases. They cover authentication, note
permissions, group membership, validation, persistence, and companion/API routes.
Android JVM tests cover QR decoding, sessions, URL policy, HTTP calls, and scan state.
Gradle writes reports to `android/app/build/reports/`.

## HTTP sharing test

Start the backend as described in the [README](../README.md), then run:

```bash
.venv/bin/python scripts/e2e.py --url http://SERVER_LAN_IP:8000
```

This creates two accounts, two objects, and public/private/group notes. It checks
sharing, membership revocation, and author-only mutations. It leaves the dataset
on the server and writes credentials/IDs to ignored `demo-data.json`. Each run
creates new data. See [the demo](DEMO.md) to print matching labels.

## Optional emulator smoke test

Use a disposable emulator with the standard APK installed and a fresh HTTP test
dataset. The script signs in as both users, creates a note, checks session recovery,
and starts/stops the camera.

```bash
.venv/bin/pip install -r scripts/requirements-device.txt
.venv/bin/python scripts/android_smoke.py --serial emulator-5554 --data demo-data.json
```

Screenshots go to ignored `artifacts/android-smoke/` by default. The script uses
manual marker lookup; it does not test optical scanning or binocular display.

## Device testing

Follow [hardware validation](HARDWARE_VALIDATION.md) for physical QR scanning,
input, display, and sustained use. Keep dated device reports in `hardware-runs/`.
The optional Mercury build requires a licensed AAR. PostgreSQL and HTTPS issuance
also need separate environment checks; the automated backend suite uses SQLite.

Generated logs, screenshots, and API schema snapshots are not source files. Store
any local captures in `artifacts/`. The live API exposes its schema at `/openapi.json`.

## Software-only evidence pipeline

`source scripts/dev_env.sh && .venv/bin/python scripts/demo.py` runs the core checks
against a separate persistent database and checks a real Uvicorn process restart.
Use `--verify-and-exit` for a finite run. Optional UI tests must run **sequentially**;
they share the emulator and temporarily modify the seeded data. Do not run them while
the core integration test is asserting the initial note counts.

```bash
(cd backend && ../.venv/bin/python -m pytest -q)
.venv/bin/python -m pytest -q scripts/tests
.venv/bin/python scripts/qr_frames.py synthetic --data artifacts/demo/demo-data.json --output artifacts/demo/qr-frames
android/gradlew -p android testDebugUnitTest lintDebug assembleDebug \
  -PreplayDir="$PWD/artifacts/demo/qr-frames" -PdemoData="$PWD/artifacts/demo/demo-data.json"
```

The `ReplayTest` and `LiveBackendTest` cases explicitly skip without their properties;
ordinary unit tests still exercise generated pixels. The demo supplies both properties,
so a successful demo run includes the actual replay and real HTTP checks. Replay reads
packed luminance, width, height and rotation from the manifest. PNGs are visual evidence;
raw `.gray` data avoids substituting a desktop QR decoder or Android Bitmap stubs.

| Evidence class | What it establishes |
|---|---|
| Synthetic image JVM tests | Production Kotlin/ZXing decoding, strict optical protocol, rotations, feature coordinates, expected-negative rejection |
| Offline real-webcam replay | Production decoder on actual saved host-camera pixels; only available after capture |
| Android emulator, generated camera | Actual Camera2/ZXing/HTTP/UI with emulator-produced images; neither host optics nor RayNeo |
| Android emulator, host webcam | Actual Android pipeline with host optics, if exposed; still not RayNeo |
| Explicit manual simulation | Authentication, identity lookup, permissions and UI; no optical timing |
| Physical RayNeo | Only actual device trials using the next-day checklist |

`companion_smoke.py` drives the real browser forms, tests two users, group revocation,
private direct-ID denial, object isolation, editing and sign-out. With `--android-serial`
it also checks a browser edit on Android, edits again, then refreshes the already selected
Android object. It restores the original public note afterwards. `android_smoke.py`
creates and removes its own disposable note and verifies encrypted session persistence.

### Timing boundaries

The standard Android activity logs one JSON object per attempt under **SpatialTelemetry**.
Durations use `SystemClock.elapsedRealtimeNanos()/1_000_000`; UTC timestamps label trials.
A UUID test ID distinguishes each actual attempt. No passwords, tokens, usernames or note
contents are included. Captured images are not part of telemetry and remain local.

| Field | Boundary |
|---|---|
| `recognition_latency_ms` | Start-camera action (after permission granted, before Camera2 startup) to valid production-decoder result; includes startup and waiting for frames |
| `frames_processed` | Frames actually passed to ZXing, not sensor frame rate |
| `recognition_wait_ms` | Time until cancellation/15-second timeout when no valid QR was found |
| `backend_latency_ms` | Controller lookup entry to both marker-resolution and authorized-note retrieval completing, including dispatch/parse time; failures end at error state |
| `detection_to_retrieval_ms` | Decoder completion to backend completion, including UI dispatch |
| `retrieval_to_ui_ms` | Backend completion to a queued UI callback after binding text; **not display-photon latency** |
| `total_latency_ms` | Start of attempt to that UI callback, or to failure/cancellation |

A frozen frame highlights **actual ZXing feature centers**, usually three finder centers
and possibly an alignment point. It never infers a four-corner box. Zero/partial points
still permit identity retrieval; no highlight is invented. Buffer rotation accounts for
sensor/display orientation and lens facing; then points and bitmap share FIT_CENTER
letterboxing. The calculation follows [Android Camera2 orientation guidance](https://developer.android.com/media/camera/camera2/camera-preview#orientation_calculation).
Front previews are deliberately unmirrored. Coordinate behavior is unit-tested; perceived
upright orientation on the target camera/display combination needs a physical check.

`simulated_lookup`, `simulated_refresh`, and `refresh` carry null recognition timing and
success fields. They must not be graphed as optical scans. The JVM replay measures decoder
call time, not camera acquisition; desktop HTTP measurements include two HTTP requests,
not Android UI time. Reports separate execution environment and identification method.

```bash
adb -s emulator-5554 logcat -d -v raw -s SpatialTelemetry:I > artifacts/android-telemetry.jsonl
.venv/bin/python scripts/summarize_telemetry.py artifacts/android-telemetry.jsonl \
  artifacts/demo/qr-frames/replay-results.jsonl --output artifacts/timing-summary.json
```

Summary output includes sample counts, success rates, mean/median and nearest-rank P95
only for groups with at least 20 measured values. Raw detection success includes expected
negative images; `expectation_match` and `positive_target_success` separately describe test
correctness. Failure categories include camera error, recognition timeout, cancellation,
network, and HTTP status. Keep failed exploratory runs; do not claim unit fixtures as
performance samples or pool desktop/emulator/device latencies.

### Reproduce the prepared headless emulator

Host KVM exists but this user cannot open it directly. The successful local route uses
an already available `spatial-android-emulator` Docker image with runtime libraries,
`--device /dev/kvm`, and the existing API-30 AVD. No physical camera is passed through.
Do not start another instance while this one owns ports 5554/5555. The read-only AVD
option keeps these test changes separate from its saved userdata.

```bash
ss -lnt '( sport = :5554 or sport = :5555 )'
# Run only if ports are free. Source paths below are specific to the prepared computer.
docker run --rm -d --name spatial-demo-emulator --device /dev/kvm --network host \
  -v /home/ahjc/projects/m202a/.toolchain:/home/ahjc/projects/m202a/.toolchain \
  -e ANDROID_HOME=/home/ahjc/projects/m202a/.toolchain/android-sdk \
  -e ANDROID_AVD_HOME=/home/ahjc/projects/m202a/.toolchain/avd \
  spatial-android-emulator /home/ahjc/projects/m202a/.toolchain/android-sdk/emulator/emulator \
  -avd spatial_api30 -read-only -no-window -no-audio -no-snapshot -gpu swiftshader_indirect \
  -camera-back imagefile:/home/ahjc/projects/m202a/.toolchain/demo-scenes/current.png -camera-front none
adb -s emulator-5554 wait-for-device
adb -s emulator-5554 shell getprop sys.boot_completed  # wait until this reports 1
adb -s emulator-5554 install -r android/app/build/outputs/apk/debug/app-debug.apk
```

On another computer, use an ordinary Android Studio AVD and its supported camera mode;
the default demo remains independent of emulator availability. The OpenCV probe on this
host failed because there are no video capture devices. It produced no webcam samples.
