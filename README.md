# Test the Spatial Notes demo, step by step

This demo attaches persistent notes to registered physical objects and shows each user
only the notes they are allowed to read. **Mug A and Mug B are separate records even if
the mugs look identical.** Alice can read her public, private and group notes; Bob can
read public notes and group notes while he is a member.

There are two identification modes:

| Mode | What you do | What identifies the instance |
|---|---|---|
| QR | Scan the object's printed marker | Its unique QR UUID |
| Model-assisted | Photograph a cup, select its detection, confirm Mug A/B | Your explicit confirmation of the registered object |

The model detects categories and image-space boxes. It **does not automatically distinguish
identical mugs**, track objects through space, or create persistent AR anchors. The standard
Kotlin Android app, FastAPI/SQLite backend and browser companion need no proprietary SDK.

**Start with the browser test below. It needs neither glasses, an Android emulator nor a webcam.**

## Live color presentation on the computer and glasses

Open **http://127.0.0.1:8014** for the no-login presentation. **Start live** continuously
captures color frames from the connected glasses, detects the selected sanitizer bottle,
and draws the current user's permitted note directly on the camera image. Switch **Alice**
and **Bob** to show different labels on the same bottle: Alice's private refill reminder
versus Bob's group note. Notes come from separate authenticated backend sessions; switching
users immediately clears the previous user's labels. Missing, ambiguous or stale detections
clear the overlay. Camera images go only to the configured local model backend and dashboard.

The glasses offer two modes, both controlled from the computer:

- **Minimal label:** readable text only, without an Android settings panel or camera picture.
  The computer keeps the live image-aligned overlay. This is the fallback.
- **On-object overlay:** experimental transparent camera-guided positioning. Arrows, scale,
  and eye-offset controls let the wearer align the label at the current viewing distance.
  It is not calibrated depth-aware AR, 6DoF tracking, or a persistent world anchor. Camera-to-eye
  parallax and movement can break alignment; use the minimal label mode when that happens.

With the model-enabled backend running (setup below), build and start:

```bash
source scripts/dev_env.sh
.venv/bin/python scripts/prepare_presentation.py --data artifacts/rayneo-demo/demo-data.json
android/gradlew -p android -PpresentationDemo=true testDebugUnitTest lintDebug assembleDebug
.venv/bin/python scripts/present_demo.py --serial YOUR_GLASSES_SERIAL \
  --data hardware-runs/rayneo/presentation-data.json \
  --install-apk android/app/build/outputs/apk/debug/app-debug.apk
```

Replace the source dataset path with the output from your backend setup. The preparation
command adds two separate bottle records without changing the original mug records, and
reuses its output on subsequent runs. The data file is local and untracked. It contains the prepared demo accounts, two registered
objects and `"target": "bottle"`. `--adb /path/to/adb` supports a toolchain outside PATH.
Setup installs `org.spatial.annotations.branchdemo` beside the original app, provisions
accounts into app-private storage, and forwards the backend over USB. Keep both backend
and dashboard running. **Pause camera** stops capture and clears labels. The presentation
activity is debug-only; credentials are not embedded in the APK or served to the browser.

This is a selected-object demo: show one sanitizer bottle at a time. The detector recognizes
the category `bottle`, not a unique physical instance. It must not be used to claim automatic
discrimination of identical bottles. The standard QR workflow below remains available.

## 1. Open the application repository

On the prepared computer:

```bash
cd /home/ahjc/projects/m202a/SmartGlassProject/spatial-annotations
source scripts/dev_env.sh
```

On another computer, enter the `spatial-annotations` submodule after cloning the parent
with `git clone --recurse-submodules https://github.com/ahjcgit/SmartGlassProject.git`.
All subsequent commands run from the application repository root.

## 2. Choose the prepared demo or start your own

### A. Use the already prepared computer

Check the existing model-enabled backend:

```bash
curl -fsS http://192.168.1.76:8012/health
curl -fsS http://192.168.1.76:8012/vision/status
export DEMO_DATA=artifacts/vision/demo-data.json
```

Expected: health `{"status":"ok"}` and vision `"configured":true`. Open
**http://192.168.1.76:8012** in your browser. The account/marker file above belongs to
this database. If the service is unavailable, follow option B rather than resetting data.

### B. Reproduce the complete setup

