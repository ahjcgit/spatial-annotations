# H0–H4 persistent-object identity experiment

This opt-in Python workflow compares identity methods on recorded images. It reuses
the existing detector adapters, physical-object UUIDs, reference gallery, asynchronous
identity controller, and authenticated annotation API. The Android single-bottle demo
is unchanged. Labels are associated with image boxes, not world anchors.

Read [executed results](IDENTITY_H0_H4_RESULTS.md) before presenting accuracy claims.
No genuine two-laptop benchmark or real VLM measurement has been completed.

## Run the software demonstration

From the application repository, on branch `experiment/h0-h4-identity`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-identity.txt
# Alternatively: uv pip install --python .venv/bin/python -r scripts/requirements-identity.txt
export IDENTITY_EXPERIMENT_ENABLED=true
.venv/bin/python scripts/identity_suite.py fixture --out artifacts/laptops/fixture

# These gates and the generous call budget are for the synthetic software check only.
IDENTITY_ACCEPTANCE=corroborated IDENTITY_VLM_REQUESTS_PER_MINUTE=100 \
  .venv/bin/python scripts/identity_suite.py suite \
  --dataset artifacts/laptops/fixture/dataset.json \
  --gallery artifacts/laptops/fixture/gallery.json \
  --calibration artifacts/laptops/fixture/calibration.json \
  --initializations artifacts/laptops/fixture/initializations.json \
  --mock --passes A --pace 1 --out artifacts/laptops/results

ss -lnt '( sport = :8026 )'
.venv/bin/python scripts/identity_suite.py serve \
  --dataset artifacts/laptops/fixture/dataset.json \
  --results artifacts/laptops/results --port 8026
```

Open `http://<computer-LAN-IP>:8026`. The development machine currently uses
`http://192.168.1.76:8026`. The server binds `0.0.0.0`, refuses occupied ports, and
reserves port 5173 for the unrelated application. Choose another free port if needed.
Use a new output directory for each suite; existing experiment data is not reset.

Select a recording and H0–H4 run, play or scrub frames, and enable ground truth to
review errors. Track IDs, accepted UUIDs, proposals, states, matching methods and
completed reasoning events are separate. Unknown tracks have neutral labels.
Ground truth is hidden by default. The fixture uses colored rectangles, not laptop
photographs. It validates execution paths, not real object recognition.

Pass B uses the existing detector, shared across all five methods:

```bash
# Only if the pinned detector weights are absent:
.venv/bin/python scripts/setup_vision.py
# Add --yolox to that command if evaluating YOLOX-S as well.
# Repeat the suite command with --passes A B and a new --out directory.
# Use --detector yolox_s for a separate YOLOX-S comparison.
```

Rectangles are not detector-positive laptop examples. Detector misses in this fixture
are expected and count as abstentions; do not report them as a laptop detector benchmark.

## What each method does

| Method | Identity evidence | Reasoning |
|---|---|---|
| H0 | Explicit operator initialization, motion-predicted IoU, area consistency, previous association | None |
| H1 | Same geometric tracker plus reference-gallery cosine matching | None |
| H2 | H1 plus unresolved-event recovery | Configured local vision endpoint |
| H3 | H1 plus unresolved-event recovery | Explicitly authorized frontier endpoint |
| H4 | H1, then local recovery; optional frontier escalation if still unsupported | Common provider interface |

All five methods use the same geometric tracker in this suite. H0 never encodes image
appearance. It cannot identify an uninitialized object or recover a UUID after a new
session by itself. Optional `--initializations` supplies independently verified starting
associations to **every** method. Without it H0 stays unknown. The generated fixture
explicitly creates these seeds from its construction; real evaluation must use operator
observations, not extract identities from test ground truth.

