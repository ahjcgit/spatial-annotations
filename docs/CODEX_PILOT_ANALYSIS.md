# Review of the November 19 laptop / RayNeo evidence

Analysis date: November 24, 2026. Source: `experiment/codex-glasses-latency`, commit
`33666abf62b4e67117bedf75745c93e8c48b45a6`. The evidence folder is
`experiments/codex-glasses/2026-11-19/`. Its original files are unchanged.

## Open the dashboard

From the application repository:

```bash
# No dependencies, model inference or device connection required.
python3 scripts/build_pilot_dashboard.py
ss -lnt '( sport = :8029 )'  # choose another port if occupied; do not use 5173
python3 -m http.server 8029 --bind 0.0.0.0 \
  --directory experiments/codex-glasses/2026-11-19
```

Open `http://<computer-LAN-IP>:8029/dashboard/` (on this development machine:
`http://192.168.1.76:8029/dashboard/`). The generated dashboard is also committed and
can be opened directly from `dashboard/index.html` without a server: data is embedded
in a local JS file, not fetched from an API. Keep the adjacent evidence folders intact.
The source audit checks the recorded hashes against the shipped files or their blobs at the evidence commit. Keep that commit in your clone when rebuilding after code changes. The archived original report remains at `/report/`.

The dashboard provides findings, host-stage timing bars, scene filters, all 13 trial
records, proposed box overlays, device screenshots, wearer feedback, retained failures,
an artifact-gap checklist, and prioritized next steps. JSON and CSV downloads include
failures and unmeasured/null values. It does not run a model or start the glasses camera.

## What was done

This was a **physical-camera snapshot and display-delivery pilot**, using two visually
distinct bottles. A is the silver bottle; B is the orange bottle. These are experiment
labels, not persistent backend object UUIDs. It did not execute the H0–H4 comparison,
call the annotation API, or implement continuous tracking.

The measured path was Android capture → JPEG over ADB → Codex conversational image
review → short labels and snapshot side cues over ADB → Android frame-commit callback.
The camera paused after capture. The host saved the proposed boxes, but the device
received only text/side cues and drew a fixed list in each eye half. The current
`CodexProbeActivity` does not attempt object-aligned rendering. This explains the
reported placement problem without attributing it to an unmeasured optical defect.

Inventory, verified against the actual files:

- Nine measured/setup attempts: six completed frame-commit acknowledgements and three
  retained failures. Four completed trials proposed two bottle labels; two proposed none.
- Four earlier image-only reviews: initial view, position swap, partial occlusion,
  reappearance. These did not deliver labels to the glasses and have no measured review
  latency. Their occlusion trial also retains one failed camera-start capture retry.
- Twelve source photographs, six device screenshots, four earlier annotated previews,
  and an archived timing plot. All 81 manifest-listed files match their SHA-256 values;
  all six recorded source-file hashes match the imported code.
- 257 audit checks pass: hashes, request/image associations, completed-trial artifacts,
  raw-clock recomputation, inventory, and agreement with the original timing CSV.

## What the measurements say

Descriptive statistics over the six **completed** trials; failures are kept separately:

| Measurement | Median | Range | Boundary |
|---|---:|---:|---|
| Capture request → commit observed | 13.43 s | 10.15–15.83 s | Host monotonic clock, includes orchestration |
| Review + tools | 10.42 s | 8.25–14.10 s | Image-ready → submit-handler receipt |
| Response → commit observed | 184.4 ms | 174.0–229.2 ms | Host receipt, transport, notification and polling |
| Device apply → frame commit | 35.7 ms | 22.2–71.2 ms | Android elapsed clock only |

Review/tools account for **81.97% of summed host elapsed time** (sum of review durations
divided by sum of end-to-end durations). That is neither the ratio of medians nor an
isolated inference measurement. The device interval is nested inside delivery and must
not be added to the host stages. Sensor, host and device clocks are never subtracted
from one another. P95 is withheld; there are too few samples.

The last two large-text bottle repeats were about 10.2 seconds end to end. That does
not prove large text made the system faster: order, warm state, scene, review behavior,
text size, side cues and hold duration were not independently controlled.

