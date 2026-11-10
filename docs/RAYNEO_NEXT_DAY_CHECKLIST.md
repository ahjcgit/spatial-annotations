# Next-day RayNeo integration checklist

Use the already built **standard** APK first. No vendor SDK is required.
All physical-device items below begin **NOT TESTED**. Emulator evidence does not
establish RayNeo camera, display, binocular or gesture compatibility.

## Connect, inventory, install

Keep `scripts/demo.py` running on the computer; see [quickstart](DEMO_QUICKSTART.md).
From the application submodule, with USB data cable connected and debugging enabled:

```bash
source scripts/dev_env.sh
adb devices -l
export GLASSES_SERIAL=ACTUAL_SERIAL
mkdir -p hardware-runs/next-day
adb -s "$GLASSES_SERIAL" shell getprop ro.product.model > hardware-runs/next-day/model.txt
adb -s "$GLASSES_SERIAL" shell getprop ro.build.version.release > hardware-runs/next-day/android.txt
adb -s "$GLASSES_SERIAL" shell getprop ro.build.version.sdk >> hardware-runs/next-day/android.txt
adb -s "$GLASSES_SERIAL" shell getprop ro.build.display.id > hardware-runs/next-day/firmware.txt
adb -s "$GLASSES_SERIAL" shell getprop ro.build.fingerprint >> hardware-runs/next-day/firmware.txt
adb -s "$GLASSES_SERIAL" shell dumpsys media.camera > hardware-runs/next-day/cameras-before.txt
sha256sum android/app/build/outputs/apk/debug/app-debug.apk > hardware-runs/next-day/apk.sha256
adb -s "$GLASSES_SERIAL" install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s "$GLASSES_SERIAL" shell am start -n org.spatial.annotations/.MainActivity
```

Record camera IDs from the camera dump and the app's scanning status. Record the
firmware version shown in the device's About screen if it differs from the build ID.
Do not infer model capabilities from the “X3” product name alone.

## Ordered trial (one visible QR at a time)

1. Confirm the app is visible **through the glasses**; record readable area, clipping,
   display routing, and whether operation is assisted by desktop mirroring.
2. Check native button selection, Back, scrolling, and text entry. With keyboard/DPAD,
   up/down focuses controls, Enter selects, left/right navigates notes, Space opens details.
   Vendor temple gestures remain unverified in the standard client.
