# Run the label-judge experiment

The experiment asks whether an advanced vision model can correct a tracker's suggestion, withhold a note when the evidence is weak, and request a useful second view. Each judgment concerns one yellow-outlined region. One take contains several checkpoints. The runner operates on recorded images and does not modify the Android app, accounts or notes. The [study design](VLM_LABEL_JUDGE_STUDY.md) defines the six manipulations. The [executed pilot](../experiments/context-labels/judge-pilot/README.md) includes the actual decisions and timings.

### 1. Reproduce the archived pilot on your laptop

From the application checkout on branch `analysis/codex-glasses-results`, use Linux and the project's Python 3.11 environment. On a fresh checkout:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-identity.txt
J=scripts/label_judge_study.py
PY=.venv/bin/python
D="artifacts/judge-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$D"
"$PY" "$J" archive --study "$D/archive"
"$PY" "$J" seal --study "$D/archive"
"$PY" "$J" score --study "$D/archive" \
  --run experiments/context-labels/judge-pilot/run --out "$D/saved-report"
cat "$D/saved-report/report.md"
```

This recomputes the scores from saved decisions. It needs no glasses, keys or inference. To execute every arm with a deterministic mock:

```bash
"$PY" "$J" run --study "$D/archive" --provider mock --max-calls 200 --out "$D/smoke"
"$PY" "$J" score --study "$D/archive" --run "$D/smoke" --out "$D/smoke-report"
```

For the second-look replay, use `archive --link-reveal` in a fresh study directory, run `seal`, and score the committed `experiments/context-labels/judge-pilot/second-look-run`. This links the recorded swap, cover and reveal checkpoints. Each second image has its own truth and timing.

### 2. Collect six practice takes and 30 held-out takes

```bash
"$PY" "$J" init --split development --study "$D/practice"
"$PY" "$J" init --study "$D/field"
```

1. Follow the [operator sheet](../experiments/context-labels/temporal-judge/next-takes.csv). The field scaffold creates 90 opportunities: start, challenge and reveal in each take. The practice scaffold selects one take per condition. Record practice and evaluation independently. Use the same gallery of three cropped photographs per enrolled body (`refs/A-1.jpg` through `B-3.jpg`). Leave the third body unenrolled.
2. Declare a **focal region** for each checkpoint before inference. For a substitution, outline the replacement. For an empty/absent control, outline the place a stale note could appear. Do not choose a region based on a model result. Record the actual body using a hidden underside ID or witness log. Separately record whether the available visual evidence supports displaying its note.
3. Obtain stills from the [RayNeo bench](CODEX_GLASSES_BENCH.md), from prerecorded video, or from the existing camera dashboard. With that dashboard already connected, a real capture can be saved using the following command:
   ```bash
   "$PY" scripts/vlm_camera_probe.py --dashboard http://127.0.0.1:8014 \
     --capture-only --out "$D/capture-001"
   ```
4. Import each actual image with its own capture time relative to the take start, pixel box in upright image coordinates and operator truth. Below is the command shape; replace coordinates, body and times with the observation:
   ```bash
   "$PY" "$J" collect --study "$D/field" --case s1-t01-1 \
     --image "$D/capture-001/source.png" --time-ms 0 \
     --box 96 15 185 295 --body B --identifiable yes
   ```
   For a video frame, replace `--image ...` with `--video take.mp4 --at-ms 3600`. Set `--time-ms` to its time on the take clock. For a hidden B use `--body B --identifiable no`. Use `C` for an unregistered replacement and `none` for background. Record `--deadline-ms` as the **elapsed interval after this capture** until its placement becomes invalid. Omit it if unknown. Never infer a wearer deadline from the previous pilot's median latency.
5. Use `--prior CASE` for the last verified earlier view in this take (`--prior none` to omit). Use `--second CASE` at a challenge if a later, separately captured view was made available for an extra look. A second view is never included in the initial model input. For continuous tracking comparisons, use `--continuous` and add `"trail": [{"time_ms": 180, "image": "images/intermediate.jpg"}]` to the public case before sealing. Use at most eight intermediate views from the same stream between the verified prior and the current frame. The continuity option requires intervals of at most 250 ms throughout; the rule limits which visual evidence may be used. A pair of distant stills cannot qualify. The `gap` control omits these intermediate views.
6. Check `observations.json` and the separate `truth.json`, then run `seal` on each directory. The seal hashes the gallery, current and contextual images, public manifest, and answer key. Revisions require a fresh study copy and a documented change. Keep captures and private truth in the ignored artifacts directory. The inference runner only reads the public inputs and seal. The scorer joins truth afterward.

### 3. Run the comparisons

```bash
"$PY" "$J" seal --study "$D/practice"
"$PY" "$J" seal --study "$D/field"
"$PY" "$J" calibrate --study "$D/practice" --out "$D/gates.json"
```

Calibration uses the existing color-grid descriptor and independent genuine/impostor examples. If those scores overlap, the command reports that the gallery cannot separate the objects. Omit `--calibration` in that case. The local matcher can still propose its nearest alias for challenge trials. Local label acceptance remains disabled until development examples support a gate. The protected evaluation set never supplies thresholds.

| Arm | What changes |
|---|---|
| `local` | Local gallery features and calibrated acceptance. The motion/appearance tracker records track ID and generation over successive checkpoints. |
| `direct` | Gallery and current scene, free of a tracker suggestion. |
| `review` | Same pixels, with the local candidate genuine, flipped A↔B, or withheld. A flipped hint can accidentally be correct; the scorer uses the sealed key. |
| `temporal` | Adds verified previous view, elapsed time, observation gap, and optional intermediate views. |
| `duplicate`, `stale`, `gap` | Repeat current-image content using the same panel sizes; use the oldest same-take view; or withhold intermediate views and declare a gap, respectively. |
| `adaptive`, `fixed-look` | Adaptive skips review on a stable, calibrated association and uses at most one requested extra image per initial decision. Fixed-look reviews every checkpoint and takes every offered extra image. A second read cannot rewrite an earlier answer. |

The `interactive` provider prints an opaque ID, an image path and the exact prompt. Inspect the card and paste one line of JSON containing that ID, an alias (`A`, `B`, or null), support, action, cue and source. Example response:

```json
{"request_id":"<printed-id>","alias":"B","support":"part","action":"request_view","cue":"Only the hinged cap is visible above the bag.","source":"current"}
```

The stateless API adapter uses one fresh chat request per decision. The historical conversational pilot reused a session. For a blinded replication, use an authorized endpoint and record a specific model revision. The endpoint receives the rendered card and prompt. It does not receive the filename, task condition, answer key, note text or study plan. Use a short smoke run before allocating the field budget:

```bash
export IDENTITY_FRONTIER_ENABLED=true
export IDENTITY_FRONTIER_AUTHORIZED=true
export IDENTITY_FRONTIER_ENDPOINT='https://YOUR-ENDPOINT/v1'
export IDENTITY_FRONTIER_MODEL='YOUR-PINNED-VISION-MODEL'
read -rs -p 'Provider key: ' IDENTITY_FRONTIER_API_KEY
export IDENTITY_FRONTIER_API_KEY
"$PY" "$J" run --study "$D/field" --provider frontier \
  --cases s1-t01-2 --arms direct review temporal --variants genuine flipped withheld \
  --max-calls 7 --out "$D/field-smoke"
