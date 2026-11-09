# Spatial annotations experiment

A RayNeo glasses capability test for [SmartGlassProject](https://github.com/ahjcgit/SmartGlassProject).
Scan QR labels on physical objects, then create and read private, group, or public notes.
The experiment includes a Kotlin Android app, a FastAPI backend, and a browser companion.

The standard Android app freezes the recognized camera frame, highlights detected QR
feature centers, and shows authorized notes in an adjacent screen-space panel. World tracking, persistent AR anchors, and
markerless recognition are not implemented. The optional Mercury viewer needs a
separately licensed SDK and device validation.

In SmartGlassProject, this repository lives in the single `spatial-annotations/`
submodule directory. Run the commands below from that directory, or from a standalone
clone of this repository.

## Software-only demo and next hardware session

Start with [DEMO_QUICKSTART.md](docs/DEMO_QUICKSTART.md) for the non-destructive, one-command demo.
See [implementation and measured evidence](docs/IMPLEMENTATION_STATUS.md) and the
[next-day RayNeo checklist](docs/RAYNEO_NEXT_DAY_CHECKLIST.md).

## Backend and companion

```bash
# Choose a free port; 5173 is reserved for Rakazo.
ss -lnt '( sport = :8000 )'
cp -n .env.example .env
# Change BACKEND_PORT in .env if needed.
docker compose up -d --build
docker compose ps
```

Open `http://SERVER_LAN_IP:8000` (or your configured port). The server binds to
`0.0.0.0`; the companion uses the same host for API requests. `/health` checks the
service, `/docs` provides the API reference, and `/openapi.json` serves its schema.
SQLite data persists in a Docker volume. Create an account in the companion.

Without Docker, use Python 3.11+:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --no-access-log
```

HTTP is supported for local testing in debug builds. Release builds require HTTPS;
see [deployment](docs/ARCHITECTURE.md#deployment) for the Caddy configuration.

## Android

Install JDK 17, Android SDK 35, and build-tools 34.0.0. Set `ANDROID_HOME` or
`sdk.dir` in `android/local.properties`, then:

```bash
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug
adb devices -l
adb -s YOUR_SERIAL install -r app/build/outputs/apk/debug/app-debug.apk
adb -s YOUR_SERIAL shell am start -n org.spatial.annotations/.MainActivity
```

Enter the backend's LAN URL in Settings, sign in, and scan a printed marker.
The default APK needs no RayNeo SDK. For desktop keyboard/mouse setup, run
`python3 scripts/control_glasses.py` from the experiment root with ADB and scrcpy
installed; see [desktop control](docs/DESKTOP_CONTROL.md).

## Working with the experiment

- [Hardware validation](docs/HARDWARE_VALIDATION.md): device checks and a results template.
- [Android / RayNeo setup](docs/RAYNEO_SETUP.md): toolchain, sideloading, and optional Mercury viewer.
- [Two-user demo](docs/DEMO.md): accounts, QR labels, and sharing checks.
- [Testing](docs/TESTING.md): backend, Android, HTTP, and emulator checks.
- [Architecture](docs/ARCHITECTURE.md): data flow, permissions, and deployment.
- [Research references](docs/RESEARCH.md): earlier SDK investigation and spatial tracking options.

`android/` contains the client, `backend/` the API and companion, `scripts/` the
device/demo utilities, and `deploy/` the optional HTTPS configuration. Generated
reports belong in ignored `artifacts/`; APKs, SDK binaries, credentials, and local
databases stay out of Git. Dependency notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