3. Enter `http://192.168.1.76:8011` (or today's printed LAN URL); sign in as Alice using
   `artifacts/demo/demo-data.json`. First perform **Manual marker · SIMULATION** on A:
   three notes, including private. Then B: zero. This isolates network/auth/UI.
4. Start camera, allow permission, aim at A. Expect live grayscale preview, frozen
   recognized frame, yellow **feature-center** highlights, Mug A and three authorized notes.
   A 15-second timeout is a failed optical trial, not success; record it and retry.
5. Scan B. Expect Mug B, zero notes, and B's frame. A's content must disappear immediately
   on rescan. Repeat A/B at the chosen distance/light; log every attempt, including misses.
6. Sign out/in as Bob. A shows public/group, never Alice-private. Alice removes Bob in the
   companion; Bob refreshes and sees public only. Re-add him and refresh: group returns.
7. Edit Alice's public note in the browser, then refresh Android; check text. Temporarily
   interrupt connectivity and retry after restoring it; errors must clear stale note content.
8. Capture screenshots and logs. Record label width, distance, lighting, input method,
   camera ID, and failures alongside the automatic timings. Check screenshots against
   what the wearer sees; a screenshot alone cannot establish binocular readability.

```bash
adb -s "$GLASSES_SERIAL" exec-out screencap -p > hardware-runs/next-day/screen.png
adb -s "$GLASSES_SERIAL" logcat -d -v raw -s SpatialTelemetry:I > hardware-runs/next-day/telemetry.jsonl
adb -s "$GLASSES_SERIAL" logcat -d -v threadtime -s AndroidRuntime CameraManager CameraDevice > hardware-runs/next-day/errors.txt
adb -s "$GLASSES_SERIAL" shell dumpsys media.camera > hardware-runs/next-day/cameras-after.txt
.venv/bin/python scripts/summarize_telemetry.py hardware-runs/next-day/telemetry.jsonl --output hardware-runs/next-day/summary.json
```

Telemetry uses `android_device_unclassified`; attach the model/firmware inventory to
identify actual RayNeo runs. Do not mix earlier emulator log samples into the report.
The [full validation guide](HARDWARE_VALIDATION.md) includes sustained-use criteria and
an unfilled result template. Camera frames stay local and are not uploaded by the app.

## Troubleshooting and fallbacks

| Failure | Next check / command |
|---|---|
| ADB unauthorized/offline | Unlock/wear glasses and accept USB authorization; reconnect a data cable; `adb devices -l`. Do not delete host ADB keys or globally loosen USB permissions. |
| Installation fails | Save exact `adb install -r` output; check `adb -s "$GLASSES_SERIAL" shell df -h /data` and `shell getprop ro.build.version.sdk` (minimum 26). Signature mismatch requires the matching signing key or a deliberate uninstall that loses app state; do not uninstall reflexively. |
| Black or sleeping display | `adb -s "$GLASSES_SERIAL" shell input keyevent KEYCODE_WAKEUP`; `shell wm dismiss-keyguard`; collect `shell dumpsys power` and `shell dumpsys display`. A secured keyguard still needs user unlock. |
| Unexpected display routing | `scrcpy --serial "$GLASSES_SERIAL" --list-displays`; inspect `shell dumpsys activity activities`; explicitly launch `.MainActivity` again after closing virtual-display control. |
| Camera unavailable | Check permission with `shell dumpsys package org.spatial.annotations`, then `shell dumpsys media.camera`; close other camera apps and retry. Record ID/error. A listed camera is not proof capture works. |
| QR not recognized | Keep quiet zone visible, use one flat 65 mm label, improve focus/light/distance; record live frame count and timeout. Try manual lookup to separate identity/backend from optics. |
| Network error | Open server `/health` from companion; verify same LAN URL, firewall/client isolation. Diagnostic USB path: `adb -s "$GLASSES_SERIAL" reverse tcp:8011 tcp:8011`, then debug app URL `http://127.0.0.1:8011`. Label this USB, not LAN verification. |
| Authentication error | Use exact local seeded username/password; sign in again after expiry. Verify both clients use port 8011 and the same dataset. HTTP 404 can mean an unknown marker or a hidden annotation. |
| Firmware input mismatch | Use native focused controls, keyboard/mouse via desktop control, or companion for typing. Record which gestures failed; do not claim temple compatibility from key events. |

**Fallback A — standard Android client:** keep the standard APK. Run
`python3 scripts/control_glasses.py --serial "$GLASSES_SERIAL"` for desktop-assisted
setup, or append `--mirror` to mirror the physical display. The helper's virtual display
can isolate UI/network failures. Close it before verifying what the wearer sees.
See [desktop control](DESKTOP_CONTROL.md); desktop success does not establish glasses
optical display or camera compatibility.

**Fallback B — recorded software demonstration:** show the prepared generated-camera
emulator recording/screenshots and browser/permission logs in `artifacts/`. Label it
“Android emulator, generated virtual camera; physical RayNeo test failed/not completed.”
Use real-webcam replay only if actual captured frames and replay logs exist. Preserve
that day's hardware failure, model/firmware and error logs; do not substitute synthetic
evidence for a claimed physical test.

Mercury is optional and isolated. No licensed AAR was found in the project environment;
its adapter remains unbuilt. Do not introduce it until the standard client is validated.
Binocular fusion, vendor gestures, physical camera/display behavior and firmware-specific
routing require the device. World tracking and persistent AR anchors are not implemented.

## Optional model mode, after the QR baseline

Use the model-enabled backend URL (prepared host: `http://192.168.1.76:8012`). Confirm
`curl -fsS http://192.168.1.76:8012/vision/status` reports `configured: true`. Sign in,
choose **Detect objects · model**, aim at a cup, select its detection and explicitly
confirm Mug A/B. Check the frozen box aligns with the cup and normal permissions apply.
The model infers on the computer, so the glasses need network connectivity. Collect
`adb -s "$SERIAL" logcat -v time SpatialVision:I SpatialTelemetry:I '*:S'`.
Category detection on the glasses' grayscale camera, lighting robustness and frame
orientation are still untested physically. Model failure does not prevent the QR baseline.
