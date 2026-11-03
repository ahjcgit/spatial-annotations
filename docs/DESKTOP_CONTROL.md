# Use a computer keyboard with the glasses

Use scrcpy to click and type into Spatial Notes from a desktop window, including
server setup, sign-in, object registration, annotation creation, and manual marker
entry. USB must stay connected. The app remains installed on the glasses; switching
computers does not require rebuilding it.

## Setup on another computer

1. Install Python 3, [Android platform-tools](https://developer.android.com/tools/releases/platform-tools),
   and [scrcpy](https://github.com/Genymobile/scrcpy#readme) from their official sources.
   Put `adb` and `scrcpy` on PATH. The original setup used scrcpy 5.0.1.
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

The launcher wakes the device, opens the installed app, and starts scrcpy with a
simulated physical keyboard. Click a field in the desktop window and type normally.
If the Android keyboard still appears, use Android's physical-keyboard settings to
disable the on-screen keyboard while a physical keyboard is connected. See the
[scrcpy keyboard guide](https://github.com/Genymobile/scrcpy/blob/master/doc/keyboard.md).

For a fresh device, build and install the APK using the [Android setup guide](RAYNEO_SETUP.md).
APKs and local SDK installations are not committed. The backend URL must be reachable
from the glasses; the companion web interface also supports editing notes on a computer.

## Black window

During the first physical test, ADB recognized scrcpy's keyboard, but a later
screenshot was black and Android reported `mWakefulness=Dozing` and display state
`OFF`. Keyboard detection alone does not prove that desktop video works.

Keep the glasses awake/worn and rerun the launcher. To check manually:

```bash
adb -s YOUR_SERIAL shell input keyevent KEYCODE_WAKEUP
adb -s YOUR_SERIAL shell am start -W -n org.spatial.annotations/.MainActivity
adb -s YOUR_SERIAL shell dumpsys power
adb -s YOUR_SERIAL shell dumpsys display
```

If the display is on but the desktop window is still black, try software decoding
with scrcpy 5.x:

```bash
python3 scripts/control_glasses.py -- --hwdec=disabled
```

Check `scrcpy --list-displays` for other displays; pass `-- --display-id=ID` to the
launcher if needed. Further [video troubleshooting options](https://github.com/Genymobile/scrcpy/blob/master/doc/video.md)
include listing encoders and choosing a different encoder. These are diagnostic
options, not verified fixes for this firmware. A different computer may help with
desktop rendering but will not fix an asleep glasses display.