Wearer feedback says small text was difficult to read and larger text was readable,
but placement was unsatisfactory. These are variant-level reports, not six independent
readability ratings. The screenshots show software content, not optical alignment,
binocular comfort or photon timing.

Five completed trials include an automatic-expiry acknowledgement. `large-text/trial-02`
has a frame commit but no observed expiry. Its final hold status was not retained by the
collection version; the host code was subsequently amended. We cannot infer that labels
remained visible or identify the cause from the saved result alone.

The rejected `large-text/trial-03` response followed 137.71 seconds of review/orchestration
delay. It exercised the 120-second source-age guard. It is not a model-inference outlier.
The other two failures were capture startup/PID handling and activity lifecycle invalidation
(`not_awaiting_response`); subsequent code addressed these paths.

## Specific files that may still be on the laptop

**The declared 81-file archive is complete.** The omissions below were found by comparing
other documentation and file references with the Git tree. “Absent” means not included
in this checkout/archive; it does not assert that the file was never saved on the laptop.

| Priority | Referenced artifact | Evidence that it existed / current status | Needed for |
|---|---|---|---|
| Optional historical comparison | Actual Qwen run folder under `artifacts/vlm-probes/` | `docs/VLM_CAMERA_PROBE.md` says its first response took 44.35 s, with false cup/laptop proposals, and that output/review were retained. No corresponding raw run is committed. The actual directory name is not stated. | Verify Qwen output, request latency and errors; compare only after matching image/task/timing boundaries |
| First | `artifacts/vlm-probes/session-2026-11-19/codex-frame-01/` | The same guide explicitly names four files: `source.jpg`, `capture.json`, `codex-result.json`, `codex-labels.png`. None is included here. This is distinct from `bottle-trials/`. | Recover the first Codex review and input provenance |
| With Qwen | `/home/ahjc/Coding/.toolchain/vlm/provenance.json` | Guide names it as the runtime/model revision, URL, size and SHA-256 record; it is outside Git. | Verify the reported llama.cpp b12554 / Qwen3-VL-2B Q4_K_M configuration |
| Useful | `large-text-build.log` | `validation.json` says “BUILD SUCCESSFUL in large-text-build.log”; the log itself is absent and its full parent path is not recorded. | Independently inspect the historical build/lint output rather than its summary |
| Useful | Original measured APKs and small-text source snapshot | README explicitly excludes binaries and says the earlier variants were not separately committed. Metadata preserves APK hashes. | Exact historical reproduction; not required for present timing analysis |
| If retained | Host bench logs or device logcat around `large-text/trial-02` | Expiry was not observed. `display_hold.last_device_status` was added **after** collection and is missing in this archived result. No specific log filename is promised. | Diagnose the unobserved expiry; otherwise repeat with the amended logger |

For the Qwen folder, look for `source.png`, `input.jpg`, `response.json`, `result.json`,
`proposals.png`, and any separate saved visual review. The guide's `my-first-frame` and
`my-photo` commands are examples, not evidence of the actual directory name. Do not
rename an example into a purported real run. The 44.35-second figure remains an
unverified documentation claim in this review and is not in the verified timing chart.

Useful laptop inventory commands (read-only, do not print credentials):

```bash
# From your laptop's spatial-annotations checkout; ignored artifacts will still appear.
rg --files --hidden --no-ignore artifacts/vlm-probes artifacts/codex-glasses-bench \
  -g '*.json' -g '*.jsonl' -g '*.png' -g '*.jpg' -g '*.log'
rg --files --hidden --no-ignore artifacts -g '*build*.log' -g '*.apk'
ls -l /home/ahjc/Coding/.toolchain/vlm/provenance.json
```

Do not force-add the whole `artifacts/` directory, credentials, toolchains or model
weights. Copy the relevant run folder and provenance into a new sibling evidence
directory with a small README describing their origin; preserve bytes and the existing
November 19 archive. Alternatively provide those selected files in a separate archive.

