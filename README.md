# Shared Spatial Annotations

A working course prototype for persistent notes on physical objects: unique QR labels, a Kotlin Android app, and a self-hosted FastAPI backend with private, group and public permissions. A companion web interface handles convenient typing, editing, printing and group membership.

**Implemented:** real authentication, database persistence, object registration, annotation CRUD/sharing, local QR recognition, Android screen-space viewing/creation, explicit manual simulation, companion UI, Docker deployment and automated tests. **The default debug APK builds successfully.** RayNeo-specific binocular/input integration is opt-in source code requiring a licensed Mercury AAR; it has not been compiled or verified on glasses. World-space rendering and persistent SLAM anchors are not implemented.

## Run the backend

From this directory:

```bash
# Inspect first; port 5173 is reserved for another project.
ss -lnt '( sport = :8000 )'
cp .env.example .env  # skip if you already have .env
# Set BACKEND_PORT in .env if 8000 is occupied.
docker compose up -d --build
docker compose ps
```

Open `http://YOUR_SERVER_LAN_IP:8000` for the companion, `/docs` for interactive API documentation and `/health` for health. The service binds **0.0.0.0** and stores SQLite in a persistent named volume. On the development machine the running service is **[http://192.168.1.76:8000](http://192.168.1.76:8000)**. Check the host's current IP if it changes.

No Docker alternative (Python 3.11+):

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd backend
../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

Create accounts in the companion; no default credentials exist. Local HTTP is for controlled LAN testing. See [HTTPS configuration and security boundaries](docs/ARCHITECTURE.md) for the optional Caddy deployment and release-mode HTTPS requirement. Keep `.env` and generated demo credentials out of version control.

## Build and sideload Android

Use JDK 17, Android SDK 35, build-tools 34.0.0 and the included Gradle 8.9 wrapper. Android Studio Ladybug 2024.2.1 or newer with AGP 8.7 support is suitable. Set `ANDROID_HOME` or `android/local.properties` first.

```bash
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug
adb devices -l
adb -s YOUR_DEVICE_SERIAL install -r app/build/outputs/apk/debug/app-debug.apk
adb -s YOUR_DEVICE_SERIAL shell am start -n org.spatial.annotations/.MainActivity
```

Built APK: [app-debug.apk](android/app/build/outputs/apk/debug/app-debug.apk). Generated build artifacts are ignored by Git; rerun Gradle when cloning the project. The APK is debug-signed and needs no RayNeo SDK or Play services. Enter your backend's LAN IP/HTTPS URL in Settings; there is no localhost default. Register/sign in, open Scan, allow camera access, and scan a printed marker. Unknown objects can be registered; selected objects support note creation/viewing. The **Manual marker · SIMULATION** action allows backend testing without a camera and is visibly labeled.

See [RAYNEO_SETUP.md](docs/RAYNEO_SETUP.md) for ADB/developer mode, exact proprietary SDK installation, optional `-PwithRayneo=true` build, gestures, camera limitations and hardware acceptance checks. The generic APK's display and camera behavior on actual RayNeo firmware are unverified.

## Run tests and demonstrate sharing

```bash
# From the project root, after installing requirements-dev.txt:
cd backend
../.venv/bin/python -m pytest -q
cd ..
.venv/bin/python scripts/e2e.py --url http://YOUR_SERVER_LAN_IP:8000
.venv/bin/python scripts/generate_markers.py --count 2 --output markers
```

The HTTP E2E creates two accounts and two objects, checks permissions, and leaves data for a physical demonstration. It saves local credentials/IDs in ignored `demo-data.json`; those specific objects need matching markers (see [DEMO.md](docs/DEMO.md)). The separate marker utility creates fresh IDs and `markers/print.html`; it does not register them automatically.

Verified results and honest runtime/hardware boundaries are in [TEST_RESULTS.md](docs/TEST_RESULTS.md). The core suite has **20 backend tests and 13 Android JVM tests**; Docker deployment, live HTTP sharing, persistence across container restart, the companion browser workflow, and a two-account Android emulator UI demonstration were also exercised. Emulator object lookup was explicitly simulated; Camera2 startup and QR pixel decoding were tested separately.

## Project map

- `backend/app/`: models, validation, authentication, REST API and same-origin companion.
- `backend/tests/`: authorization, validation, persistence and integration coverage.
- `android/app/`: Camera2/ZXing, HTTP/authentication, state controller, standard and optional RayNeo adapters.
- `scripts/`: printable markers and live two-user E2E workflow.
- [ARCHITECTURE.md](docs/ARCHITECTURE.md): data flow, API, permissions, coordinates and tradeoffs.
- [FEASIBILITY.md](docs/FEASIBILITY.md): researched sources/licenses, feature status and exact blockers.
- [DEMO.md](docs/DEMO.md): two users/two physical objects, expected results and failure cases.

Next steps are physical X3 Pro validation, licensed Mercury build/optical and gesture testing, and deployment hardening/migrations. Calibrated world-space tracking, markerless instance recognition, automatic GPS/proximity filtering and shared persistent anchors remain separate extensions. No proprietary SDK binaries or third-party camera-upload services are included.
