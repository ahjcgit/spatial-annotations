# Event-triggered physical-object identity recovery

This is an **opt-in recorded-frame experiment**, separate from the live single-bottle
RayNeo demonstration. It associates temporary tracks with existing `PhysicalObject.id`
UUIDs, abstains when evidence is inadequate, and can ask a vision-language model (VLM)
for identity proposals asynchronously. It does not provide world anchors or prove that
similar laptops can be distinguished reliably.

The implementation and validation results are in [IDENTITY_RECOVERY_RESULTS.md](IDENTITY_RECOVERY_RESULTS.md).
No real laptop-identity benchmark or real VLM inference has been completed in this phase.
The existing bottle/toy recordings are not a labeled two-laptop dataset.

## 1. Install and run the software checks

Run from the `spatial-annotations` application repository, not its parent repository.
Python 3.11 is the tested environment. Install ordinary dependencies once:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-identity.txt
# If this environment uses uv instead of pip:
# uv pip install --python .venv/bin/python -r scripts/requirements-identity.txt

PYTHONPATH=backend .venv/bin/python -m pytest backend/tests scripts/tests -q
```

No model download, credentials, webcam, or glasses are needed for the fixture below.
It generates abstract red/blue/gray rectangles, **not synthetic laptop photographs**.
The fixture's calibration is restricted to synthetic data and cannot be used on real recordings.
Output directories must be new or empty; commands never reset an existing database.

```bash
export IDENTITY_EXPERIMENT_ENABLED=true
.venv/bin/python scripts/identity_experiment.py fixture --out artifacts/identity/input

# Larger budget solely to exercise all six short software scenarios in one run.
export IDENTITY_VLM_REQUESTS_PER_MINUTE=100
.venv/bin/python scripts/identity_experiment.py run \
  --dataset artifacts/identity/input/dataset.json \
  --calibration artifacts/identity/input/calibration.json \
  --mode baseline --out artifacts/identity/run-a --preview
.venv/bin/python scripts/identity_experiment.py run \
  --dataset artifacts/identity/input/dataset.json \
  --calibration artifacts/identity/input/calibration.json \
  --mode vlm --mock --out artifacts/identity/run-b --preview
.venv/bin/python scripts/identity_experiment.py run \
  --dataset artifacts/identity/input/dataset.json \
  --calibration artifacts/identity/input/calibration.json \
  --mode hybrid --mock --out artifacts/identity/run-c --preview
.venv/bin/python scripts/identity_experiment.py compare \
  --runs artifacts/identity/run-a artifacts/identity/run-b artifacts/identity/run-c \
  --out artifacts/identity/comparison
unset IDENTITY_VLM_REQUESTS_PER_MINUTE
```

Each run produces `summary.json`, `sequence-metrics.csv`, `observations.csv`, `observations.jsonl`,
`tracks.jsonl`, `vlm-events.jsonl`, and optional boxed PNG previews. The comparison
produces JSON, CSV, SVG, and PNG. Previews show accepted object names or neutral
verification states and, with authenticated HTTP enabled, authorized note counts.
They deliberately do not export private note contents. This is image-space labeling.

`--pace 1` (default) replays according to recorded timestamps. `--pace 0` is a throughput
check: it may finish before asynchronous results arrive and is unsuitable for live
recovery latency comparisons. All modes must use the same replay pace and request budget.

## 2. Register Laptop A and Laptop B

Start the existing backend using the root README or a separate local database:

```bash
mkdir -p artifacts/identity
ss -lnt '( sport = :8018 )'  # use a different free port if occupied; never use 5173
DATABASE_URL=sqlite:///./artifacts/identity/annotations.db \
  .venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8018
```

Open `http://<computer-LAN-IP>:8018` to register/sign in using the existing companion.
On the development machine used for this work the LAN address is `192.168.1.76`;
check your machine's address before using it. The CLI uses the same accounts/API.
Acquire an access token without putting the password or token in command history:

```bash
export IDENTITY_BACKEND=http://127.0.0.1:8018
export IDENTITY_USERNAME=alice  # use the actual existing username
export IDENTITY_API_TOKEN="$(.venv/bin/python - <<'PY'
import getpass, os, httpx
r = httpx.post(os.environ['IDENTITY_BACKEND'] + '/auth/login',
               json={'username': os.environ['IDENTITY_USERNAME'],
                     'password': getpass.getpass('Password: ')}, timeout=15)
r.raise_for_status()
print(r.json()['access_token'])
PY
)"
```

