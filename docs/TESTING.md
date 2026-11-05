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