```

For the complete comparison remove `--cases`, select the desired arms and up to three `--repeats`, and set an explicitly budgeted call limit. Pass `--calibration "$D/gates.json"` when available. Paid calls are opt-in. The cap includes second looks, invalid responses and timeouts; budget-exhausted jobs remain in the report. A local OpenAI-compatible endpoint uses `--provider local-api` and `IDENTITY_LOCAL_ENABLED`, `IDENTITY_LOCAL_ENDPOINT`, `IDENTITY_LOCAL_MODEL` and optional `IDENTITY_LOCAL_API_KEY`. The timeout and per-million token price variables follow the [existing provider conventions](IDENTITY_H0_H4.md). The worker processes recorded requests sequentially.

For the detector pass, cache the pinned model's outputs once and reuse them across all arms:
```bash
"$PY" scripts/setup_vision.py  # when NanoDet weights are absent
"$PY" "$J" detect --study "$D/field" --model nanodet --label bottle --out "$D/detections.json"
"$PY" "$J" run --study "$D/field" --provider mock --cache "$D/detections.json" \
  --max-calls 200 --out "$D/detector-check"
```

The runner matches the designated focal region to the best same-category detection at IoU ≥ 0.50. This tests label decisions at planned opportunities. It does not measure false positives outside those regions or continuous scene-wide detector precision.

### 4. Score the result

```bash
"$PY" "$J" score --study "$D/field" --run "$D/field-smoke" --out "$D/field-report"
```

Open `report.md`, `decisions.csv`, `by-take-and-condition.csv`, and `summary.json`. The raw `events.jsonl` retains each proposal, cue, candidate actually shown, action, request ID, timing, CPU, memory, usage, cost if priced, and failures. JSON null marks unavailable measurements. CPU is time used by the local process. Elapsed time includes cached local preprocessing and, on the detector pass, the recorded detector duration. Request latency can include throttling or interactive review. Image bytes are prepared JPEG bytes. Uninstrumented provider resources and optical latency cannot be inferred from these.

For actual wearer measurements, add `--wearer wearer.csv` to scoring. Use columns `request_id,capture_to_commit_ms,capture_to_selection_ms,displayed_alias,selection` keyed to that decision. Record elapsed capture-to-software-commit and elapsed capture-to-wearer-selection on the same clock, the alias actually shown (`A/B/none`), and which hidden-ID body the wearer selected (`A/B/C/none/unreadable`). Keep missing rows missing. The scorer reports offline correctness by deadline and measured wearer correctness separately. This tool prepares offline decisions; showing an accepted production UUID and resolving its notes still runs through the existing authenticated application.