Manually crop several reference images around each laptop. Include visible distinctive
features and several views. Reference images are identity evidence; generic stock laptop
images are not references for your physical devices. Store originals under ignored
`identity-data/` or `artifacts/identity/`.

```bash
export IDENTITY_EXPERIMENT_ENABLED=true
.venv/bin/python scripts/identity_experiment.py register \
  --backend "$IDENTITY_BACKEND" --gallery artifacts/identity/gallery.json \
  --name 'Laptop A' --images identity-data/references/a-front.jpg identity-data/references/a-side.jpg
.venv/bin/python scripts/identity_experiment.py register \
  --backend "$IDENTITY_BACKEND" --gallery artifacts/identity/gallery.json \
  --name 'Laptop B' --images identity-data/references/b-front.jpg identity-data/references/b-side.jpg
```

Record each printed `object_id` and `marker_id`. The former is the persistent identity;
the latter lets the existing companion select the object to author public/private/group
notes. They are different UUIDs. Use `--object-id <existing-object-UUID>` instead of
`--name` to add references without creating another object. Registration requires a
valid login and looks up the existing object through the normal API. It does not add
anonymous annotation endpoints or store images in public object metadata.

A local version-1 gallery stores UUID, name, relative reference paths, SHA-256 hashes,
optional last-known image position, and `last_verified_identity_at`. Images are EXIF
oriented, metadata stripped, and copied as PNGs up to 1024 pixels. Embeddings are computed
in memory. Last verified time/position are updated only by explicit operator confirmation;
null means no such confirmation has been recorded. Registration is manual and galleries
are local to this experiment; this is not a concurrent multi-user gallery service.

## 3. Collect and label evaluation sequences

Keep reference images, development sequences for calibration, and held-out evaluation
sequences separate. Record the following conditions with stable physical-instance labels:

| Condition | Capture |
|---|---|
| `stationary` | Observe both laptops without object motion |
| `position_swap` | Exchange their positions between observations |
| `moving` | Move the objects while they remain visible; include crossing |
| `disappearance` | Occlude/remove one, then reintroduce it |
| `new_session` | Set `reset_session: true` before observing them again |
| `ambiguous` | Hide distinguishing details; unknown is a valid outcome |

Import a recorded video (no live camera dependency):

```bash
.venv/bin/python scripts/identity_experiment.py import-video \
  --video identity-data/swap.mp4 --sample-fps 2 --sequence swap-01 \
  --condition position_swap --out identity-data/swap-01
```

This saves decoded PNGs with dimensions and timestamps computed as frame index/container
FPS. Variable-frame-rate or unusual rotation metadata needs explicit timestamp/orientation
review; the importer does not claim original sensor timestamps. Check the decoded images.
Imported ground truth is null until you label it; **null is unscored, not a successful test**.
Combine sequence entries into a dataset whose image paths remain within its directory.

Example layout:

```text
identity-data/
  references/a-front.jpg, a-side.jpg, b-front.jpg, b-side.jpg
  development/dataset.json, frames/...
  evaluation/dataset.json, frames/...
artifacts/identity/
  gallery.json, references/<object-UUID>/<sha256>.png
  calibration.json
  run-a/, run-b/, run-c/, comparison/
```

A minimal evaluation manifest (replace the UUID and box with actual labels):

```json
{
  "version": 1,
  "evidence_kind": "real_recording",
  "sequences": [{
    "id": "swap-01",
    "condition": "position_swap",
    "frames": [{
      "image": "frames/00000000.png",
      "timestamp_s": 0.0,
      "reset_session": false,
      "detections": [{"label": "laptop", "bbox": [100, 120, 320, 290]}],
      "ground_truth": [{
        "instance_id": "physical-laptop-a",
        "object_id": "11111111-1111-4111-8111-111111111111",
        "bbox": [100, 120, 320, 290]
      }]
    }]
  }]
}
```

Boxes are `[left, top, right, bottom]` in decoded, upright image pixels. Timestamps must
increase within each sequence. `instance_id` follows the physical item across position
changes; it is never the temporary tracker ID. Use `object_id: null` for an unregistered
physical object. `ground_truth: []` means an explicitly labeled empty scene, while null
means unscored. Ground truth is consumed only by calibration/evaluation, never by matching
or VLM payload construction. Manual detections and ground truth are separate fields.
Using the same boxes for both is an intentional identity-only experiment, not a detector test.

