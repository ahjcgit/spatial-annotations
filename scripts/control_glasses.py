#!/usr/bin/env python3
"""Control the installed Android app with a desktop mouse and keyboard."""
import argparse
import os
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="ADB serial (required if multiple devices are connected)")
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"), help="ADB executable")
    parser.add_argument("--scrcpy", default="scrcpy", help="scrcpy executable")
    parser.add_argument("scrcpy_args", nargs=argparse.REMAINDER, help="Extra scrcpy options after --")
    args = parser.parse_args()
    adb = shutil.which(args.adb)
    scrcpy = shutil.which(args.scrcpy)
    if not adb or not scrcpy:
        parser.error("Install Android platform-tools and scrcpy; add them to PATH or use --adb and --scrcpy.")
    devices = subprocess.run([adb, "devices"], check=True, capture_output=True, text=True)
    ready = [line.split()[0] for line in devices.stdout.splitlines()[1:]
             if len(line.split()) >= 2 and line.split()[1] == "device"]
    serial = args.serial
    if serial is None:
        if len(ready) != 1:
            parser.error("Connect and authorize one device, or select one with --serial. Run adb devices -l to check.")
        serial = ready[0]
    if serial not in ready:
        parser.error("Selected device is not connected and authorized. Check adb devices -l.")
    subprocess.run([adb, "-s", serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP"], check=True)
    launch = subprocess.run([adb, "-s", serial, "shell", "am", "start", "-W", "-n",
                             "org.spatial.annotations/.MainActivity"], check=True,
                            capture_output=True, text=True)
    print(launch.stdout, end="")
    if "Error" in launch.stdout + launch.stderr:
        parser.error("Could not launch Spatial Notes. Install the APK first; see docs/DESKTOP_CONTROL.md.")
    extra = args.scrcpy_args
    if extra[:1] == ["--"]:
        extra = extra[1:]
    env = dict(os.environ, ADB=adb)
    return subprocess.call([scrcpy, "--serial=" + serial, "--keyboard=uhid", "--no-audio",
                            "--window-title=Spatial Notes - glasses control", *extra], env=env)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        sys.exit(f"Device command failed (exit {exc.returncode}). Check the USB connection.")
    except KeyboardInterrupt:
        sys.exit(130)
