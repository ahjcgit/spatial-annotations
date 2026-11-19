# Codex → RayNeo snapshot pilot — November 19, 2026

Six physical-camera trials reached a matching Android frame-commit acknowledgement:
four with two bottle labels and two no-bottle scenes with no labels. Three failed
attempts are retained. The wearer confirmed **A = silver bottle, B = orange bottle**.
The four earlier qualitative snapshots are archived separately; they did not send
labels to the glasses and have no measured Codex inference latency.

## Inspect on a server, without the glasses

From the `spatial-annotations` repository root:

```bash
python3 -m http.server 8029 --bind 127.0.0.1 --directory experiments/codex-glasses/2026-11-19
```

Open **http://localhost:8029/report/**. For a remote server, forward its port:
`ssh -L 8029:127.0.0.1:8029 USER@SERVER`. The report includes source frames,
approximate image-space boxes, short visual rationales, device screenshots,
filterable successes/failures, timing plots, and downloadable raw traces.
Everything is static; no model, credentials, browser build, or device is needed.

To regenerate the analysis from preserved evidence:

```bash
python3 -m venv .venv-analysis
.venv-analysis/bin/pip install matplotlib==3.10.8
.venv-analysis/bin/python scripts/analyze_codex_bench.py \
  --runs experiments/codex-glasses/2026-11-19/setup-diagnostics \
         experiments/codex-glasses/2026-11-19/small-text \
         experiments/codex-glasses/2026-11-19/large-text \
  --out experiments/codex-glasses/2026-11-19/report
```

The analyzer checks source-image hashes, request/hash association with device
acknowledgements, and the sum of host timing stages. CSVs and JSON contain raw
precision. Plots and the browser report round only for presentation. `manifest.json`
contains evidence-file hashes and final source-file hashes; regenerated chart/HTML
bytes can differ by environment, so preserve the original archive for comparison.

## What was actually measured

1. A debug Android activity captured one color frame after a 600 ms warmup.
2. The host pulled the JPEG via USB ADB and verified its SHA-256.
3. Codex inspected that exact image in this conversation and returned structured
   identities, labels, approximate boxes, uncertainty, and brief visible evidence.
4. The host transferred labels and snapshot left/right cues back to the activity.
5. Android validated request ID, image hash, and age, then drew a fixed label list
   in both eye halves. A frame-commit callback and host observation were timestamped.
6. The host saved a screenshot and sampled app/Python CPU and RSS through the hold.

Host monotonic and Android elapsed clocks remain separate. Sensor timestamps are
retained but never subtracted from either clock. `codex_assisted_review_turnaround_ms`
includes the conversation, image-view tool, and orchestration. **It is not isolated
model inference.** A frame commit is a software rendering milestone, not measured
photons. Exact remote model version, remote compute, tokens/cost, power, and optical
latency were unavailable and remain null. No mock result was substituted.

## Results

| Variant / condition | Completed | Review + tools, median | Response → commit observed, median | Device apply → commit, median | Capture → commit observed, median |
|---|---:|---:|---:|---:|---:|
| Small text / two bottles | 1 | 9.779 s | 212.7 ms | 69.5 ms | 12.827 s |
| Small text / no bottles | 1 | 14.102 s | 182.7 ms | 42.0 ms | 15.828 s |
| Large text / two bottles | 3 | 8.453 s | 184.5 ms | 29.4 ms | 10.187 s |
| Large text / no bottles | 1 | 11.586 s | 174.0 ms | 22.2 ms | 14.105 s |

For the three large-text bottle trials, review turnaround ranged **8.245–11.059 s**,
post-response delivery **184.2–229.2 ms**, and device apply-to-commit **23.5–71.2 ms**.
The final two fixed-scene repeats were approximately 10.2 s end to end. These are
descriptive observations, not evidence that changing font size improved latency.
Order, scene, warm state, review behavior, and display duration were not controlled.
P95 is withheld because the sample is too small.

In those three trials, peak sampled app RSS was **152.8–154.9 MiB** and Python bench
RSS **51.6–52.0 MiB**. During about 29–30 sampled seconds of holding bottle labels,
app CPU increments were 0.00, 0.00, and 0.01 seconds. CPU ticks have 10 ms granularity;
zero observed increments do not mean zero energy or rendering cost. The ~0.5-second
sampler cannot reliably isolate a ~0.2-second delivery stage. See
`report/phase-resources.csv`; absent intervals are null, not zero. These numbers
exclude remote inference, most host processes, GPU work, and power consumption.

