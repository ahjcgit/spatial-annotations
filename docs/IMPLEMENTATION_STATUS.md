# Implementation status — November 9, 2026

The standard Kotlin Android client, FastAPI/SQLite backend and browser companion are
implemented and software-tested without RayNeo glasses. The app now preserves the
recognized frame and highlights QR feature centers beside readable object-specific
annotations. This is **image-space annotation visualization**, not SLAM, markerless
recognition, a pose estimate, or persistent world anchoring.

The prepared companion is running at **http://192.168.1.76:8011**. The original service
on port 8000 and Rakazo on 5173 were left intact. Run commands inside
`/home/ahjc/projects/m202a/SmartGlassProject/spatial-annotations`, the actual submodule.
The sibling standalone clone was not edited.

## Baseline and environment

Baseline commit: `6468b4eb0b1740985ede19babda168cd6429c3b6`. Parent and submodule were
clean before work. Baseline backend: **20 passed**. Baseline Android: **13 passed**;
`testDebugUnitTest lintDebug assembleDebug` succeeded; lint had **0 errors, 28 warnings**.
No baseline functional/build failure was found. An initial shell invocation used the
wrong relative Python path; the corrected command passed before implementation.

| Environment item | Observed result |
|---|---|
| JDK | Existing Zulu OpenJDK 17.0.21 under workspace `.toolchain` |
| Android SDK | Existing SDK 35, build-tools 34.0.0, platform-tools; Gradle 8.9/Kotlin 2.0.21 |
| Python | Python 3.11 virtual environment; ordinary dependencies installed with uv |
| Docker | Available; separate Python backend plus existing emulator runtime image |
| ADB | Available; disposable `emulator-5554`, Android API 30 x86_64 |
| Emulator | 37.2.13; host user lacks direct KVM access; Docker `--device /dev/kvm` booted successfully |
| Host webcam | No `/dev/video*`; OpenCV device-0 probe failed; **zero real-webcam samples** |
| Licensed Mercury SDK | No matching AAR in project environment; optional adapter not compiled |
| Physical RayNeo | **Not connected or tested in this task** |

## Feature matrix

| Feature | Implemented | Tested | Test environment | Result | Hardware validation needed |
|---|---|---|---|---|---|
| Backend/authentication | Yes | Yes | 22 pytest cases, actual Uvicorn HTTP, browser, Android | Pass | RayNeo connectivity only |
| Two distinct identities | Yes | Yes | Identical-name objects in backend tests; A/B alternating camera fixtures | Pass; no cross-object notes | Printed labels on physical mugs |
| Public/private/group and direct-ID protection | Yes | Yes | Backend, HTTP E2E, browser, Android accounts | Pass; Bob never receives Alice-private note | Repeat on glasses |
| Group membership revocation | Yes | Yes | API/browser plus Bob Android refresh | Pass; public-only after removal, group returns after restoration | Repeat on glasses |
| Persistent accounts/objects/notes/groups | Yes | Yes | File-backed SQLite tests and actual backend process restart | Pass | Device app restart/storage behavior |
| Printable QR labels and served PNGs | Yes | Yes | Exact two printed PNGs and two `/markers/UUID.png` responses replayed through production Kotlin decoder | 4/4 decoded to registered markers | Printing/optical quality |
| QR parsing/decoding/rotation | Yes | Yes | Production ZXing JVM replay, varied size/quarter-turn/18°/dim synthetic images | 20/20 positives, 4/4 correct rejections | Blur/glare/distance on glasses |
| Live preview and frozen-frame highlight | Yes | Yes | Actual emulator Camera2, screenshots; coordinate JVM tests | Pass; detected feature centers only | Physical camera/display orientation |
| Partial/missing/invalid points | Yes | Yes | JVM geometry validation | Pass; no fabricated corners | Not required for software logic |
| Annotation readability/navigation | Yes | Yes | Emulator views, account smoke, navigation JVM tests | Pass on emulator; full-text dialog available | Wearable readable area, binocular comfort |
| Refresh after companion edit | Yes | Yes | Actual browser form edit → Android lookup → second edit → Android Refresh | Pass | Repeat on glasses |
| Stale requests, logout, session expiry | Yes | Yes | Controller/cancellation/auth JVM tests; Android sign-out and process restart | Pass; stale 401 cannot erase a newer session | Device Keystore compatibility |
| Rapid rescan decoder concurrency | Yes | Yes | Concurrent-worker JVM test and final APK rescan regression | See final APK regression below | Camera HAL reopen behavior |
| Network failure and recovery | Yes | Yes | Actual Android connection refusal then restored server; JVM recovery | Pass; cleared notes/error, subsequent B lookup succeeds | Real Wi-Fi failure modes |
| Telemetry/reporting | Yes | Yes | Monotonic calculation tests, real emulator/HTTP JSONL, 2 reporter tests | Pass; simulated/optical/environment fields separated | Collect physical samples |
| One-command demo | Yes | Yes | Fresh dataset on 8012; reuse on 8011; setup script | Pass; no destructive reset | None |
| Standard debug APK | Yes | Yes | Gradle, lint, installed Android emulator | Pass | Install/display/input on RayNeo |
| Webcam capture utility | Yes | Partial | OpenCV failure probe; shared raw replay path tested with generated pixels | Capture blocked: no exposed webcam | Host webcam access, not RayNeo |
| Emulator with host webcam | Available workflow | No | No host capture device | Environment blocked | Host webcam access |
| Offline real-webcam replay | Yes | No real frames | No captures available | Not tested on real-camera images | Host webcam access |
| Mercury binocular adapter | Existing optional source | No | Licensed AAR absent | Isolated; unbuilt/untested | Licensed SDK, firmware and device |
| Physical camera, display, gestures, binocular alignment | Prepared checklist | No | Physical RayNeo absent | Not tested | Required |
| SLAM/6DoF/world anchors/markerless recognition | No | No | Out of checkpoint scope | Not implemented | Additional future implementation |

