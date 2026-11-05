# RayNeo experiment capability validation — step by step

Use this guide to decide whether **your particular glasses, firmware and SDK combination** can perform the experiment. Record observations instead of checking boxes based on product specifications. No physical RayNeo test has been completed by this project's software author.

There are two separate decisions:

- **Required experiment:** identify physical objects by QR, create/retrieve persistent notes, read them through the glasses, and enforce multi-user permissions. Screen/head-locked text and companion-based authoring are acceptable. Passing steps 1–8 confirms this workflow for the tested configuration.
- **Optional spatial extension:** obtain usable 6DoF poses and render a calibrated card beside an object. Steps 9–10 investigate this. Failure here does not invalidate the required QR-based experiment. The current app does not implement world-space alignment or persistent SLAM anchors.

An app failure alone does not prove a hardware capability is absent: distinguish app bugs, permissions, firmware restrictions, SDK incompatibility and genuinely unavailable features. Use **PASS / FAIL / BLOCKED / NOT TESTED**. Record the build/firmware for every result.

## Before starting

Have the glasses and their normal companion phone, a USB **data** cable, a computer with ADB, the Android project toolchain or an existing debug APK, the backend, and two visually identical mugs/boxes. Have a printer and two test accounts. Use synthetic notes, not confidential content.

Run shell examples from the repository root in Bash on Linux/macOS. Windows users can run them in a configured Bash environment or adapt paths/variables to PowerShell. APK installation does not require building the project if you already have the debug artifact. On a fresh Git clone, build it using [RAYNEO_SETUP.md](RAYNEO_SETUP.md); build outputs are not tracked in Git.

Create a local evidence folder:

```bash
mkdir -p hardware-runs
```

`hardware-runs/` is ignored by Git. Keep device logs and private test credentials local; review/redact anything you later share. Copy the report template at the end into that folder. Record firmware before changing it; firmware updates can change the capabilities being measured.

## 1. Confirm the exact device and development access

**Question:** Can this model run and debug our Android application?