Prerequisites: Python 3.11+, JDK 17, Android SDK 35 and build-tools 34.0.0. The helper
finds this workspace's existing JDK/SDK; on another machine configure `JAVA_HOME` and
`ANDROID_HOME` using [Android setup](docs/RAYNEO_SETUP.md#toolchain).

```bash
bash scripts/setup_dev.sh
source scripts/dev_env.sh
# If uv is unavailable, use .venv/bin/python -m pip install instead.
uv pip install --python .venv/bin/python -r backend/requirements-vision.txt
.venv/bin/python scripts/setup_vision.py --sample
# Check the chosen port is free. Never interrupt a service already using it.
ss -lnt '( sport = :8013 )'
.venv/bin/python scripts/demo.py --vision --port 8013 --output artifacts/local-demo
```

Keep that terminal running. Wait for the final **Companion**, **Credentials**, **Print**,
**APK** and **Evidence** paths. The command:

1. Starts the backend on `0.0.0.0` and checks health.
2. Runs backend/script tests and creates or reuses Alice, Bob, Mug A/B and notes.
3. Loads the real model, verifies a blank frame, and associates both mugs with `cup`.
4. Generates printable markers and QR replay fixtures.
5. Verifies permissions and persistence across an actual backend restart.
6. Runs Android JVM tests, lint and the standard debug build.

In a **second terminal**, enter the same repository and set:

```bash
source scripts/dev_env.sh
export DEMO_DATA=artifacts/local-demo/demo-data.json
```

Open the **LAN URL printed by the first terminal**. Do not use `0.0.0.0` as the browser
address. Port 5173 is reserved. If 8013 is occupied, choose another free port with `--port`.
Re-running with the same output directory reuses its database and credentials; no reset occurs.
Ctrl-C stops only the backend started by this command, retaining its data.

For QR-only setup, omit the optional model installation and `--vision`. `--skip-build`
reuses an existing APK and skips Android tests/lint/build in that run; it does not claim
those checks passed. `--verify-and-exit` runs the checks, then stops its own backend.

## 3. Find the two users and object identifiers

Open the file named by `$DEMO_DATA` in your local editor. It contains:

- `backend`: the exact server URL to use in the browser and Android.
- `users[0]`: Alice's generated `username` and `password`.
- `users[1]`: Bob's generated `username`, `password`, and user `id`.
- `objects[0]`: Mug A, including its `marker_id`.
- `objects[1]`: Mug B, with a different `marker_id`.

Use the **full generated usernames**, not the literal words `alice` and `bob`. Credentials
remain local and untracked. Do not include this file in presentation evidence.

## 4. Check object-specific notes and permissions in the browser

1. Open the companion URL in two tabs. Sign in as Alice in one and Bob in the other.
   Sessions are stored per tab; reloading a tab signs it out.
2. In each tab, paste Mug A's `marker_id` into **Select an object → Marker UUID** and
   press **Look up**.
3. Compare **Annotations for this object** (expected counts for the unmodified seed dataset):

   | Selected object | Alice | Bob, initially a member |
   |---|---|---|
   | Mug A | 3 notes: PUBLIC, PRIVATE, GROUP | 2 notes: PUBLIC, GROUP |
   | Mug B | 0 notes | 0 notes |

4. Look up Mug B in both tabs. Expect zero notes and no leftover Mug A note text.
5. Return both tabs to Mug A. In Alice's tab, edit the **PUBLIC** note and save it.
   Press **Refresh** in Bob's tab. Expect the changed text.
6. In Alice's **Your groups** section, remove the member whose ID matches Bob's `id`
   from the local file. Refresh Bob's annotations. Expect **1 PUBLIC note**.
7. Restore Bob using the **Member username** form and his full generated username.
   Refresh Bob. Expect **2 notes** again. Leave membership restored for later tests.
8. Sign out in Alice's tab while Mug A is selected. Expect **1 PUBLIC note** and no
   private/group content. Sign back in when ready to continue.

**Pass condition:** A/B never mix, private content never appears for Bob, group access
changes on refresh, and edits are visible to other authorized readers.

## 5. Test model detection entirely in the browser

1. Sign in as Alice. Scroll to **Detect an object without a QR code**.
2. Use the photo chooser to select `artifacts/vision/coffee.png`. If absent, run
   `.venv/bin/python scripts/setup_vision.py --sample`.
3. Wait for detection results and a yellow box. Select the **cup** detection.
4. The page must ask you to confirm the physical object. Click **Confirm Mug A**.
   Expect **Model + your confirmation: Mug A** and **3 authorized annotations**.
5. Click **Confirm Mug B**. Expect **0 annotations**, with the same captured image
   clearly distinguished from your manually chosen database identity.
6. Repeat the upload in Bob's tab and confirm Mug A. Expect **2 notes**, no private note.
7. Upload a blank photo, or use **Clear / stop camera**. The previous annotations and
   selection must clear. A blank image should report **No confident object found**.

The sample is a real published CC0 coffee photograph, not a photo of your actual Mug A/B.
This replay validates detection and retrieval; your A/B confirmation supplies its demo
identity. Try a photo of your own mug next. Detection is imperfect: try better light and
framing if no cup appears. You may select another detected category only if you have a
registered object whose **Visual category** matches it.

For a new object, use **New marker**, fill **Register / update object** (including Visual
category, e.g. `cup`), and save. The internal UUID is still needed for storage, but you do
not need to print its QR to use model-assisted selection. Object metadata is public;
private information belongs in private annotations.

### Optional webcam test

On the **same computer as the backend**, open `http://localhost:8012` for the prepared
service, or `http://localhost:8013` for the example fresh setup. Sign in again on this
origin. Click **Open webcam preview**, allow camera access, aim at a cup, then click
**Capture and detect**. Preview alone uploads nothing. Capture sends one frame, stops
the camera, and enters the same category/instance confirmation flow.

Browsers restrict webcam access over ordinary LAN HTTP. For another device, use photo
upload or your configured HTTPS deployment. A missing/denied camera shows an error and
leaves photo upload available. No real webcam is currently exposed to this development
environment; its automated camera test uses a clearly labeled virtual camera fixture.

## 6. Install and test the actual Android app

Use a running Android emulator, ordinary Android phone, or the glasses when available.
Do not assume an emulator proves RayNeo compatibility.

```bash
source scripts/dev_env.sh
adb devices -l
export TEST_SERIAL=emulator-5554  # Replace with the exact serial shown above.
adb -s "$TEST_SERIAL" install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s "$TEST_SERIAL" shell am start -n org.spatial.annotations/.MainActivity
```

1. Enter the `backend` LAN URL from `$DEMO_DATA`, press **Save server**, sign in as Alice.
   The device must be able to reach that computer. If using USB instead of LAN, run
   `adb -s "$TEST_SERIAL" reverse tcp:8012 tcp:8012` and use `http://127.0.0.1:8012`
   in the debug app; substitute your chosen port when needed.
2. Open **Scan / view annotations → Manual marker · SIMULATION**. Enter A's UUID.
   Expect Mug A, **3 authorized notes**, and the explicit **SIMULATION** label.
3. Use **Next annotation** to see PUBLIC, PRIVATE and GROUP labels and author names.
   Look up B; expect zero notes. This step verifies network/permissions/UI, not a camera.
4. Return to A. Edit its public note in the companion and press **Refresh selected object**
   on Android. Expect the edit. Repeat Bob's login and membership-removal checks from step 4.
5. For optical QR testing, open the generated `markers/print.html` identified by the setup
   output and print both labels. Attach each to its correct mug. Select **Start camera /
   scan next object**, allow camera access, and scan A then B. Expect a frozen frame,
   highlighted QR feature centers, the correct name, and the correct authorized notes.
6. For model testing, use **Detect objects · model**, aim at a cup, select its category,
   then confirm A/B. Expect a frozen bounding box and **MODEL + YOUR CONFIRMATION**.
   This sends one grayscale frame to the configured model-enabled backend.
7. Try **Stop camera**, rescan, and refresh. On errors, adjust framing or fix the backend
   connection and retry; the app must not keep stale private notes from an earlier object.

APK: `android/app/build/outputs/apk/debug/app-debug.apk`.
For desktop mirroring and keyboard input, see [DESKTOP_CONTROL.md](docs/DESKTOP_CONTROL.md).
For physical RayNeo inventory, camera/display/input checks and fallbacks, follow
[RAYNEO_NEXT_DAY_CHECKLIST.md](docs/RAYNEO_NEXT_DAY_CHECKLIST.md).

## 7. Run automated checks and save evidence

With the backend running and `$DEMO_DATA` set to its matching dataset:

```bash
# Optional browser/emulator test dependencies; install once.
uv pip install --python .venv/bin/python -r scripts/requirements-evidence.txt
.venv/bin/python -m playwright install chromium

# Browser model/photo flow, Alice/Bob permissions, failure/recovery and stale-request checks.
.venv/bin/python scripts/companion_vision_test.py --data "$DEMO_DATA"
# Isolated 101-note pagination/revocation/recovery test; creates its own temporary backend.
.venv/bin/python scripts/companion_pagination_test.py
# Existing browser sharing, revocation, update and sign-out workflow.
.venv/bin/python scripts/companion_smoke.py --data "$DEMO_DATA"
# Production Android HTTP client and unit tests, lint, APK.
android/gradlew -p android testDebugUnitTest lintDebug assembleDebug -PdemoData="$PWD/$DEMO_DATA"
```

Run scripts that control the same emulator **sequentially**. The prepared emulator uses
an image-file camera; the following is photo/generated replay, not a real webcam:

```bash
.venv/bin/python scripts/emulator_model_test.py --data "$DEMO_DATA" \
  --camera-image-file /home/ahjc/projects/m202a/.toolchain/demo-scenes/current.png
.venv/bin/python scripts/emulator_camera_test.py --serial emulator-5554 --data "$DEMO_DATA" \
  --trials 1 --negatives --camera-image-file /home/ahjc/projects/m202a/.toolchain/demo-scenes/current.png
.venv/bin/python scripts/record_sharing_demo.py --data "$DEMO_DATA"
```

For an unattended full setup/check run on a **free** port:

```bash
.venv/bin/python scripts/demo.py --vision --port 8013 --output artifacts/check-run --verify-and-exit
```

| Evidence | Location |
|---|---|
| Backend/Android tests, restart checks, HTTP timings, QR replay | Chosen setup output directory |
| Browser model screenshots and actual assertion results | `artifacts/browser-vision/` |
| Alice/Bob sharing recording | `artifacts/sharing-video/alice-bob-demo.mp4` |
| Existing combined sharing/model video | `artifacts/vision/demo-with-bob-and-model.mp4` |
| Model camera test/video | `artifacts/vision/emulator/` (or specified `--output`) |
| Android lint/unit-test reports | `android/app/build/reports/` |
| Current measured results and limits | [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) |

The demo's purpose is **object-specific shared knowledge with enforced permissions**.
A successful test establishes the software path you actually exercised. Browser photo
upload, browser virtual camera, Android emulator camera, host webcam and physical RayNeo
are separate test environments; do not describe one as proof of another.

## Troubleshooting

| Symptom | Action |
|---|---|
| Port occupied | Choose a different free port. Do not kill another project's server; 5173 is reserved. |
| Health check fails | Keep the setup terminal open; inspect its `backend.log`; verify LAN/firewall access. |
| Login fails or notes/counts differ | Use the full generated username and the dataset file belonging to this backend/database. Restore Bob's membership. If you added notes, use a new output directory for strict automated demo checks. |
| Model unavailable (503) | Install `backend/requirements-vision.txt`, run `setup_vision.py`, start with `--vision`. QR remains usable. |
| Detector busy (429) | Another inference is running. Wait briefly and retry. |
| Cup detected but no candidates | Owner must set each object's Visual category to `cup`, or rerun the `--vision` setup for that dataset. |
| Browser webcam unavailable | Use localhost on the backend computer or HTTPS; check OS/browser permission; use photo upload. |
| No detection | Use a clearer, well-lit photo. The detector supports a fixed category list and is not universally reliable. |
| Android cannot reach backend | Use the actual LAN IPv4 URL, or the documented ADB reverse route; do a manual lookup first. |
| Stale page after source updates | Reload, then sign in again; authentication is deliberately tab-memory-only. |
| Android build missing tools | Configure JDK/SDK using [RAYNEO_SETUP.md](docs/RAYNEO_SETUP.md); browser tests can still run. |

Architecture/deployment: [ARCHITECTURE.md](docs/ARCHITECTURE.md).
Model provenance and timing definitions: [MODEL_DETECTION.md](docs/MODEL_DETECTION.md).
Dependency licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Generated credentials, databases, images, reports and APKs stay out of Git.
