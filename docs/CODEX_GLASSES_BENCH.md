# Codex-to-glasses measurement bench

This debug-only experiment closes a real **camera → Codex-assisted review → labels
on Android** loop. It measures transport and software rendering and samples process
CPU/RSS. It does not measure isolated Codex inference, optical presentation latency,
world alignment, or remote-model resources.

The wearer confirmed A = silver bottle and B = orange bottle. Each image is actually
reviewed in the Codex conversation before a structured response is submitted. No
nested agents, model API credentials, mock provider, or automatic identity guesser
are substituted for that review.

## Run

Build and install the debug presentation package; the production app is separate:

```bash
source scripts/dev_env.sh
# On this workstation:
export JAVA_HOME=/home/ahjc/Coding/.toolchain/jdk17
export GRADLE_USER_HOME=/home/ahjc/Coding/.toolchain/gradle
export PATH="$JAVA_HOME/bin:$PATH"
android/gradlew -p android -PpresentationDemo=true testDebugUnitTest lintDebug assembleDebug
adb devices -l
adb -s YOUR_SERIAL install -r android/app/build/outputs/apk/debug/app-debug.apk
.venv/bin/python scripts/codex_glasses_bench.py --serial YOUR_SERIAL \
  --out artifacts/codex-glasses-bench/new-run
```

The bench binds localhost:8028. `--adb` accepts an explicit ADB path.
Use a fresh `--out` directory; existing evidence is never overwritten.
Allow camera permission in the debug app before collection. The new activity uses the camera
directly; the old detector backend and presentation dashboard are not part of its
inference/display path. Starting this activity pauses the old activity.

1. Wear/position the glasses and arrange the requested condition. Keep it stable
   through the snapshot; record any changes. Explain that the result is a fixed
   snapshot list, not text anchored to the physical bottles.
2. `POST http://127.0.0.1:8028/capture`. The returned object has an exact image path,
   unique request ID, and SHA-256. The camera pauses after one accepted color frame.
3. Have Codex inspect that exact image immediately. Do not do unrelated work while
   measuring review turnaround. Use the operator-confirmed reference identities and
   visible evidence; return no labels if neither bottle is visible. Preserve uncertainty.
4. `POST /submit` with the response schema below. The host transfers only the short
   labels and image-side cues to the device. It waits for a matching frame-commit
   acknowledgement, saves a screenshot, and monitors the display until expiry.
   Allow a 60-second HTTP timeout for the 30-second hold.
5. Ask the wearer to judge readability and clipping. A screenshot is not proof of
   readability through the optics. Save their report separately and do not invent
   an optical latency from a verbal response.
6. Repeat with a fresh capture. Keep misses, rejected responses, and setup failures.
   Use a new run directory after a build/configuration change.

Submission example (replace IDs, hash, boxes and descriptions using the real image):

```json
{
  "requestId": "ID_RETURNED_BY_CAPTURE",
  "sourceSha256": "SHA256_RETURNED_BY_CAPTURE",
  "labels": [
    {"identity":"A","label":"Silver bottle","uncertain":false,
     "box":[500,100,650,500],"evidence":"Silver body and narrow screw cap are visible."}
  ],
  "reasoning_summary":"Appearance supports A; no visible evidence supports B in this image."
}
```

`labels: []` is a valid abstention. Boxes are approximate visible extents, normalized
0–1000 in `[left, top, right, bottom]` order. They are saved for review, not used as
calibrated physical anchors. Left/right text on the device is derived from the box
center in the captured image and can become stale if the wearer moves.

The device rejects a wrong request ID, wrong image hash, duplicate IDs, invalid
labels, and snapshots more than 120 seconds old. This deliberately generous bound
is for the snapshot workflow, not a safe live-tracking policy. The current large-text
viewer clears labels after 30 seconds, on a new capture, or when its activity pauses.
An initial small-text variant used 10 seconds and was reported difficult to read.

## Timing definitions