1. On the glasses, note the marketed model and OS version from Settings/About.
2. Enable ADB using the vendor instructions for that firmware. See [the developer-mode section](RAYNEO_SETUP.md#developer-mode-adb-and-sideloading). Do not assume an X3 and X3 Pro, or different regional firmwares, are equivalent.
3. Connect USB and accept the computer authorization on the glasses.
4. Run:

   ```bash
   adb devices -l
   export GLASSES_SERIAL='REPLACE_WITH_THE_ACTUAL_DEVICE_SERIAL'
   adb -s "$GLASSES_SERIAL" shell getprop ro.product.model > hardware-runs/model.txt
   adb -s "$GLASSES_SERIAL" shell getprop ro.build.display.id > hardware-runs/firmware.txt
   adb -s "$GLASSES_SERIAL" shell getprop ro.build.version.sdk > hardware-runs/android-api.txt
   adb -s "$GLASSES_SERIAL" shell getprop ro.product.cpu.abilist > hardware-runs/abis.txt
   adb -s "$GLASSES_SERIAL" shell pm list features > hardware-runs/features.txt
   adb -s "$GLASSES_SERIAL" shell dumpsys media.camera > hardware-runs/cameras-before.txt
   adb -s "$GLASSES_SERIAL" shell dumpsys sensorservice > hardware-runs/sensors.txt
   ```

**PASS:** ADB reports the physical serial as `device`, shell commands succeed, and Android API is at least 26 (this app's minimum). Preserve the model/firmware/API outputs. Feature and sensor listings are an inventory, not proof that an ordinary application can use every listed feature.

**If blocked:** `unauthorized` means the computer authorization is incomplete; `offline` or no device suggests a cable, driver, USB mode or firmware setting issue. Resolve this before spending time on AR SDK integration. Avoid selecting `emulator-*` accidentally. The [Android ADB manual](https://developer.android.com/tools/adb) documents device selection, installation and shell access.

## 2. Confirm installation, readable display and usable controls

**Question:** Can the wearer actually use this APK through the glasses?

```bash
adb -s "$GLASSES_SERIAL" install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s "$GLASSES_SERIAL" shell am start -n org.spatial.annotations/.MainActivity
```

1. Look through the glasses themselves. Confirm that **Spatial Notes** and its controls appear and are readable.
2. Test selecting a control, going Back, and scrolling. Record which hardware inputs work. An attached keyboard/cursor or ADB mirroring may assist initial server/account configuration, but mark that setup as assisted.
3. Check both eyes independently, then together: note missing-eye content, double images, clipping and whether the text can be comfortably read. A computer screenshot cannot establish binocular fusion.
4. If ordinary Android windows are unusable, perform the **Mercury adapter test below**, then repeat this gate.

**PASS:** The wearer can read notes and operate the viewing/scanning controls. For the final independent-use trial in step 8, selecting/scanning objects and navigating notes must work without a computer operator. Companion typing remains allowed.

**If blocked:** Save a crash log and compare the generic app with the official vendor sample. A generic-window failure may be a display/input integration issue, not a lack of camera/network capability. Continue any independent diagnostic steps you can access, but do not mark the glasses workflow passed.

### Mercury binocular/input test, if needed

Follow [official SDK installation](RAYNEO_SETUP.md#official-sdk-installation-optional-adapter). Obtain the licensed Mercury AAR; it is not supplied in this repository. From the repository root:

```bash
cd android
./gradlew -PwithRayneo=true assembleDebug
cd ..
adb -s "$GLASSES_SERIAL" install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s "$GLASSES_SERIAL" shell am start -n org.spatial.annotations/.MainActivity
```

This replaces the standard debug APK at the same build path. Record the AAR filename/version and APK hash so results can be attributed to the correct build. The optional adapter has not yet been compiled with a licensed AAR in this project.

Configure the server/account in the standard screen, then select **RayNeo binocular viewer**. After you have notes from step 3, test all mappings:

| Wearer action | Expected result |
| --- | --- |
| Tap with no selected note | Start scanning |
| Tap with a selected note | Toggle author/time details |
| Slide forward / backward | Next / previous note |
| Slide up / down | Scroll long text |
| Triple tap | Clear selection and scan again |
| Double tap | Return to standard screen |

Record results for each gesture; direction and system interception must be measured on the target firmware. Do not substitute long press for an unverified gesture. Test binocular readability again. If the adapter fails, try the **unmodified official Android sample** with the same SDK/firmware: sample failure and adapter-only failure are different findings. The [Qualcomm guide](https://www.qualcomm.com/developer/project/get-started-with-rayneo-x3-pro-ar-development) links the official development resources and distinguishes Android and Unity development paths.

## 3. Prepare a known-good backend and controlled test objects

**Question:** Are the server and test data ready, independently of the glasses camera?

1. Start or reuse the backend. On the Linux server, check the port first; 5173 is reserved for another project:

   ```bash
   ss -lnt '( sport = :8000 )'
   docker compose up -d --build
   docker compose ps
   ```

   If a different service owns port 8000, choose a free `BACKEND_PORT` in `.env`. Do not interrupt that service.
2. Open `http://SERVER_LAN_IP:8000/health` from another device on the same Wi-Fi. Expect `{"status":"ok"}`. Use the actual server IP and configured port.
3. Open the companion at the same base URL. Create Alice and Bob accounts in separate browser profiles/windows.
4. As Alice, use **New marker → Register / update object** to create “Mug A”. Print its marker. Repeat for “Mug B” with a different marker. Attach each label to its own mug. Save their marker UUIDs in your local report.
5. Create three notes on A: `PUBLIC-A` (public), `PRIVATE-A` (private), and `GROUP-A` (group). Create a group owned by Alice for the third note; initially leave Bob outside it. Put no notes on B yet.
6. Confirm in the companion that Alice sees three notes and Bob sees only `PUBLIC-A` on A. B has none. Keep this dataset unchanged until step 6 so expected counts stay meaningful.

**PASS:** Companion results match the above and both printed markers resolve to distinct objects. A server/permission failure here is not a glasses capability failure. The automated [HTTP E2E workflow](DEMO.md#reproducible-software-demonstration) is an alternative for validating the backend, but it ends with Bob already in the group—remove him before using the table in step 6.

Print markers at about 65 mm wide with their white quiet zones intact. This is a starting test setup, not a proven device-specific optimum.

## 4. Confirm the glasses can reach and authenticate to the backend

**Question:** Does the actual Android application have working Wi-Fi, HTTP/TLS and authentication?

1. Connect the glasses to the same reachable LAN as the backend. Enter the server's LAN/HTTPS URL in app Settings. For a controlled LAN use the debug APK; the release build requires HTTPS.
2. Sign in as Alice on the glasses. Record success or the exact visible error.
3. In the **standard viewer**, select **Manual marker · SIMULATION**, enter A's UUID, and retrieve the three notes. The SIMULATION label should remain visible.
4. Sign out and repeat as Bob: only `PUBLIC-A` should be available.

**PASS for transport/authentication only:** Both logins and the expected retrievals work in the app. This does **not** pass camera recognition or the final physical experiment. It isolates the network path before introducing optics.

**If blocked:** Check the same URL from the companion; then check Wi-Fi client isolation, routing/firewall and app URL/build type. Do not use `localhost`, assume `ping` proves application access, or assume a device-side `curl` binary exists. Do not use `adb reverse` for the final LAN trial—it would hide whether Wi-Fi networking works. An HTTP error or failed TLS trust check is not proof the glasses lack networking.

## 5. Confirm camera access and physical QR recognition

**Question:** Can this app acquire usable frames and identify real objects through the glasses?

1. Use the standard viewer to test CAMERA permission. On the first request, deny it and confirm the app reports denial without crashing. Then grant it via the app's request or Android application settings and retry. If permission was granted previously, test denial through settings only if you want to reset that test condition.
2. Select **Start camera / scan next object**. Note the status `Scanning QR`, chosen camera ID and resolution. This app shows camera status, not a preview. Close other camera applications if acquisition fails.
3. Keep B's marker out of view. Present A's printed marker upright and approximately front-facing under ordinary indoor lighting. Record distance and lighting; move it gradually if the first position does not decode.
4. Confirm the display changes to **Mug A** and its authorized notes. Confirm the selection came from the camera, not the SIMULATION action. Acquisition stops after detection by design.
5. Select **Start camera / scan next object** again and present only B. Expect **Mug B** with no notes. Swap the mugs' positions and repeat: identity must follow the marker.
6. Test an ordinary unrelated QR, then an unregistered valid `spatial:v1:UUID` marker. The unrelated QR should not select an object; the valid unknown ID should offer registration. Generate an additional unregistered marker with `scripts/generate_markers.py` if needed. Register it through the app or companion and rescan.
7. Repeat A/B scans with rotated labels and representative viewing distances/lighting. If both markers are in view, selection is not guaranteed to choose the intended one; use one visible marker per controlled trial.

**PASS for basic recognition:** Camera-originated scans identify both physical objects correctly, retrieve the correct authorized notes and distinguish them after moving the objects. An inventory entry for a camera, or `Scanning QR` alone, is insufficient.

For demo readiness, a **proposed project criterion** is at least 9/10 successful scans per object within five seconds at your chosen working distance/lighting, with zero wrong-object associations. These numbers are a suggested acceptance target, **not a RayNeo performance claim**; agree on the course criteria before collecting formal results. Report misses/timeouts and wrong identities separately.

If scanning fails, collect:

```bash
adb -s "$GLASSES_SERIAL" shell dumpsys media.camera > hardware-runs/cameras-during-test.txt
adb -s "$GLASSES_SERIAL" logcat -d -v threadtime -s AndroidRuntime CameraManager CameraDevice > hardware-runs/camera-log.txt
```

Compare with the vendor's camera sample on the same firmware. If that sample captures but our app cannot, investigate Camera2 selection/formats/lifecycle. If frames work but QR decoding fails, investigate marker size, blur, glare, orientation and selected camera. Android's [Camera2 documentation](https://developer.android.com/media/camera/camera2) describes the low-level camera API; device-specific configuration still needs validation. Do not conclude “no camera support” from a failed QR trial alone.

## 6. Confirm multi-user retrieval and permissions on the glasses

**Question:** Does the full experiment behave correctly for two identities on physical hardware?

Use actual camera scans, not manual UUID entry. Passing the same physical device between users is sufficient; record if two separate devices are tested as well.

| Account / condition | Notes visible on A |
| --- | --- |
| Alice | `PUBLIC-A`, `PRIVATE-A`, `GROUP-A` |
| Bob before membership | `PUBLIC-A` only |
| Bob after Alice adds him to the group | `PUBLIC-A`, `GROUP-A` |
| Bob after Alice removes him and he refreshes/rescans | `PUBLIC-A` only |
| Signed-out guest | `PUBLIC-A` only |

1. Run every row. Sign out between identities; the prior user's note state must clear. In the Mercury viewer, triple tap/rescan to retrieve current data; in the standard viewer, Refresh is also available.
2. Check content, author, timestamp and visibility. Create one long public note after the table trial and verify that the wearer can read its full contents and navigate between notes. Timestamps should be generated by the backend, not entered manually.
3. As Bob, create a new public note on A using the companion (allowed baseline) or the standard app. Switch to Alice on the glasses, rescan A and verify Bob's author and note. Repeat in the opposite direction if desired.
4. Edit Bob's note as Bob in the companion and refresh on the glasses; then delete it and refresh again. Verify the observed change. The [backend tests](TESTING.md) cover direct unauthorized-ID/edit/delete probes; those checks validate the server rather than a sensor capability.

**PASS:** All rows and both users' creation/retrieval work, with zero private-content exposure to the other identity. If the backend works but this APK presents stale notes or cannot switch accounts correctly, record an application failure and fix it before the experiment.

## 7. Confirm persistence, loss of connectivity and location independence

1. Restart only our Android app, preserving its data:

   ```bash
   adb -s "$GLASSES_SERIAL" shell am force-stop org.spatial.annotations
   adb -s "$GLASSES_SERIAL" shell am start -n org.spatial.annotations/.MainActivity
   ```

   Rescan A and B. Expect the same identities and authorized notes. A valid remembered session may survive; sign in again if it expired.
2. Restart the backend from its server directory with `docker compose restart backend`, wait for healthy status, and rescan. Do **not** remove the database volume. Expect the same objects, permissions and notes.
3. Briefly disconnect the glasses' Wi-Fi, then refresh/scan. Expect a bounded error instead of a new successful result or another user's data. Reconnect and explicitly retry; retrieval should recover.
4. Put both mugs at the same location label/coordinates, then move them. Their distinct markers must still retrieve distinct objects. Enter location metadata in the companion if desired; the baseline must work without GPS permission or a phone-supplied position.

**PASS:** Stored annotations survive app/server restarts, network failure is handled and recoverable, and object identity is independent of approximate position. This proves **database/marker persistence**, not world-anchor persistence. Membership revocation cannot erase text already read; measure the next retrieval after refresh.

## 8. Confirm an independently operable, sustained demonstration

1. After setup, disconnect USB (or stop using computer-assisted input). Keep Wi-Fi connected. A companion may still author notes, but the wearer must select/scan A and B and navigate notes using available device controls.
2. Run the intended presentation sequence repeatedly for the duration you need. A proposed rehearsal is 15–20 minutes, including pauses/resumes, rescans and user changes. Record initial/final battery level, scan delays, crashes, display interruptions and any device thermal warnings. Stop if the device issues a thermal warning.
3. Optionally collect available device diagnostics before/after:

   ```bash
   adb -s "$GLASSES_SERIAL" shell dumpsys battery > hardware-runs/battery-after.txt
   adb -s "$GLASSES_SERIAL" shell dumpsys thermalservice > hardware-runs/thermal-after.txt
   ```

   Reconnect USB for collection if needed, and record the charging state. Missing thermal diagnostics are not a failure by themselves; battery temperature is not a calibrated CPU/skin-temperature measurement.

**PASS:** The wearer can independently perform viewing/object selection, and the intended rehearsal completes without a blocking failure. Record all assistance. Success only via computer clicks is an assisted prototype, not confirmation of independent glasses operation.

**Baseline decision:** If steps 1–8 pass on the recorded configuration, the glasses are demonstrated to support the required QR-based experiment. If a required gate is blocked, name that gate and the missing evidence rather than concluding that every RayNeo device is unsuitable.

## 9. Investigate IMU and 6DoF separately — optional

1. Review `sensors.txt` and the vendor's supported sensor APIs. Listing a gyroscope/rotation-vector sensor establishes advertised availability only. Confirm live samples with the official sensor sample or a diagnostic app that actually registers listeners. Our app currently does neither.
2. With a licensed, firmware-compatible SDK, build and run the **unmodified official tracking sample**, following the vendor's instructions linked by the [Qualcomm development guide](https://www.qualcomm.com/developer/project/get-started-with-rayneo-x3-pro-ar-development). Record SDK/runtime/sample versions and any missing-license/build blockers.
3. If the sample exposes poses, record timestamps and tracking validity while rotating the head, translating left/right and moving toward/away from a fixed reference. Rotation alone is 3DoF evidence; translation must produce credible positional changes to support a 6DoF claim.
4. Observe tracking interruption/recovery using the sample's documented procedure. Record jumps, drift and invalid-pose behavior. If position/validity/timestamps are not exposed or trustworthy, mark that part BLOCKED rather than inferring it from an animated scene.
5. Only after the supported path is characterized, consider the experimental native SDK procedure in [RESEARCH.md](RESEARCH.md#experimental-native-sdk-unblock-procedure). Its upstream success on another device is not a local test result.

**Outcome:** Record whether usable orientation and/or position tracking was demonstrated, through which API and on which firmware. This does not yet prove object-relative alignment or persistence. Lack of a functioning native sample may still leave a Unity route available; neither should replace the already working QR baseline prematurely.

## 10. Validate object-aligned AR and persistence — optional, implementation required

These checks cannot pass with the current prototype merely by enabling its Mercury viewer. Its panel is head-locked. First implement the calibrated renderer described in [ARCHITECTURE.md](ARCHITECTURE.md#spatial-coordinates-and-extension-boundary).

1. Obtain camera intrinsics/distortion, known physical marker size, camera-to-head extrinsics, display calibration and a usable time relationship between camera frames and head poses. Record provenance and units. Missing inputs mean BLOCKED, not “approximately calibrated.”
2. Estimate the marker pose and transform it into the runtime world frame. Verify axis directions/scale with known translations. A screen-pixel coordinate is not a 3D anchor.
3. Place a card at a known offset from a stationary marker. Rotate and translate the wearer; measure apparent/card-placement error and tracking loss. Agree on an error tolerance before trials. A card that simply stays in the same part of the display is head-locked.
4. Briefly remove the marker from view and test the declared tracking behavior; then reintroduce it. Avoid presenting a frozen stale pose as valid tracking.
5. Restart the app/device and test again. A claim of persistent world anchors requires implemented relocalization into the same reference frame. Finding the QR again and reading the database is a different, already-supported persistence mechanism.
6. For shared spatial alignment, repeat with a second physical device and demonstrate a shared frame/alignment procedure. Two accounts on one device do not establish cross-device spatial calibration.

**Outcome:** Distinguish usable 6DoF, object-relative placement, same-session world tracking, cross-restart relocalization and cross-device alignment. Pass each only with measured evidence. These extensions remain NOT IMPLEMENTED in the delivered prototype.

## Copyable report template

Save as `hardware-runs/report.md`. Begin every status as NOT TESTED; replace it only after running that gate.

```text
Date / tester:
Physical model / region:
OS build / Android API:
App git commit / APK SHA-256:
Build: standard or Mercury; AAR version if used:
Backend URL / version (no passwords/tokens):
Input method / assisted setup / assisted runtime:
Marker printed width / distance / lighting:

1  ADB / device identity: NOT TESTED; evidence:
2  Install / readable display / controls: NOT TESTED; evidence:
3  Backend and controlled dataset: NOT TESTED; evidence:
4  On-device LAN/auth (manual diagnostic): NOT TESTED; evidence:
5  Camera / real QR / two-object identity: NOT TESTED; evidence:
6  Two-user creation/retrieval / permissions: NOT TESTED; evidence:
7  Restart / reconnect / location independence: NOT TESTED; evidence:
8  Independent use / sustained rehearsal: NOT TESTED; evidence:
9  Optional live IMU / 6DoF: NOT TESTED; evidence:
10 Optional calibrated AR / relocalization: NOT TESTED; evidence:

Scan trials: object, distance, lighting, attempt, correct ID, latency, failure reason
Baseline decision: NOT YET ESTABLISHED
Optional AR decision: NOT YET ESTABLISHED
Remaining blockers / next diagnostic:
```

Record exact failures, SDK versions and observed behavior. Preserve the separation between capability inventory, a working API/sample, and the actual end-to-end experiment.
