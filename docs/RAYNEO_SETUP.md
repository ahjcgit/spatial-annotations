# RayNeo / Android setup

## Verified scope

The default app does not require proprietary files. The optional Mercury adapter is source implemented using verified API symbols, but cannot be compiled or hardware-tested here without the licensed SDK. World-space AR is not implemented. All device assertions below distinguish documentation/source evidence from project test evidence; see [FEASIBILITY.md](FEASIBILITY.md).

Target: RayNeo X3 Pro. Devices sold as “X3” must be checked by model, OS build, camera IDs and SDK version; the name alone does not establish compatibility. Record these when testing:

```bash
adb devices -l
adb shell getprop ro.product.model
adb shell getprop ro.build.display.id
adb shell getprop ro.build.version.sdk
adb shell dumpsys media.camera
```

Use a USB data cable, a computer with platform-tools, Wi-Fi shared with the backend, and two printed QR markers. The emulator tests are not glasses tests.

## Toolchain

This project pins AGP 8.7.3, Kotlin 2.0.21, Gradle 8.9, compile/target SDK 35, minimum SDK 26 and JDK 17. Install Android Studio Ladybug 2024.2.1 or a newer version supporting AGP 8.7; command-line builds do not require Studio. The [AGP 8.7 compatibility table](https://developer.android.com/build/releases/agp-8-7-0-release-notes) specifies Gradle 8.9 and JDK 17. No NDK or CMake is needed for this prototype.

Install SDK command-line tools, then:

```bash
export JAVA_HOME=/path/to/jdk-17
export ANDROID_HOME=/path/to/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"
sdkmanager --licenses
sdkmanager 'platforms;android-35' 'build-tools;34.0.0' 'platform-tools'
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug
```

Alternatively set `sdk.dir=/absolute/path/to/android-sdk` in untracked `android/local.properties`. Wrapper distribution checksum validation is enabled. The debug artifact path is exactly `android/app/build/outputs/apk/debug/app-debug.apk`; its application ID is `org.spatial.annotations` and launcher is `.MainActivity`.

The build machine's local tools are outside the deliverable at `../.toolchain/android-sdk` and `../.toolchain/zulu17.70.113-ca-jdk17.0.21.0.3-linux_x64`. Other machines should use their own installation.

## Official SDK installation (optional adapter)

The [official Android ARDK download page](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/ardk-xia-zai) lists v0.2.6 dated April 21, 2026 and states that the X-series uses this SDK line; its changelog identifies X3 Pro support beginning in v0.2.1. Confirm the firmware-compatible package with RayNeo. Do not download binaries from an unrelated application's repository merely because it contains an AAR.

1. Open that official page (or follow the Android ARDK link in the [Qualcomm guide](https://www.qualcomm.com/developer/project/get-started-with-rayneo-x3-pro-ar-development)). Accept RayNeo's SDK license and download the Android ARDK and sample. Some Feishu/English mirror links were not accessible from this environment; use the official download page in a browser if needed.
2. Extract the archive. Find `MercuryAndroidSDK*.aar` in the package/sample. Inspect the accompanying release notes and dependencies.
3. Copy **exactly one** licensed Mercury AAR into `android/app/libs/`. The supplied `.gitignore` excludes AARs. No proprietary SDK, credentials or extracted binaries are included in this project.
4. Build explicitly:

   ```bash
   cd android
   ./gradlew -PwithRayneo=true assembleDebug
   ```

   The build fails clearly if zero/multiple AARs are supplied. It switches to `src/rayneo` sources/manifest and adds the local file dependency; it does not use an invented Maven coordinate. The default build uses `src/standard` instead.
5. If the vendor release adds dependencies or changes symbols, compare its official sample and adjust the isolated adapter. Do not fix failures by fabricating stubs. This optional build has **not** been compiled here because the licensed AAR is absent.
6. Install, configure the backend and account in the standard screen, then choose **RayNeo binocular viewer**. Confirm readable identical content in both eyes, comfortable fusion and gesture direction. The adapter is head-locked, not world-locked.

The implemented API surface is `com.ffalcon.mercury.android.sdk.MercurySDK.init(Application)`, `ui.activity.BaseMirrorActivity<ViewBinding>`, `mBindingPair.updateView`, and `touch.TempleAction` from `templeActionViewModel.state`. These symbols and lifecycle collection were checked against [OpenClaw's actual activity](https://github.com/RayNeo-AI-2025/OpenClaw/blob/6802e8d8dfd63f087447f9ef7a7135ebe69e48c4/app/src/main/java/com/openclaw/app/AgentChatActivity.kt) and [application](https://github.com/RayNeo-AI-2025/OpenClaw/blob/6802e8d8dfd63f087447f9ef7a7135ebe69e48c4/app/src/main/java/com/openclaw/app/MyApplication.kt). UI-only work runs once per eye; network/state mutations run outside that callback. The optional manifest sets `com.rayneo.mercury.app=true`. Launcher classification may vary with firmware; direct `adb am start` is available.

## Developer mode, ADB and sideloading

Enable developer/ADB access using RayNeo's firmware-specific developer manual. The community [X3 setup guide](https://github.com/tropicalstream/TapInsight/blob/unipanel/FABLE_X3_STARTER_GUIDE.md) describes Settings → General → swipe left against the end of the list ten times for OS 25.8.13 and newer. This sequence is source evidence, **not tested on a device here**, and may change by firmware. Do not assume the normal phone “tap build number” gesture works. Accept the computer's USB-debugging authorization on the glasses.

```bash
adb devices -l
# Expect a serial with state 'device', not 'unauthorized' or 'offline'.
cd android
./gradlew assembleDebug
adb -s YOUR_SERIAL install -r app/build/outputs/apk/debug/app-debug.apk
adb -s YOUR_SERIAL shell am start -n org.spatial.annotations/.MainActivity
adb -s YOUR_SERIAL logcat -s AndroidRuntime CameraManager CameraDevice
```

Use the actual serial, especially if an emulator is running. If the device is missing, try a known data cable/port and the vendor's OS-specific USB driver/udev instructions. Do not globally loosen USB permissions. `scrcpy --serial YOUR_SERIAL` can help with configuration if supported; it does not prove binocular comfort.

Set the app's backend field to the server's LAN address, e.g. `http://192.168.1.76:8000` on this machine, or your HTTPS hostname. Verify `http://SERVER_LAN_IP:8000/health` from a companion browser first. Guest Wi-Fi isolation, firewalls and VPN routing can prevent access. `127.0.0.1` on the glasses is the glasses itself unless an ADB reverse tunnel is configured. The debug app supports that USB workflow; see [Desktop control](DESKTOP_CONTROL.md#backend-on-this-computer-over-usb). Emulator alias `10.0.2.2` works for a backend on the emulator host; the LAN address is also supported.

## Camera and input

The app requests CAMERA at runtime, handles denial without crashing and provides an explicit manual-marker simulation. It uses native Camera2 `CameraManager`, `ImageReader(YUV_420_888)` and supported output sizes. It does not assume camera ID `0`, sensor rotation, fixed focus mode or a vendor camera sharing service. Close other camera users before testing. Record chosen camera/resolution from the app's scanning status; test upright, rotated and poorly lit markers. QR decoding is orientation tolerant; it is not a calibrated image-to-display overlay. The camera UI shows a small grayscale aiming preview and an analyzed-frame counter. Supported capture resolution nearest 1280×960 is selected, and continuous autofocus is requested only when supported. Stopping or pausing clears the preview and reports that the camera is stopped. QR acquisition with this diagnostic build still requires physical validation.

Standard UI controls: Enter/DPAD center activates focused buttons; left/right or up/down moves between annotations; Space opens details; Back returns to settings. Touch controls and scrollable text work on ordinary Android devices. If a keyboard or OS cursor is available, use it for setup. Practical native-glasses text entry is unverified, so use the companion for longer notes.

Optional Mercury viewer mappings:

| Input | Action |
| --- | --- |
| Single tap | Scan if no annotation is selected; otherwise toggle author/timestamp details |
| Double tap | Return to standard settings/viewer |
| Triple tap | Clear selection and scan another object |
| Slide forward/back | Next/previous annotation |
| Slide up/down | Scroll long text |

Long press is deliberately unmapped because the example reports a system-level shortcut. Gesture direction, event delivery and system interception must be tested on the target firmware. The standard viewer has load-more/creation controls; the optional binocular viewer reads the first API page (up to 100 notes) and uses the companion or standard viewer for authoring.

## Head pose, IMU and spatial rendering

Android `SensorManager` can enumerate accelerometer, gyroscope and rotation-vector sensors; availability is device-dependent. IMU orientation is not positional 6DoF tracking and does not create a persistent world frame. This prototype does not register IMU listeners or synthesize head pose.

Qualcomm documents the official OpenXR **Unity** path (recommended Unity 2022.3.36f1, ARDK 1.1.2). That does not establish a native Android world-anchor API. The native experimental repository has real Kotlin/C++ APIs, but requires separately licensed OpenXR AARs and device validation. Its integration path, limitations and tested upstream firmware are recorded in FEASIBILITY.md. No experimental native SDK code is linked into this APK.

## Hardware acceptance checklist

For the complete ordered procedure, pass/fail criteria and results template, use [HARDWARE_VALIDATION.md](HARDWARE_VALIDATION.md).

Record PASS/FAIL and firmware, never prefill PASS:

- Install/start and configure LAN server; reconnect after process/device restart.
- Allow/deny/re-enable camera; enumerate cameras and verify QR decode of both physical markers.
- Log in as each user; retrieve public/private/group notes through the glasses, including after membership removal and server restart.
- Create/register from standard app or companion; rescan after moving the objects.
- Read long text, navigate notes, verify both eyes and all temple gestures with the optional AAR build.
- Check pause/resume, camera contention, Wi-Fi failure, token expiry and thermal behavior over a sustained session.
- World-space alignment/relocalization remain NOT IMPLEMENTED, even if the head-locked viewer works.