All raw clocks are retained. Never subtract a host timestamp from a device timestamp.
The camera sensor timestamp is a third clock and is recorded only as provenance.

| Field | Boundary and interpretation |
|---|---|
| `host_capture_to_image_ready_ms` | Start of wake/capture orchestration to image saved and ready for Codex; includes startup and ADB. |
| `host_jpeg_transfer_ms` | Host time pulling the encoded frame from app-private storage over ADB. |
| `codex_assisted_review_turnaround_ms` | Image-ready to submit-handler receipt; includes Codex review, image-view tools, response serialization and orchestration. **Not isolated model inference.** |
| `host_submit_to_commit_observed_ms` | Response receipt through validation/file transfer/app notification to host observation of the device commit callback. Includes polling overhead. |
| `device_capture_command_to_frame_callback_ms` | Android elapsed time; includes the explicitly configured 600 ms camera warmup. |
| `device_frame_to_jpeg_ms` | Camera callback receipt to JPEG write completion. |
| `device_apply_to_draw_start_ms` | Receipt of the apply broadcast to first label draw. |
| `device_draw_recording_ms` | Wall time recording Canvas draw commands on the UI thread; not GPU execution. |
| `device_apply_to_frame_commit_ms` | Apply receipt to Android frame-commit callback on the device clock. **Not photon/optical latency.** |
| `device_frame_to_frame_commit_ms` | Camera callback to label-frame commit, entirely on the device elapsed clock. Includes the host/Codex round trip. |
| `host_capture_to_commit_observed_ms` | Host orchestration start to acknowledgement observation. Sum of host capture, review and post-response stages. |

Pure inference duration, remote GPU/RAM, provider tokens/cost, battery power, and
optical display latency remain null. The app's screenshot verifies its rendered
surface, while wearer feedback addresses readability. Neither establishes spatial
registration accuracy.

## Resources and analysis

Every 0.5 seconds the host samples Linux process CPU ticks and resident pages for
the app and Python bench. One-core CPU percent is CPU-seconds delta / sampled wall
seconds ×100. These are sampled process metrics, not machine-wide load or power.
The Python parent excludes ADB child CPU, which is reported separately. ADB sampling
adds overhead; retained labels spend most of the display hold idle. The first cold
capture can precede availability of the app PID and therefore its first sample.

Files per trial: `source.jpg`, `capture.json`, `codex-proposal.json`, `display.png`,
`result.json`, and `resources.jsonl`. Failures get `failure.json`; do not remove them
from the inventory. `run-metadata.json` records hardware, firmware, APK hash,
configuration, clock definitions, and confirmed identity references.

```bash
.venv/bin/python scripts/analyze_codex_bench.py \
  --runs artifacts/codex-glasses-bench/2026-11-19-measured \
         artifacts/codex-glasses-bench/2026-11-19-large-text \
  --out artifacts/codex-glasses-bench/report
```

The analyzer checks image hashes, request association, and host stage accounting.
It exports per-trial CSV, JSON summaries, PNG/SVG timing plots, a portable HTML
report with annotated frames and raw traces, and process resources by phase.
Phase CPU only includes adjacent samples within that phase; a delivery shorter
than the sampling interval may have no measurable CPU delta, represented as null.
Report variants
and no-label cases separately. Min/median/max are descriptive pilot statistics;
P95 is withheld below 20 observations. Repeated captures of this scene are technical
repeats, not independent trials demonstrating general recognition accuracy.

Future work: a timed inference API adapter for isolated request metrics; a latest-frame
queue and motion-aware staleness policy; calibrated camera/display mapping and wearer
evaluation before object-aligned rendering; sustained-use thermal/power measurements.

The [committed November 19 dataset](../experiments/codex-glasses/2026-11-19/README.md)
can be analyzed and served on another computer without ADB, glasses, or model access.
It also records a completed display commit whose automatic-expiry acknowledgement
was not observed. A completed trial means commit acknowledgement, not successful
optical presentation or expiry. Future runs save the final observed hold status
in `display_hold` even when expiry is not observed.
