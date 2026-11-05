# SDK research references

Historical investigation from 2026-11-01. These references do not establish
compatibility with the current glasses firmware. The working experiment uses QR
identity and screen-space notes; world tracking remains a separate experiment.

## Source and dependency investigation

The following sources were inspected on 2026-11-01. API tree SHAs below pin the inspected versions; upstream READMEs may change.

| Resource | Availability, license, actual API/build findings | Compatibility decision |
| --- | --- | --- |
| [Qualcomm X3 Pro guide](https://www.qualcomm.com/developer/project/get-started-with-rayneo-x3-pro-ar-development) | Accessible; links official Android and OpenXR Unity ARDK docs. Documents ADB, Android-native camera/gyro access, Unity 2022.3.36f1 and ARDK 1.1.2. Documentation inspected, no SDK binaries obtained. | Official spatial development evidence is Unity-oriented; it does not verify a native persistent-anchor API. |
| [RayNeo Android ARDK download](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/ardk-xia-zai) | Accessible. Lists Android SDK 0.2.6 (2026-04-21), X-series SDK, X3 Pro support from 0.2.1. Proprietary package terms must be obtained and respected. Some linked Feishu/English pages failed to load here. | Core optional device integration uses this SDK line. Default APK is independent. |
| [RayNeo OpenClaw](https://github.com/RayNeo-AI-2025/OpenClaw/tree/6802e8d8dfd63f087447f9ef7a7135ebe69e48c4) | SHA `6802e8d8dfd63f087447f9ef7a7135ebe69e48c4`. LICENSE is MIT with a separate Mercury proprietary-binary note (GitHub API labels it “Other”). Actual source uses `MercurySDK.init`, `BaseMirrorActivity`, `mBindingPair.updateView` and `TempleAction` flow. Inspected Gradle uses local libs, compile SDK 36.1, min 26 and newer Android tooling. | Its device APIs inform the isolated adapter. Its full application/build is not transplanted; no hosted proprietary binaries copied. Core MVP uses our pinned SDK 35 toolchain. |
| [Experimental native spatial SDK](https://github.com/AlexSKuznetsov/rayneo-x3-spatial-sdk/tree/f5c3ecf0a794867624efb927f6d5f4f4c71e6f59) | SHA `f5c3ecf0a794867624efb927f6d5f4f4c71e6f59`, Apache-2.0. Source has `SpatialTracking`, `PoseSample`, `WarmupGate` and scene APIs backed by C++ OpenXR. Requires JDK17, SDK35, NDK27.0.12077973, CMake3.22.1, min30/arm64 and two proprietary ARDK1.1.2 AARs. Upstream reports one X3 Pro/runtime1.1.7.9 tested and issues with tracking jumps/timestamps. | Verified as real source, not adopted. Upstream reports are not our test results; calibration/relocalization remain unresolved. |
| [xg-glass-sdk](https://github.com/hkust-spark/xg-glass-sdk/tree/c697e7faadde27762c9aa3954f6ed7e65961c28f) | SHA `c697e7faadde27762c9aa3954f6ed7e65961c28f`, Apache-2.0. `RayNeoRuntimeGlassesClient` implements Camera2 capture/video methods. Host integration needs vendor Mercury/IPC AARs; README says X2 validated, X3 Pro untested. Source tooling uses SDK36, Kotlin2.4+/AGP9.x; distributed artifacts use a different release baseline. | Adds cross-device/host complexity without validated X3 Pro spatial benefit. Not a dependency. |
| [TapInsight Unity guide](https://github.com/tropicalstream/TapInsight/blob/unipanel/FABLE_X3_UNITY_GUIDE.md) | Branch `unipanel`, inspected tree SHA `271a819b5cad64f5011278809ee5543ba8f1fffa`; repository GPL-3.0. Community guide describes Unity2022.3.36f1/ARDK1.1.2, scene setup and thermal constraints. | Research reference only; no GPL source/assets copied. Its “Unity only” assertion is narrower than the newer experimental native work, so it is not treated as proof that native 6DoF is impossible. |

### Experimental native SDK unblock procedure

For a **separate research branch**, acquire the licensed RayNeo OpenXR ARDK 1.1.2 and extract `OXR/Runtime/Plugins/Android/RayNeoSDK-client.aar` and `RayNeoOpenXRLoader.aar` into that repository's `vendor/rayneo-sdk-1.1.2/`. Follow its pinned [vendor instructions](https://github.com/AlexSKuznetsov/rayneo-x3-spatial-sdk/blob/f5c3ecf0a794867624efb927f6d5f4f4c71e6f59/vendor/README.md), which validate exact SHA-256 values. Install its required NDK/CMake and build `./gradlew :sample-scene:assembleDebug`. First validate the unmodified sample on the actual firmware; then add pose acquisition and a calibrated renderer. Do not claim metric accuracy, stable timestamps, relocalization or cross-device persistence based solely on that sample. Proprietary AARs remain outside version control and redistribution depends on RayNeo's terms.

### Marker library and other dependencies

The baseline uses the real Maven Central artifact `com.google.zxing:core:3.5.3` (Apache-2.0), verified by successful Gradle resolution/build and actual QR decode tests. Its [API documentation](https://zxing.github.io/zxing/apidocs/com/google/zxing/MultiFormatReader.html) provides `setHints`/`decodeWithState`; the [upstream release history](https://github.com/zxing/zxing/releases) shows maintenance releases. ZXing is a mature maintenance-stage decoder, not an actively expanding AR SDK. It needs neither OpenCV native binaries nor Play services. Camera frames remain local. Other shipped open-source dependencies and licenses are listed in THIRD_PARTY_NOTICES.md; the APK's dependency metadata is generated by Gradle.