The `qualitative-baseline/trial-summary.json` paths under
`artifacts/vlm-probes/bottle-trials/trial-*/codex-result.json` are **not missing results**:
their four corresponding files are already preserved under `qualitative-baseline/`.
The audit resolves these old local paths rather than treating them as omissions.

## Measurements that cannot be reconstructed from these files

- Exact Codex model/version, complete prompts/reference context and API usage/cost are
  not recorded. This was conversation review, not an isolated API timing experiment.
- No independently reviewed identity/box ground truth exists here. Visual inspection
  agrees with the obvious silver/orange scene descriptions and the partial-occlusion
  uncertainty, but that is not an independent accuracy benchmark. Approximate boxes
  should not be scored against themselves.
- No continuous video, tracking output or H0–H4 real-sequence results is included.
  Snapshot swap/reappearance observations do not measure tracking identity switches
  or recovery delay.
- No camera-to-eye calibration, optical presentation timing, battery power, thermal
  trajectory or remote-model memory is measured. Process RSS/CPU samples do not supply
  these missing quantities. Device screenshots cannot substitute for optical tests.

## Next steps, with a decision at each stage

1. Run the [same-model object session](CONTEXT_LABEL_GLASSES_SESSION.md). The [paired crop and scene experiment](../experiments/context-labels/2026-11-24/README.md) recovered three previously ambiguous regions in the archived frames. Test whether the same approach carries across viewpoints and rejects a third lookalike. The missing local-model files are optional for this question.
2. Implement camera-space overlays as an image association feature. Separately measure
   camera-to-eye mapping/per-eye offsets and distance effects before promising aligned
   see-through labels. Record static placement error and wearer readability.
3. Use an explicitly timed local or authorized hosted inference adapter on the same saved
   images. Record runtime/model/weights, input resolution, request/response boundaries,
   failures and usage. Define a freshness budget and movement invalidation before live use.
4. Run controlled persistent-identity experiments with separate references/development/test
   data and human-reviewed identities/boxes. Compare H0–H4 using matched inputs and report
   per-recording coverage, wrong-object labels, recovery latency and cost. Distinct-colored
   bottles are an initial sanity check; they do not establish similar-laptop discrimination.
5. Repeat the no-label display/expiry case with final status and lifecycle logs saved.
   Record wearer feedback per trial. Profile sustained power/thermal behavior only once
   the display loop is stable.

**Research conclusion:** the physical snapshot-to-device path worked in this pilot.
Whether visual reasoning improves object-specific annotation correctness enough to
justify its latency and cost is still unanswered.

## Verification of this dashboard

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests scripts/tests -q
.venv/bin/python scripts/pilot_dashboard_smoke.py \
  --url http://127.0.0.1:8029/dashboard/ --out artifacts/codex-results-review/browser
```

Baseline on the imported branch: 98 Python tests passed, one existing Starlette/AnyIO
deprecation warning. The dashboard adds six tests for the real inventory, independent
clock domains, missing artifacts, tampered derived metrics, archive preservation and
overwrite protection. Browser checks exercise filters, failure/uncertain states, box
visibility, expiry status, file links and narrow-screen layout. No new hardware or paid
inference run is claimed by this analysis. Android source is unchanged in this branch.

Final checks: **104 Python tests passed**, the same one warning; **six Chromium browser
checks passed**, no page errors, all 75 tested file URLs returned HTTP 200, and the 390px
layout had no horizontal page overflow. Browser checks caught and fixed SVG box-toggle
visibility. The original analyzer was rerun into a separate ignored directory; its
summary, six-row trial CSV and 38-row resource CSV match the archived analysis.

The manual design detector flagged long prose lines; measures were narrowed. Independent
visual review requested that the two mobile narrative tables stack their rows, keeping
conclusions and failure interpretations visible. That fix was applied and recaptured;
the reviewer scored it resolved with disposition `ship`. The portable `file://` page was
also checked independently of the server.

Local verification logs/screenshots are under `artifacts/codex-results-review/` and are
ignored by Git. The portable dashboard and its audited JSON/CSV are committed beside
the archive; regenerate them with the build command above. Python source checks and
`git diff --check` pass. No changes were made to the original 81 archived files.