## 4. Appearance baseline and calibration

Default `color-grid-v1` is a 448-dimensional RGB grid/histogram descriptor with cosine
similarity. It is cheap and CPU-compatible but strongly sensitive to lighting, crop, and
viewpoint; it is not a learned instance embedding. There are **no default identity acceptance
thresholds for real images**. Without a calibration file, observations remain unresolved.

```bash
.venv/bin/python scripts/identity_experiment.py calibrate \
  --gallery artifacts/identity/gallery.json \
  --dataset identity-data/development/dataset.json \
  --out artifacts/identity/calibration.json
```

The development calibration requires separable genuine/impostor scores, chooses their
midpoint as the floor and half the minimum genuine margin as the ambiguity gate, and
records the descriptor, dataset/image fingerprint, and sample count. If separation fails,
it refuses to create a usable calibration. Collect better references or change descriptors;
do not lower thresholds until everything is assigned. This simple development calibration
is not a probability calibration or a guarantee on held-out data. Evaluation rejects the
identical development dataset and rejects synthetic calibration on real recordings.

Optional `--descriptor dinov2 --dino-repo <local-checkout> --dino-weights <checkpoint>`
uses DINOv2 ViT-S/14 on CPU. Install PyTorch and dependencies compatible with the official
[DINOv2 repository](https://github.com/facebookresearch/dinov2) separately. The adapter
uses `source=local`, `pretrained=False`, explicit local weights, RGB stretch to 224 and
ImageNet normalization; weight SHA-256 identifies the descriptor. It never automatically
downloads weights. This adapter has **not been executed here** and needs its own calibration.
Consult the upstream [model card](https://github.com/facebookresearch/dinov2/blob/main/MODEL_CARD.md).

Temporal association is a replaceable greedy baseline: motion-predicted box overlap plus
appearance (weights 0.6/0.4), gated by overlap >0.05 or a nearby center with similarity >0.9.
Motion extrapolation caps at 0.5 s. Tracks expire after 3 s; gaps above 1 s request verification
when recovery is enabled. Similarity 0.97 gates temporal consistency; overlapping boxes with
IoU >=0.25 invalidate identities. These are **engineering tracking gates**, not calibrated
identity probabilities. Registered identity acceptance additionally requires calibrated
appearance evidence and uniqueness.

[ByteTrack](https://github.com/FoundationVision/ByteTrack) was evaluated for integration:
its YOLOX/native-extension setup would add dependencies to the existing OpenCV detector
path. This phase uses the smaller baseline rather than claiming ByteTrack performance.
The baseline is not an occlusion-robust MOT tracker; crossing and appearance drift can
cause abstentions, track fragmentation, or errors. An object's UUID never comes from its
track ID, screen position, or detector category.

## 5. Configure a real VLM (optional)

The generic adapter targets an OpenAI-compatible `/chat/completions` vision endpoint.
It sends image data URLs and requests JSON-object output. Choose a model/server that
supports both; compatibility has been transport-tested with mocks, not every provider.
The model ID is deliberately not hardcoded. No keys or endpoint credentials are committed.

```bash
export IDENTITY_EXPERIMENT_ENABLED=true
export IDENTITY_VLM_ENABLED=true
export IDENTITY_VLM_ENDPOINT=http://127.0.0.1:1234/v1  # local compatible server
# For hosted service, use that provider's HTTPS API base instead.
export IDENTITY_VLM_MODEL='<installed-or-hosted-vision-model-id>'
read -rs -p 'VLM key (Enter if local server needs none): ' IDENTITY_VLM_API_KEY; echo
export IDENTITY_VLM_API_KEY
export IDENTITY_VLM_TIMEOUT_S=45
export IDENTITY_VLM_RESPONSE_TTL_S=30
export IDENTITY_VLM_CONCURRENCY=2
export IDENTITY_VLM_MAX_IMAGE_DIMENSION=640
export IDENTITY_VLM_COOLDOWN_S=30
export IDENTITY_VLM_REQUESTS_PER_MINUTE=6
export IDENTITY_ACCEPTANCE=manual
```

The request contains cropped current observations, up to three reference views per object,
registered UUIDs, ambiguity reasons, and previous associations explicitly marked stale.
The current implementation supports up to eight candidate objects/four tracks per request;
excess galleries abstain instead of silently dropping candidates. It does not send note
contents, backend credentials, tokens, arbitrary metadata, or filenames. Only images you
choose as references/current observations are submitted to the configured provider.
No overview image is currently sent.

Optional real-model smoke test (selected frames, real data, no mock):

```bash
.venv/bin/python scripts/identity_experiment.py run \
  --dataset identity-data/evaluation/dataset.json --gallery artifacts/identity/gallery.json \
  --mode vlm --max-frames 1 --out artifacts/identity/real-vlm-smoke
```

This submits the first observation **of each sequence**, subject to the global budget.
Use a one-sequence manifest for a single-request smoke test. A valid proposal does not
establish that the identity is correct. Count HTTP/protocol/timeouts separately from
identity errors.

Automatic acceptance remains off by default. `IDENTITY_ACCEPTANCE=manual` preserves
non-null responses as `pending_verification`; no object-specific notes are fetched.
A development operator can explicitly call
`pipeline.confirm(track_id, generation, object_id)` while that observation is current.

For a calibrated experiment, `IDENTITY_ACCEPTANCE=corroborated` additionally requires
`vlm_min`, `vlm_margin`, and `vlm_development_set` in the calibration file. Derive those
on a separate labeled VLM development run and document the error/coverage tradeoff.
The appearance `calibrate` command intentionally does not invent VLM acceptance gates.
Acceptance requires a structurally valid proposal, current track/session/generation,
fresh and consistent crop, unoccupied UUID, no unresolved overlap, and independently
corroborating appearance evidence. VLM prose or confidence claims are never treated as proof.
This conservative policy can miss valid VLM recoveries when appearance is weak.

`IDENTITY_VLM_INPUT_USD_PER_MILLION` and `IDENTITY_VLM_OUTPUT_USD_PER_MILLION` optionally
supply your provider's pricing. Estimated cost is null without both prices and token
usage. The simple estimate does not model cache discounts or additional provider fees.

## 6. Run the controlled comparison with real data

Run the same commands as step 1 with your evaluation manifest/gallery/calibration, omit
`--mock`, and keep the same provider settings, request budget, and replay pace across B/C.

- **A / `baseline`:** motion/appearance only, no VLM requests even when configured.
- **B / `vlm`:** selected independent observations (`--vlm-stride 4`, minimum 2). Reset
  temporal context before every selection and await the standalone correspondence result.
  Nonselected observations abstain. Raw proposed correspondence accuracy is reported
  separately from accepted identity accuracy; manual policy never automatically accepts it.
- **C / `hybrid`:** process every observation locally and schedule recovery only for
  unresolved events. Frame processing does not await a VLM response. Results can affect
  later frames, never retroactively rewrite earlier evaluations.

Add `--detector nanodet` or `--detector yolox_s` to replace manual detections with the
existing `scripts/eval_models.py` adapters (laptop category only). Existing verified model
files under `artifacts/models/` are required; use the existing `scripts/setup_vision.py`
workflow. No model is downloaded by the experiment runner. First evaluate identity with
manual boxes, then repeat with detector boxes to expose detection failures separately.

Add `--backend "$IDENTITY_BACKEND"` to retrieve authorized notes for accepted identities.
Use galleries registered against that backend; fixture UUIDs are not backend records.
For Alice/Bob comparison, obtain each user's token and run into separate output directories.
The session-aware client also supports switching with `set_token`: it clears tracks, cancels
pending reasoning, discards old HTTP results, and never caches private notes. Expired auth
clears identities; later login/retrieval can recover. The VLM is not an authorization mechanism.

## 7. State machine and result validation

```text
new/unidentified observation -> unknown or uncertain
  calibrated unique appearance -> matched
  unresolved event + available budget -> pending_verification (async request)
    valid unknown / failed request -> unknown
    valid non-null proposal -> pending_verification
      operator confirmation or calibrated corroboration -> matched
matched + loss/conflict/crossing -> uncertain, hide object-specific annotation
session change / expired auth -> invalidate tracks, requests, and pending retrieval
```

Small movements and routine box updates do not trigger requests. Brief misses hide a
track while absent, invalidate pending responses, and preserve an accepted identity on a
consistent brief return. Objects outside the field of view generate no recovery requests.
Each unresolved track generation has at most one active request; successful proposals or
unknown responses consume that event. Failures may retry twice total after cooldown.
Global concurrency/rate budgets survive sequence/session resets within a runner.

A VLM response must cover exactly the submitted track IDs, use only supplied UUIDs,
contain no extra fields, and never assign the same UUID twice. Unknown/malformed JSON,
unknown UUIDs, repeated tracks, incompatible statuses, occupied UUIDs, changed crops,
lost tracks, expired responses, and changed session/generation are rejected. If any member
of a batch becomes stale, the entire batch is discarded. No stale box is used to reassign
an identity. Failure is an abstention, not a fabricated successful lookup.

## 8. Read the metrics correctly

Ground truth is paired to output boxes using one-to-one IoU >=0.5. Detection misses count
as unknown; unmatched predicted boxes count as additional observations with no registered
identity. Reports include both known-object denominator and total evaluated observations.

| Metric | Definition |
|---|---|
| Correct / incorrect / unknown | Accepted UUID equals ground truth / differs / no accepted UUID (including pending) |
| Proposal counts | Correct / incorrect / unknown VLM proposals on evaluated observations; separate from acceptance |
| Identity switches | Change between two assigned UUIDs for the same physical instance within a session, including after abstention |
| Correct identity coverage | Correct accepted assignments / known-object observations |
| Correct retrieval coverage | Correct identity plus successful authenticated retrieval / known-object observations; null if HTTP disabled |
| Wrong-object label rate | Incorrect accepted identity with successfully retrieved nonempty notes / total observations; null if HTTP disabled |
| Initial acquisition | First visible observation to first correct assignment, separately from recovery |
| Identity recovery | First unresolved/reappearing observation to first correct assignment, using frame timestamps; censored episodes counted |
| VLM latency | Monotonic request worker start to validation/failure, including image encoding, HTTP and validation |
| Local latency | Crop/descriptor/association/scheduling time; excludes decoding, detector, HTTP note retrieval, and display |
| Detector latency | Existing adapter's decode/preprocess/inference/postprocess duration, separately measured |
| VLM requests/minute | Actual scheduled requests / recorded sequence duration in minutes, not wall-clock throughput |
| Usage/cost | Returned token metadata and optional configured pricing; missing means null, not zero |

Mean/median are reported for available timing samples; P95 is withheld below 20 samples.
Cancellations before dispatch have null latency and are counted separately from started workers.
Sequence boundaries and cancellations are logged; results arriving after the last evaluated
frame do not count as recovered. Pending episodes at disappearance/end are censored, not
silently scored as successful. Include censored counts when reporting recovery latency.

B's standalone selection uses a wait; C does not. Compare B's selected correspondence
results separately from C's online coverage. Proposal observations may repeat a retained
proposal across frames, so they are not independent VLM trials. Frame samples within a
sequence are correlated. Six short clips do not establish statistical generalization.
Report per-condition counts and independent recordings before aggregate claims.

## 9. Next phase: live RayNeo integration

1. Collect real A/B references, a development set, and held-out clips with physical identity
   labels. Include unknown laptops, crossing, viewpoint/lighting changes, and obscured details.
2. Compare the replaceable descriptor and a maintained tracker on those clips. Calibrate
   thresholds on development data and freeze them before held-out evaluation.
3. Run standalone real-VLM correspondence. Review incorrect proposals, timeouts, image
   quality, cost, and the proposed acceptance policy before enabling automatic recovery.
4. Feed the existing RayNeo frame/detector output into one serialized pipeline owner per
   user/session. Run recovery in a separate service/task; bound the frame queue and drop
   obsolete frames instead of blocking camera capture.
5. Render only current accepted UUID labels through the existing authenticated retrieval
   path; show a neutral verification state on uncertainty. Preserve the existing bottle
   presentation as a separate fallback and keep the experiment disabled by default.
6. Test physical camera motion, network loss, login changes during recovery, thermal/load
   behavior, and display/input routing. Those live tests were not performed in this phase.

There is no new Android integration, world tracking, optical alignment, or hardware claim
in this implementation. Existing physical-pilot results in IMPLEMENTATION_STATUS remain
separate evidence for the earlier single-object demonstration.