The tracker is a replaceable greedy baseline: motion-predicted IoU >0.05 and area ratio
0.5–2 admit associations; motion extrapolation caps at 0.5 seconds. Tracks expire after
3 seconds; gaps above 1 second and overlapping boxes (IoU >=0.25) invalidate identity.
These are fixed engineering gates, not probability thresholds. Camera-motion compensation
is not implemented. [ByteTrack](https://github.com/FoundationVision/ByteTrack) was inspected;
its YOLOX/native-extension setup adds dependencies to the existing OpenCV path. This phase
retains the small modular baseline and makes no ByteTrack/BoT-SORT performance claim.

H1 uses the existing CPU `color-grid-v1` descriptor: 448 RGB grid/histogram features.
It is sensitive to lighting and viewpoint, and is not a learned instance embedding.
Optional local DINOv2 ViT-S/14 is independently replaceable, but remains untested here.
Use `--descriptor dinov2 --dino-repo <local-checkout> --dino-weights <checkpoint>` on
calibration and runs; dependencies/weights must be installed explicitly. See the
[existing adapter instructions](IDENTITY_RECOVERY.md#4-appearance-baseline-and-calibration).
Gallery embeddings, reference hashes and descriptor metadata are exported to an ignored
`embeddings/` directory beside the gallery. Features are recomputed when a run starts;
this export is provenance, not a persistent model-serving cache.

## Controller and acceptance policy

```text
recorded image → shared detections → temporary tracks → appearance/identity policy
                                                   ↓ unresolved event
                                        asynchronous ProviderHub
                                        local → optional frontier
                                                   ↓ validated proposal
                         current generation + evidence + unique assignment check
                                                   ↓ accepted UUID only
                                    existing authenticated annotation API
```

`unknown` means no supported identity; `uncertain` invalidates a previous association;
`pending_verification` means reasoning or an unaccepted proposal is outstanding;
`matched` exposes an accepted UUID. New unresolved tracks, long gaps, overlaps and
appearance conflicts trigger recovery. Routine motion, brief misses and objects outside
the field of view do not create per-frame reasoning calls.

The controller deduplicates events and limits attempts/cooldowns; ProviderHub separately
limits actual local/frontier calls and concurrency across sequences/session resets in one
runner. Tracking continues during inference. Epoch, track generation, observation age,
appearance consistency and current existence are checked before applying delayed results.
Responses for superseded observations are discarded. Unknown/invalid IDs, malformed JSON,
unsubmitted tracks and duplicate physical-object assignments are rejected. Timeout or
network failure leaves a neutral state. Recovery event logs retain cancellations/failures.

Default `IDENTITY_ACCEPTANCE=manual` keeps VLM output as a **proposal**, not an accepted
label. `corroborated` additionally requires calibrated appearance support and uniqueness.
Model confidence and prose are never proof. Calibration may use separate VLM corroboration
gates, but these must also be derived from development data. A generic model cannot grant
annotation permissions, register/overwrite objects, or execute instructions in images.

This conservative policy can limit any VLM benefit when the appearance descriptor is
inadequate. Measure proposal correctness separately, and evaluate a new acceptance policy
on development data before changing it. The viewer is a reviewer, not a manual-confirmation
editor; Python `IdentityPipeline.confirm()` is the explicit operator-confirmation hook.

## Configure local and frontier providers

No endpoint, weights, key or paid inference is required for the mock demonstration.
No nested Codex sessions are launched. A coding-agent session is not used as an inference API.

Qwen3-VL-2B-Instruct is a suggested local starting point, **not a tested dependency**.
The [official GGUF model card](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/blob/main/README.md)
documents Apache-2.0 licensing and quantizations. Preserve its license/provenance when
obtaining weights. A compatible recent llama.cpp server supports the vision projector
and [OpenAI-compatible multimodal requests](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md).
After explicitly installing that runtime and a matching model/projector pair:

```bash
ss -lnt '( sport = :8086 )'
llama-server -m /path/to/Qwen3-VL-2B-Instruct-Q4_K_M.gguf \
  --mmproj /path/to/matching-mmproj.gguf --alias qwen3-vl-2b \
  -ngl 0 --no-mmproj-offload --host 0.0.0.0 --port 8086
```

This CPU example is an installation recipe, not an executed runtime test. Record your
runtime version, weight hashes, quantization, projector, thread count and acceleration.
Confirm image input and JSON-object response support on your installed server.

```bash
export IDENTITY_EXPERIMENT_ENABLED=true
export IDENTITY_LOCAL_ENABLED=true
export IDENTITY_LOCAL_ENDPOINT=http://127.0.0.1:8086/v1
export IDENTITY_LOCAL_MODEL=qwen3-vl-2b
export IDENTITY_LOCAL_TIMEOUT_S=30
# Set IDENTITY_LOCAL_API_KEY privately only if your endpoint requires it.

# Optional frontier use: setting AUTHORIZED explicitly authorizes configured API calls.
export IDENTITY_FRONTIER_ENABLED=true
export IDENTITY_FRONTIER_AUTHORIZED=true
export IDENTITY_FRONTIER_ENDPOINT=https://your-provider.example/v1
export IDENTITY_FRONTIER_MODEL=your-vision-model-id
read -rs -p 'Frontier API key: ' IDENTITY_FRONTIER_API_KEY
export IDENTITY_FRONTIER_API_KEY
export IDENTITY_FRONTIER_TIMEOUT_S=45
```

Do not execute the placeholder frontier configuration unchanged. Disable with
`IDENTITY_FRONTIER_ENABLED=false`. H2 needs local configuration; H3 needs authorized
frontier configuration; H4 needs local and can run without frontier. Missing configuration
is reported as `not_run`, not a successful benchmark. Adapter transport is tested with
mocks; model-specific JSON/vision compatibility still needs a real smoke test.

Shared settings (inherited existing environment conventions):

| Variable | Default / meaning |
|---|---|
| `IDENTITY_VLM_CONCURRENCY` | 2 active provider calls |
| `IDENTITY_VLM_REQUESTS_PER_MINUTE` | 6 actual calls per rolling minute, including escalation |
| `IDENTITY_VLM_COOLDOWN_S` | 30 seconds per track |
| `IDENTITY_VLM_MAX_IMAGE_DIMENSION` | 640 pixels, aspect preserved |
| `IDENTITY_VLM_RESPONSE_TTL_S` | 5 seconds of observation age |
| `IDENTITY_ACCEPTANCE` | `manual` or explicitly `corroborated` |
| `IDENTITY_LOCAL_INPUT_USD_PER_MILLION`, `IDENTITY_LOCAL_OUTPUT_USD_PER_MILLION` | Optional declared prices |
| `IDENTITY_FRONTIER_INPUT_USD_PER_MILLION`, `IDENTITY_FRONTIER_OUTPUT_USD_PER_MILLION` | Optional declared prices |

H0–H4 use `IDENTITY_LOCAL_*`/`IDENTITY_FRONTIER_*` enables; the older single-provider
`IDENTITY_VLM_ENABLED` is not needed. Keep it unset when using this suite. Context defaults
are at most 4 tracks/request, 8 registered objects and 3 reference images/object. The
configuration is logged without endpoint credentials or API keys. Prompts include only
candidate UUIDs, reference images, current crops, ambiguity reason and potentially stale
tracking context. Test filenames, ground-truth mappings and annotation text are excluded.

The default 5-second TTL deliberately discards slower answers even if the HTTP timeout
is longer. For standalone offline probes, explicitly set a suitable TTL (for example
`IDENTITY_VLM_RESPONSE_TTL_S=60`) to measure a slow CPU provider's correspondence. Record
that setting and keep it fixed across compared methods. Do not silently relax the live
staleness policy to make a slow provider appear useful; evaluate its delayed-label failures.

## Register real laptops and collect data

Follow [backend startup and private login commands](IDENTITY_RECOVERY.md#2-register-laptop-a-and-laptop-b)
to set `IDENTITY_BACKEND` and `IDENTITY_API_TOKEN`. Use the existing companion to create
public/private/group notes. Register multiple manually cropped photographs per object:

```bash
.venv/bin/python scripts/identity_experiment.py register \
  --backend "$IDENTITY_BACKEND" --gallery artifacts/laptops/gallery.json \
  --name 'Laptop A' --images identity-data/references/a-front.jpg identity-data/references/a-side.jpg
.venv/bin/python scripts/identity_experiment.py register \
  --backend "$IDENTITY_BACKEND" --gallery artifacts/laptops/gallery.json \
  --name 'Laptop B' --images identity-data/references/b-front.jpg identity-data/references/b-side.jpg
.venv/bin/python scripts/identity_suite.py plan --out artifacts/laptops/collection
```

Use `--object-id <physical-object-UUID>` instead of `--name` to extend an existing object.
The marker UUID is different from the physical-object UUID. The gallery stores object
name, references/hashes, optional room position, last verification timestamp and status.
Only operator confirmation marks an identity verified; VLM explanations do not update it.

The collection plan lists **35 planned recordings**: five independent recordings for
each C1–C6 condition and five CX ambiguous recordings. It does not fabricate recordings.

| Condition | Repeat independently five times |
|---|---|
| C1 | Both laptops stationary; observe both |
| C2 | Move camera between frontal and oblique views |
| C3 | Move/cross laptops continuously in view |
| C4 | Hide/remove one laptop, then bring it back |
| C5 | Leave and return; positions unchanged |
| C6 | Leave; exchange positions out of view; return |
| CX | Hide distinguishing features; abstention is appropriate |

Use the same recording device, resolution, lighting protocol and observation duration
across conditions, and log variations. Capture reference photos separately from development
and held-out clips. Distinguishing physical features should be natural/object-associated;
do not introduce ground-truth overlays or encoded identity markers into evaluation images.
Do not split one recording into five purported independent trials. Obtain footage using
your webcam recording application, phone or RayNeo; no hardware is needed to import it:

```bash
.venv/bin/python scripts/identity_experiment.py import-video \
  --video identity-data/raw/crossing-01.mp4 --sample-fps 2 \
  --sequence crossing-01 --condition C3 --out identity-data/evaluation/crossing-01
```

The importer writes PNGs and initial metadata. Review upright orientation and timestamps;
timestamps are decoded frame-index/container-FPS estimates, not sensor measurements.
Variable-frame-rate recordings need manual timestamp review. Copy imported sequences into
one version-1 manifest, fix paths relative to that manifest, then manually label **every**
evaluated frame. Boxes are upright pixel `[left, top, right, bottom]`. No new box editor is
included; edit the JSON using reviewed crops/your labeling tool. Minimal schema:

```json
{
  "version": 1,
  "evidence_kind": "real_recording",
  "split": "test",
  "sequences": [{
    "id": "crossing-01", "recording_id": "independent-recording-01", "condition": "C3",
    "ground_truth_verified": true,
    "frames": [{
      "image": "crossing-01/frames/00000000.png", "timestamp_s": 0.0,
      "reset_session": false, "reasoning_probe": true,
      "ground_truth": [{
        "instance_id": "physical-a", "object_id": "11111111-1111-4111-8111-111111111111",
        "bbox": [100, 120, 320, 290]
      }]
    }],
    "recovery_events": []
  }]
}
```

Replace the example identity with the registered physical-object UUID. `instance_id`
follows the same physical laptop across movement, never the temporary track. Mark empty
scenes `ground_truth: []`; null is unverified and rejected by this study runner. Unregistered
objects use `object_id: null`. For an ambiguous *registered* laptop retain its verified UUID
in ground truth; `unknown` is an abstention, not a falsely correct identity assignment.

Mark `reset_session: true` on return for C5/C6. Add recovery episodes such as
`{"instance_id":"physical-a","kind":"swap","start_frame":20,"deadline_frame":35}`;
start is the first frame where the laptop is visible again. Kinds are `occlusion`, `return`,
`swap`. Deadline misses remain unrecovered rather than disappearing from latency results.
Freeze `reasoning_probe: true` on the same predetermined difficult observations for all
standalone-provider comparisons. These labels never enter prompts or association logic.

Optional initialization file:
`[{"sequence":"crossing-01","frame_index":0,"bbox":[100,120,320,290],"object_id":"<UUID>","verification":"operator_confirmed"}]`.
Use only independently operator-confirmed boxes, record their source, and give the identical
file to every method. The file is fingerprinted and does not mutate the gallery during runs.

Calibrate on a separately collected `split: "development"` dataset:

```bash
.venv/bin/python scripts/identity_experiment.py calibrate \
  --gallery artifacts/laptops/gallery.json \
  --dataset identity-data/development/dataset.json --out artifacts/laptops/calibration.json
```

Calibration refuses non-separable genuine/impostor development scores. The runner rejects
the same development manifest, exact overlapping image bytes, and synthetic gates on real
recordings. This does not detect near-duplicate crops from the same video: independence is
also a collection responsibility. Freeze thresholds and test data before final evaluation.

## Execute real evaluation and provider probes

```bash
.venv/bin/python scripts/identity_suite.py suite \
  --dataset identity-data/evaluation/dataset.json --gallery artifacts/laptops/gallery.json \
  --calibration artifacts/laptops/calibration.json --passes A B --pace 1 \
  --out artifacts/laptops/real-events

# Separate standalone correspondence pass: no temporal identity memory, fixed probe mask.
.venv/bin/python scripts/identity_suite.py suite \
  --dataset identity-data/evaluation/dataset.json --gallery artifacts/laptops/gallery.json \
  --calibration artifacts/laptops/calibration.json --methods H2 H3 --protocol probes \
  --passes A --trials 3 --pace 1 --out artifacts/laptops/real-probes
```

These commands make actual configured provider calls; enable only endpoints you intend to
use. Start with H0/H1 (`--methods H0 H1`) to validate data without inference. `events`
does not wait for reasoning in the frame loop. `probes` intentionally waits at selected
observations and clears temporal state each time; unselected observations are not scored.
Run the same masks, references, calibration, detector cache and image/context budgets.
Repeated inference trials measure provider variation, not additional independent recordings.
Use the same `--initializations` for every method when comparing seeded tracking.

`--pace 1` replays at recorded time. Faster pace is a software throughput check and can
cancel pending requests before the recording ends; it is not a real-time recovery benchmark.
Pass A uses verified ground-truth boxes only. Pass B computes NanoDet/YOLOX detections once
per suite and reuses identical cached outputs for all methods; detection and identity errors
remain distinguishable. No ground-truth UUIDs are passed into detection or inference.

Add `--backend "$IDENTITY_BACKEND"` to `suite` with `IDENTITY_API_TOKEN` for accepted-UUID
retrieval. Unknown/pending observations never fetch object-specific notes. The existing
API enforces authorization independently. Expiration and account changes clear identity
and content state; delayed responses cannot repopulate the prior user's notes.

To inspect authorized note text in the browser, add `--backend "$IDENTITY_BACKEND"` to
`serve`, then sign in there. The viewer forwards authentication to the existing backend,
stores tokens only in browser memory, and clears/aborts on sign-out or user/frame switches.
Only accepted recorded identities permit retrieval; notes are permission-filtered anew.
It displays up to the first 100 authorized notes and does not persist their contents in
experiment results. The offline results are trusted local artifacts, not signed identity proofs.

## Outputs and metric definitions

Each method/pass/trial writes summaries, observations JSONL/CSV, frame predictions,
recovery-event JSONL and provider-event JSONL. Suite reports include `comparison.json`,
per-sequence `comparison.csv`, `method-summary.csv`, and PNG/SVG correctness/latency plots.
Regenerate presentation files without rerunning inference:

```bash
.venv/bin/python scripts/identity_suite.py report --root artifacts/laptops/real-events
```

Results record source/data/reference/detector fingerprints, model metadata, thresholds,
library versions, pace and acceptance policy. Comparison refuses incompatible inputs.
Raw images, embeddings, tokens and private annotation text stay out of Git by default.

| Metric | Definition |
|---|---|
| Evaluated observation | Each labeled visible GT instance plus unmatched detection; prediction/GT pairs use one-to-one IoU >=0.5 |
| Correct-label coverage | Correct **accepted** UUIDs / known registered-object observations |
| Wrong-object label rate | Incorrect non-null accepted UUIDs / all evaluated observations; includes false-positive assignments |
| Unknown rate | Observations without accepted UUID / all evaluated observations, including detector misses and pending proposals |
| Proposal counts | Separate correct/incorrect/unknown VLM proposal observations; repeated frame observations are not unique calls |
| Identity switches | Changed accepted UUID for the same GT instance within a sequence/session; intervening abstention does not erase the last accepted UUID |
| Recovery success/time | First correct accepted identity in a declared return/occlusion/swap window; milliseconds from its first visible frame; also reports unrecovered windows |
| Correct retrieval coverage | Correct UUID plus successful authenticated HTTP retrieval / known observations; null if no backend |
| Annotation wrong-object rate | Incorrect UUID with successful nonempty annotation retrieval / all observations; distinct from identity-label error rate |
| Tracking update frequency | Selected tracking updates / sequence wall time, including pacing; not camera FPS |
| Calls per minute | Actual provider attempts, including escalation/failures, divided by recorded sequence duration in minutes |
| Provider latency | Wall time per actual provider attempt, including failures; median and P95 (P95 withheld below 20 samples) |
| Local latency | Tracker/descriptor/association step duration, excludes asynchronous reasoning and cached detector execution |
| CPU processing | Process CPU time during replay frame processing; model/gallery initialization excluded |
| Replay processing | Decode, local processing, optional HTTP and (only for probes) reasoning wait; shared detector latency reported separately |
| Replay label latency | Frame-processing elapsed time on frames producing an accepted label; not camera-to-display latency |
| Memory | Linux runner peak RSS in fresh child process per run; remote server/GPU memory remains unmeasured |
| Tokens/cost | Provider-reported usage and explicitly configured prices; null when unavailable, with completeness flag for partial metadata |

Sensor-to-display and GPU latency are explicitly null. Global-budget denials that prevent
a call are controller recovery events, not provider-attempt samples. The limits are global
within one runner, not a distributed quota across simultaneous users/processes.

`comparison.csv` retains independent sequence and trial identifiers. Method summaries
aggregate observation counts; plots use equally weighted sequence means. Neither is a
confidence interval or evidence that correlated frames are independent trials.

## Test and integrate next

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests scripts/tests -q
source scripts/dev_env.sh
android/gradlew -p android testDebugUnitTest lintDebug assembleDebug --console=plain
# Optional browser test dependencies, when not already installed:
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/identity_viewer_smoke.py \
  --url http://127.0.0.1:8026 --out artifacts/laptops/browser
```

The browser test expects the generated H0–H4 event suite and mocks only auth race transport;
actual backend permissions are tested separately. Standard APK:
`android/app/build/outputs/apk/debug/app-debug.apk`. New identity logic is not in this APK.

Before live RayNeo integration: collect/verify the 35 planned recordings; measure both
proposal and accepted-label errors with real local/frontier inference; choose development
gates; then place this pipeline behind an explicit experimental backend flag using the
existing rotated camera frames and detector outputs. Keep a bounded latest-frame queue,
per-session identity epochs and a shared inference quota. Return track/generation/state/UUID
to the existing image-space overlay; clear notes immediately on uncertainty or account
change. Instrument capture-to-overlay latency and server memory under actual concurrent
load. Keep the bottle demo as a selectable fallback. Smartphone/runtime deployment,
camera-motion compensation, robust MOT and world anchoring are later work.