## Changes and safeguards

- `Recognition.kt`, `FrameGeometry.kt`, `FramePreview.kt`, `Camera2Capture.kt`: strict
  `spatial:v1:` optical payloads; original image-space feature coordinates; shared rotation
  and letterboxing; worker-thread bitmap creation; one pending preview update; generation
  guards; retained frozen frame. Displayed bitmaps are released to Android/GC instead of
  being recycled while RenderThread might still reference them. ZXing access is synchronized
  across overlapping old/new camera workers.
- `MainActivity.kt`, `Hardware.kt`: high-contrast native views, author/visibility/count,
  progress, refresh/rescan, adaptive preview height, 15-second optical timeout, DPAD focus
  navigation and an explicit SIMULATION label. Changing server refreshes the identity label.
- `ScanController.kt`, `ApiClient.kt`, `Auth.kt`, `Models.kt`: cancellable HTTP through body
  reading, revision-guarded results, atomic token-specific expiry handling, cleared error
  content, and revalidation of existing pages when loading more after membership changes.
- `ScanTelemetry.kt`: monotonic stage timing; JSON contains IDs/counts/status/durations,
  never tokens, passwords, usernames or note contents. UI timing means a queued callback
  after binding, not photons reaching a display. See [timing definitions](TESTING.md#timing-boundaries).
- Tests: `VisualizationTest.kt`, `ReplayTest.kt`, `LiveBackendTest.kt`, `ApiClientTest.kt`,
  `backend/tests/test_api.py`, `scripts/tests/test_telemetry.py`.
- Workflow/evidence: extended `e2e.py`, `generate_markers.py`, `android_smoke.py`; added
  `demo.py`, `setup_dev.sh`, `dev_env.sh`, `qr_frames.py`, `verify_markers.py`,
  `companion_smoke.py`, `android_ui.py`, `emulator_camera_test.py`, `emulator_scene.py`,
  `summarize_telemetry.py`, `package_evidence.py` and optional dependency lists.
- Backend and companion production code and permission rules were preserved. Existing
  `.gitignore` covers credentials, databases, SDKs, APK/build output and all `artifacts/`.

## Final commands and observed outcomes

| Executed command | Actual outcome / evidence |
|---|---|
| `bash scripts/setup_dev.sh` | Pass; `artifacts/setup-dev.log` |
| `(cd backend && ../.venv/bin/python -m pytest -q)` | **22 passed**, one Starlette/AnyIO deprecation warning; `artifacts/backend-final.log` |
| `.venv/bin/python -m pytest -q scripts/tests` | **2 passed**; `artifacts/script-tests.log` |
| `android/gradlew -p android testDebugUnitTest lintDebug assembleDebug -PreplayDir="$PWD/artifacts/demo/qr-frames" -PdemoData="$PWD/artifacts/demo/demo-data.json"` | **25 JVM tests passed, zero skipped**, 28 replay fixtures matched; build successful; `artifacts/android-final.log` and Gradle XML |
| Android lint | **0 errors, 31 warnings**: dependency-version notices and English literal/localization warnings; no DrawAllocation warning remains |
| `.venv/bin/python scripts/demo.py --port 8012 --output artifacts/repro --verify-and-exit` | Fresh setup, seed sharing assertions, exact QR generation/replay, **40/40 HTTP lookups** across process restart, build/lint/tests all passed; `artifacts/repro-run.log` |
| `.venv/bin/python scripts/android_smoke.py --serial emulator-5554 --data artifacts/demo/demo-data.json` | Alice/Bob privacy, Android note creation, encrypted session persistence, camera permission/start/stop passed; `artifacts/emulator-manual.log` |
| `.venv/bin/python scripts/companion_smoke.py --data artifacts/demo/demo-data.json --android-serial emulator-5554` | Browser permissions/editing, Bob Android membership changes, browser edit/Android refresh, actual network failure/recovery passed; `artifacts/companion-final.log` |
| `.venv/bin/python scripts/emulator_camera_test.py` with shared image-file camera, ten trials/object and negatives | **20/20 valid scans and 2/2 correct negative rejections**; `artifacts/emulator-final/{results.json,telemetry.jsonl,summary.json}` |
| Final APK camera/rescan regression | **7/7 valid scans** (three A/B pairs plus recovery), **2/2 correct negative rejections**, **eight rapid start/stop cycles** without stale frame/crash; installed APK SHA matches final artifact; `artifacts/apk-regression/` |
| Final dataset verification on 8011 | **20/20 additional HTTP lookups**; expected Alice=3, Bob=2, B=0; `artifacts/final-http.log` |
| Webcam utility `webcam --headless --frames 1` | Failed to open device 0; no video device exists; `artifacts/webcam-probe.log` |
| `python3 -m compileall -q scripts`, `bash -n ...`, `git diff --check` | Passed |

The fresh setup ran before the last concurrent-decoder regression was added, so its
saved Gradle report contains 24 tests. The final explicit Android run contains 25; both
are actual completed runs. A fresh ordinary Gradle run without replay/live properties
will explicitly skip those two optional integration cases, not silently claim them passed.

## Measured timings (milliseconds)

| Measurement | n | Mean | Median | P95 |
|---|---:|---:|---:|---:|
| Emulator camera → valid QR | 20 | 806.95 | 793.50 | 873.00 |
| Emulator marker lookup + notes | 20 | 513.45 | 510.00 | 534.00 |
| Emulator successful scan → UI callback | 20 | 1367.20 | 1350.50 | 1448.00 |
| Desktop HTTP simulated lookup | 40 | 4.09 | 3.88 | 4.88 |
| Synthetic JVM decoder, including negatives | 24 | 1.57 | 1.52 | 2.20 |

Camera measurements are from 20 correct generated-camera detections (ten/object),
not physical RayNeo trials. Both negative inputs correctly timed out at 15 seconds;
the raw 22-attempt summary retains those two `recognition_timeout` records. The table
reports successful scan latency separately from those intentional negatives. There were
zero wrong-object associations and 20/20 successful backend lookups after identification.

Benchmark APK SHA-256: `f5984072db9560a71532c0d248a9c6c4fb76dba1eb7c0aeeabd4827a55f94b81`.
The final APK adds decoder synchronization for overlapping camera workers. Its separate
camera/rescan regression is listed above; benchmark measurements are not relabeled as
measurements of that later APK. The browser/network workflow used the benchmark APK;
the final decoder change does not alter that HTTP/UI implementation, and final JVM
HTTP/authentication tests were rerun. Desktop/JVM and emulator latencies must not be pooled.

## Evidence Available for November 12 Presentation

The allowlisted `artifacts/presentation/` bundle contains actual test logs, summaries,
raw timing samples, selected screenshots, a three-minute generated-camera recording,
APK checksums and an evidence manifest. It excludes local credentials, the database,
SDKs and tokens. Recreate it with `.venv/bin/python scripts/package_evidence.py`.

Software demonstrated: two registered objects, QR identification, frozen feature highlights,
authorized annotation retrieval, Alice/Bob privacy, group revocation/restoration,
browser edits reflected in Android, error recovery, and persistent SQLite data.

Copyable four-slide summary:

| Slide | Claim supported by evidence |
|---|---|
| 1 — Design | Camera2 + ZXing identify `spatial:v1:UUID`; Kotlin Views display image-space highlights and notes; FastAPI/SQLite enforce sharing. No world anchors. |
| 2 — Software correctness | 22 backend + 25 Android JVM + 2 reporter tests; 28 image replay cases; two-user browser/Android workflows; 40 HTTP retrievals across backend restart. |
| 3 — Demonstration and timing | Actual APK Camera2 → QR → HTTP → highlighted frozen frame; A/B identities remain separate. Use the measured table above and label **generated emulator camera**. |
| 4 — Limits and next step | No host webcam was exposed; no physical RayNeo run. Next: install the prepared APK, isolate network/UI with manual lookup, then test physical camera/display/input using the checklist. |

Screenshots/recording demonstrate an emulator rendering generated QR images, not a wearer
viewing physical mugs. The two negative camera inputs are intended rejections, not
successful optical identifications. Earlier exploratory failures are retained separately.

## Resolved issues and remaining limits

During implementation, the replay Gradle input declaration initially failed to compile;
it was corrected. Android's Kotlin compile classpath did not expose desktop `ImageIO`,
so fixtures now use portable packed grayscale data plus PNG previews. UIAutomator dialog
selection raced keyboard animation; the helper now waits and uses the dialog resource ID.
These were introduced development/test-harness failures, not baseline failures, and the
final checks pass.

The emulator's new virtual room ignored legacy poster updates; the first optical trial
failed. Two image-file setup trials then failed because the source QR was cropped.
The final fixture positions the full marker within the observed field of view. These
logs/screenshots remain in `artifacts/emulator-camera-probe/`, `emulator-image-probe/`
and `emulator-padded-probe/`; they are not counted as successful controlled trials.
Monotonic arrival-time throttling replaced reliance on emulator capture timestamps,
which had caused only one frame to be processed in the first 15-second run.

Physical RayNeo display routing, Camera2 HAL behavior, focus/exposure, optics, gestures,
Keystore and binocular comfort remain unverified. Real-webcam capture/replay is environment
blocked. The optional Mercury adapter remains unbuilt without a licensed SDK. Localization
warnings remain; the demo UI is English. SQLite is tested; PostgreSQL, public deployment
hardening and production TLS issuance are not part of this checkpoint. Copying a QR copies
its identity; this is not anti-counterfeit recognition. No physical performance claim is made.

## Handoff

Run today: [DEMO_QUICKSTART.md](DEMO_QUICKSTART.md).
Physical integration commands: [RAYNEO_NEXT_DAY_CHECKLIST.md](RAYNEO_NEXT_DAY_CHECKLIST.md).

APK: `android/app/build/outputs/apk/debug/app-debug.apk` (normal build location).

SHA-256: `5aef0107b4a47451cc09a3ebe68136cec349a3cd0d7820d2f4e80a1fc843d858`.

Git branch: `demo/no-glasses-validation`; verified work is committed locally in the
application repository. Use `git log -1 --oneline` for the final source commit. Nothing
was pushed. The parent repository still pins baseline `6468b4e`; after reviewing the
application commit, its `spatial-annotations` gitlink must be advanced to that commit.
The parent pointer was not committed here. Publish the application commit before any
future parent pointer push so other clones can resolve it.
