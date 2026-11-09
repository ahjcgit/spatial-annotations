# Demo today, without glasses

Run from the **application submodule** (`SmartGlassProject/spatial-annotations`).
The standard APK needs no Mercury SDK. This demo uses QR identity and image-space
visualization. Optional [model detection](MODEL_DETECTION.md) needs no printed QR but
requires explicit object confirmation; neither mode implements spatial anchors.

## First-time environment setup

Use Python 3.11+, JDK 17, Android SDK 35 and build-tools 34.0.0.
The supplied environment helper finds the existing workspace `.toolchain` installation,
or honors your `JAVA_HOME` and `ANDROID_HOME`. See [toolchain setup](RAYNEO_SETUP.md#toolchain)
when using another computer.

```bash
bash scripts/setup_dev.sh
source scripts/dev_env.sh
```

## One command for the tested software workflow

```bash
.venv/bin/python scripts/demo.py
```

The script checks port **8011**, starts Uvicorn on **0.0.0.0**, checks health,
runs backend tests, creates/reuses Alice and Bob plus Mug A/B, generates printable
QR labels and grayscale fixtures, verifies sharing over HTTP, restarts its own backend
to verify persistence, runs Android JVM tests (including actual FastAPI HTTP and ZXing
replay), lint, and the standard debug build. It writes logs and a latency summary.
It then keeps the backend running until Ctrl-C. Re-running reuses the same database
and credentials; it never resets existing databases. Use `--port 8012` if occupied.
Port 5173 is reserved. Another running service is never stopped.

On the prepared computer the companion is **http://192.168.1.76:8011**.
On another computer, use the LAN URL printed by the script.

| Output | Location |
|---|---|
| Local credentials and registered marker IDs | `artifacts/demo/demo-data.json` (0600; do not share) |
| Persistent database | `artifacts/demo/demo.db` |
| Printable labels | `artifacts/demo/markers/print.html` |
| APK | `android/app/build/outputs/apk/debug/app-debug.apk` |
| Test logs, XML, real HTTP samples, summary | `artifacts/demo/` |
| Android test/lint reports | `android/app/build/reports/` |

Mug A has public, Alice-private, and team-group notes. Bob is initially a team member;
Mug B initially has no notes. The seed verification also checks Bob before membership
and after revocation, unauthorized direct-ID access, edits, and distinct marker resolution.
A and B may be physically identical: their **different QR labels** distinguish them.

## Run the APK without a camera

Start an Android emulator (API 26+), then use its explicit serial:

```bash
adb devices -l
adb -s emulator-5554 install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s emulator-5554 shell am start -n org.spatial.annotations/.MainActivity
```

1. Enter the printed LAN URL, save it, and sign in with Alice's local credentials.
2. Open **Scan / view annotations → Manual marker · SIMULATION**; paste A's UUID.
3. Expect **Mug A**, three notes, visibility/author labels, and an explicit SIMULATION label.
4. Navigate with buttons or left/right; up/down moves native control focus, Enter activates,
   Space opens full text. Refresh retrieves the currently authorized notes.
5. Select B: expect Mug B and zero notes. Return to A.
6. Open the companion in two separate browser contexts. Sign in as Alice/Bob using the
   local file; look up A; edit Alice's public note. Android **Refresh selected object**
   must show the change. Sign out/in on Android to check Bob sees only public/group notes.
7. Alice removes Bob in the companion; Bob refreshes and sees only public notes.
   Restore his membership for the presentation.

Manual entry verifies transport/permissions/UI, **not optical recognition**. No webcam
or emulator is needed for the default JVM/backend workflow. `--skip-build` reuses an
existing APK but skips JVM/lint/replay in that invocation; the log makes this explicit.

## Optional actual Android UI and generated-camera evidence

Install optional test dependencies once (using `uv pip install --python .venv/bin/python`
if this environment has no pip):

```bash
.venv/bin/python -m pip install -r scripts/requirements-evidence.txt
.venv/bin/python -m playwright install chromium
```

Run these **sequentially**, with the demo backend still running:

```bash
.venv/bin/python scripts/android_smoke.py --serial emulator-5554 --data artifacts/demo/demo-data.json
.venv/bin/python scripts/companion_smoke.py --data artifacts/demo/demo-data.json --android-serial emulator-5554
# Prepared emulator uses -camera-back imagefile:/home/ahjc/projects/m202a/.toolchain/demo-scenes/current.png
.venv/bin/python scripts/emulator_camera_test.py --serial emulator-5554 --trials 10 --negatives \
  --camera-image-file /home/ahjc/projects/m202a/.toolchain/demo-scenes/current.png
```

The image-file path must be shared with the emulator host/container. The test changes
that PNG before each camera open. The tested API-30 image-file camera crops its source;
`--fixture-x .25` (default) puts the full QR in view. This does not change app recognition.
For a host emulator supporting the legacy `virtualscene` poster API, omit
`--camera-image-file` (and use `--fixture-x .5`); `--token-file` selects its console token.
For a Docker-hosted legacy scene add `--container CONTAINER_NAME`. The installed emulator
37.2.13's new virtual room did not respond to poster changes; that exploratory trial failed.
The successful image-file path exercises **actual Camera2 → production ZXing → HTTP →
frozen frame and feature highlight**. This is an Android emulator with generated
camera images, not a webcam and not RayNeo hardware. Use a dedicated emulator: the
UI tests change the app's account/server and create then remove their own test note.

## Real webcam capture and production-decoder replay

```bash
.venv/bin/python -m pip install -r scripts/requirements-webcam.txt
.venv/bin/python scripts/qr_frames.py webcam --device 0 --label mug-a --expected MUG_A_UUID --conditions '40 cm, indoor light' --output artifacts/webcam
# Repeat for B, distance, rotation and dim-light conditions. Omit --expected for blank/unrelated QR.
# Space captures early, q cancels; --headless captures automatically.
android/gradlew -p android testDebugUnitTest -PreplayDir="$PWD/artifacts/webcam"
.venv/bin/python scripts/summarize_telemetry.py artifacts/webcam/replay-results.jsonl --output artifacts/webcam/summary.json
```

The capture utility saves lossless grayscale PNGs, packed luminance `.gray` files,
dimensions, clockwise display rotation, conditions and timestamps. Replay calls the
same Kotlin/ZXing recognizer used by Android; there is no substitute OpenCV decoder.
Capture files may show surroundings; keep them local. The current development host
exposes no webcam, so real-webcam results are **not yet available**.

Timing definitions and evidence interpretation: [TESTING.md](TESTING.md).
Next physical session: [RAYNEO_NEXT_DAY_CHECKLIST.md](RAYNEO_NEXT_DAY_CHECKLIST.md).

The corrected two-user recording is `artifacts/sharing-video/alice-bob-demo.mp4`.
Recreate it with `scripts/record_sharing_demo.py`; it shows Bob explicitly and labels
manual identification as simulation.
