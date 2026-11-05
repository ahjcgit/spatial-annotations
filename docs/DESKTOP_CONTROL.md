# Use a computer keyboard with the glasses

Use scrcpy to click and type into Spatial Notes from a desktop window, including
server setup, sign-in, object registration, annotation creation, and manual marker
entry. USB must stay connected. The app remains installed on the glasses; switching
computers does not require rebuilding it.

## Setup on another computer

1. Install Python 3, [Android platform-tools](https://developer.android.com/tools/releases/platform-tools),
   and [scrcpy](https://github.com/Genymobile/scrcpy#readme) from their official sources.
   Put `adb` and `scrcpy` on PATH. Use scrcpy 5.x; the working setup used 5.0.1.
2. Clone/pull this repository. Connect the glasses with a USB **data** cable, enable
   ADB mode, and accept the new computer's debugging authorization in the glasses.
3. Check `adb devices -l`: the device must have state `device`.
4. From the repository root run:

   ```bash
   python3 scripts/control_glasses.py
   ```

   On Windows, use `python` instead of `python3`. If multiple devices are attached:

   ```bash
   python3 scripts/control_glasses.py --serial YOUR_SERIAL
   ```

   Executables outside PATH can be supplied with `--adb /path/to/adb` and
   `--scrcpy /path/to/scrcpy` (quote paths containing spaces).

The launcher wakes the device, dismisses an unsecured keyguard, and opens the
installed app on a 1280×900 virtual display with a simulated physical keyboard.
It keeps the session active and uses software decoding. Closing the window returns
the app to the glasses display. A secured lock screen still requires user unlock. Click a field in the desktop window and type normally.
If the Android keyboard still appears, use Android's physical-keyboard settings to
disable the on-screen keyboard while a physical keyboard is connected. See the
[scrcpy keyboard guide](https://github.com/Genymobile/scrcpy/blob/master/doc/keyboard.md).

For a fresh device, build and install the APK using the [Android setup guide](RAYNEO_SETUP.md).
APKs and local SDK installations are not committed. The backend URL must be reachable
from the glasses; the companion web interface also supports editing notes on a computer.

## Backend on this computer over USB

The debug app accepts `http://127.0.0.1:8000` for an ADB reverse tunnel. Release
builds still require HTTPS. Start the backend using Python 3.11 from the repo:

```bash
ss -lnt '( sport = :8000 )'  # Choose a free port; 5173 is reserved.
python3.11 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd backend
../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

Keep that terminal running. From another terminal in the repository root:

```bash
python3 scripts/control_glasses.py --usb-backend
```

Enter `http://127.0.0.1:8000` in both the app and the computer's browser.
Other computers on the LAN can use `http://SERVER_LAN_IP:8000`.
If port 8000 is occupied, start Uvicorn on a free port and run
`adb -s YOUR_SERIAL reverse tcp:8000 tcp:YOUR_BACKEND_PORT` manually, then
launch desktop control without `--usb-backend`.

The ADB tunnel forwards glasses port 8000 to the computer over USB; no glasses Wi-Fi
is needed. Repeat after reconnecting USB. The tunnel remains when the desktop window
closes, so physical scanning can use the backend while USB stays connected.

Prepare the two-account test dataset with:

```bash
.venv/bin/python scripts/e2e.py --url http://127.0.0.1:8000
```

Credentials and marker IDs are saved in ignored `demo-data.json`. Follow
[the demo guide](DEMO.md) to generate matching labels and test optical scanning.

## Black window

The physical glasses display was returning to sleep after a wake command, and
ADB screenshots were black. A desktop virtual display, wake/keyguard dismissal,
keep-active mode, and software decoding together produced a visible UI confirmed
by the user. This combination is now the default; the individual contribution of
each setting has not been isolated.

For the physical scanning stage, close the desktop setup window so the app moves
back to the glasses. Wear/wake the glasses, then open **Scan / view annotations**.
You can also run the launcher in physical-screen mirror mode:

```bash
python3 scripts/control_glasses.py --mirror
```

The glasses' physical screen must stay awake for this mirror mode. If the display
is black, check its power state and unlock it if needed:

```bash
adb -s YOUR_SERIAL shell dumpsys power
adb -s YOUR_SERIAL shell dumpsys display
adb -s YOUR_SERIAL shell input keyevent KEYCODE_WAKEUP
adb -s YOUR_SERIAL shell wm dismiss-keyguard
```

Check `scrcpy --list-displays` for other displays; pass `--mirror -- --display-id=ID` to the
launcher if needed. Further [video troubleshooting options](https://github.com/Genymobile/scrcpy/blob/master/doc/video.md)
include listing encoders and choosing a different encoder. These are diagnostic
options, not verified fixes for this firmware. A different computer may help with
desktop rendering but will not fix an asleep glasses display.