### Wearer feedback and display outcome

- Small text, 10-second hold: labels changed but were difficult to read; they did
  not line up with the bottles.
- Larger text, 30-second hold, snapshot side cues: the wearer reported readable
  text, but placement remained unsatisfactory and requested box-like alignment.
- These reports apply to variants, not separately rated repetitions. The snapshot
  list has no calibrated object alignment. A desktop screenshot cannot establish
  optical readability, comfort, or spatial registration.
- Five of six completed trials recorded automatic expiry. `large-text/trial-02`
  reached a frame commit but the host did not observe expiry within its hold wait.
  Its saved status is the last commit status, not proof of the final optical state.
  The exact reason is unconfirmed. Future host code preserves the final polled
  hold status separately to make this diagnosable.

### Failures retained

| Attempt | Observation | Treatment |
|---|---|---|
| setup-diagnostics/trial-01 | ADB startup/PID lookup failed before a frame was saved | Fixed by waiting for matching capture before PID lookup; not a completed latency trial |
| setup-diagnostics/trial-02 | `not_awaiting_response`; activity launch caused pause and invalidated pending capture | Result delivery now uses a broadcast without launching the activity |
| large-text/trial-03 | `source_expired` after 137.7 s host review/orchestration delay | Retained stale-response rejection; fresh trials 04 and 05 succeeded |

The expired response includes a long orchestration interruption; it is not a slow
model-inference measurement. Successful timing summaries exclude these failed
attempts, while the inventory and report show all nine measured/setup attempts.

## Evidence inventory and provenance

| Directory | Contents |
|---|---|
| `small-text/` | Two completed trials; initial 10-second viewer; metadata and feedback |
| `large-text/` | Four completed trials plus one expired response; 30-second viewer; metadata and feedback |
| `setup-diagnostics/` | Two failed development attempts, retained separately |
| `qualitative-baseline/` | Four earlier snapshot-only reviews, including swap and partial occlusion; no measured inference or glasses delivery |
| `report/` | Reproducible per-trial CSV, phase resources, JSON summaries, PNG/SVG plots and portable HTML |

Each measured capture has the original JPEG bytes and host/device capture clocks.
Reviewed frames have proposals; completed deliveries add a device screenshot,
acknowledgement, derived metrics and process samples. Failures retain their available
evidence without invented missing fields. Boxes are assistant proposals, not
human-verified ground truth. No recognition accuracy or IoU score is asserted.

Hardware: RayNeo X3 Pro (`ARGF20`), Android 12 / SDK 32; USB ADB; Linux workstation,
8 logical CPUs; Python 3.11.18. Metadata records firmware and APK SHA-256 per run.
The final committed Android source implements the large-text viewer. The initial
small-text/setup revisions were edited during this pilot and were not separately
committed; their original APK hashes/configurations are retained, but their binaries
and exact historical source trees are not archived. Final source hashes document
the implementation shipped with this dataset, not those earlier variants.

Raw trial evidence is copied byte-for-byte from the local run directories. Server
PID/log files, credentials, virtual environments, and APK binaries are excluded.
The images are deliberately versioned here for the requested portable experiment;
ordinary generated `artifacts/` remains ignored. The earlier hosted dashboard is
a separate qualitative presentation; this report is the committed measured run.

## Next development work

1. **Object alignment:** use the retained image-space boxes for overlay iteration;
   then measure camera-to-eye mapping, per-eye offsets and distance-dependent
   parallax with the wearer. A raw camera box is not a calibrated physical anchor.
   Evaluate static alignment before adding tracking or claiming world registration.
2. **Freshness:** this snapshot path presents results from several seconds earlier.
   Add a latest-frame queue, movement-aware invalidation and a defined freshness
   budget before a live experience. The 120-second cap is only a snapshot guard.
3. **Inference instrumentation:** use an explicitly timed model endpoint and preserve
   exact model/configuration, request/response boundaries and provider usage. Keep
   it separate from conversational review measurements.
4. **Display and resources:** investigate missing expiry acknowledgement, measure
   optical presentation separately, use finer profiling for delivery, and run
   controlled longer-duration power/thermal trials.

Build/test evidence and commands are in `validation.json`; live collection is
documented in [the bench guide](../../../docs/CODEX_GLASSES_BENCH.md).
