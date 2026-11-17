# H0–H4 implementation and validation — November 17, 2026

The offline comparison pipeline, asynchronous provider escalation, authenticated viewer
and reproducible reports are implemented. **Visual reasoning has not been shown to improve
real object-specific annotation correctness or justify its latency/cost.** No genuine
two-laptop evaluation dataset or configured real VLM was available. The measurements below
are software checks with synthetic colored rectangles and deterministic mock providers.

Branch: `experiment/h0-h4-identity`, built from `origin/demo/model-detection` plus the
previous tested identity experiment (`f13d7c1`). No live Android or production annotation
routes were replaced. [Execution and collection guide](IDENTITY_H0_H4.md).

## Executed validation

| Check | Actual result | Scope |
|---|---|---|
| Baseline Python | 67 passed | Before these changes; existing identity experiment included |
| Final full Python suite | **82 passed**, one existing Starlette/AnyIO deprecation warning | Existing tests plus 15 new tests |
| Study-specific validation | 14 passed | H0–H4, probes, escalation, leakage, shared inputs/report/viewer |
| Backend viewer authorization | Passed in full suite | Actual FastAPI/SQLite via ASGI: Alice sees public/private, Bob only public; anonymous/expired credentials rejected |
| Browser checks | **5 passed**, no page errors | Headless Chromium via LAN; controls, run switching, GT toggle, mobile layout, playback, account race |
| Browser account-switch race | Passed with intercepted HTTP | Delayed Alice note response discarded after Bob login; sign-out clears notes; no token storage |
| Android standard unit tests | **29 passed, 2 skipped**, no failures | Optional external-fixture tests retain their pre-existing skip conditions |
| Android lint/build | Passed; 0 errors, 40 existing warnings | Standard debug APK built; Android source unchanged |
| H0–H4 Pass A | All five ran, 101 scored observations each | Seven generated conditions, manual boxes, same refs/gates, recorded-time pace |
| H0–H4 Pass B | All five ran, 101 missed observations each | Actual NanoDet CPU execution on colored rectangles; no laptop detections |
| Standalone-provider protocol | H2/H3, two trials each, 28 selected observations/run | Fixed 14-frame probe mask, reset temporal state, mock providers |
| Missing provider configuration | H2/H3/H4 correctly marked `not_run` | No implicit endpoint, paid calls or nested agent sessions |
| Python source checks | Passed | Ruff imports/undefined names and formatting on experiment modules/tests |
| Viewer design check | No detector findings | Impeccable manual scan; desktop/mobile screenshots reviewed |

An initial final-test invocation omitted `PYTHONPATH=backend` and failed collection with
`ModuleNotFoundError: app`; rerunning the documented command passed. This was an invocation
error, not a source regression. No baseline source-test failures were found.

The 15 new tests supplement previous tests for malformed JSON, invalid UUIDs, duplicate
assignments, generation/TTL invalidation, concurrent events, cooldown/deduplication,
network failure/recovery, auth expiration and account switching while reasoning is pending.
New tests additionally exercise no-appearance H0, H1 viewpoint/swap, local→frontier fallback,
timeouts/malformed local responses, stale-session escalation cancellation, shared actual-call
budget, explicit frontier authorization, prompt isolation from labels/notes/filenames,
hand-counted recovery metrics, embedding provenance, exact development-image leakage,
five-method shared-input execution, probe masks and authenticated browser-serving routes.

No physical RayNeo, webcam, emulator, real Qwen, DINOv2 or frontier-model test was performed
for this extension. Prior hardware-pilot evidence remains documented separately.

## Synthetic event-run results

Each method processed the same seven generated sequences (C1–C6 and CX), 56 frames and
101 labeled object observations, at `--pace 1`. Seeds explicitly initialize both objects
on the first frame of nonambiguous sequences, identically for every method. New sessions
are not reseeded. The `corroborated` policy uses the fixture-only calibration; real-image
evaluation rejects that calibration. The 100-call/minute test budget avoids limiting short
software scenarios. These are **zero independent real recordings**.

| Method | Correct accepted | Incorrect accepted | Unknown/pending | Coverage | Provider calls | Provider median |
|---|---:|---:|---:|---:|---:|---:|
| H0 geometry | 56 | 0 | 45 | 55.45% | 0 | — |
| H1 appearance | 81 | 0 | 20 | 80.20% | 0 | — |
| H2 local mock | 80 | 0 | 21 | 79.21% | 3 | 5.98 ms |
| H3 frontier mock | 80 | 0 | 21 | 79.21% | 3 | 5.87 ms |
| H4 adaptive mocks | 80 | 0 | 21 | 79.21% | 6 | 5.06 ms |

All methods had zero identity switches on these fixtures. Wrong-object identity-label
rate was zero; actual annotation retrieval was disabled in these runs, so annotation
retrieval coverage/rate are null and are tested separately. H0 cannot recover identities
after reset without fresh operator evidence. H1 recognizes the fixture colors. H2/H3
use the same descriptor-based mock; H4's local mock deliberately abstains to exercise
frontier escalation. This is not a comparison of actual models' reasoning abilities.

H2–H4 produce one fewer accepted observation than H1 while waiting for asynchronous
verification. They do **not** improve coverage in this check. Mock delays are deliberately
about 5 ms; the measured medians are not VLM latency. P95 is withheld for these methods
because there are fewer than 20 provider attempts each. Token usage and cost are null.

Per-condition median local processing was 0.18–0.90 ms for H0, 1.87–2.90 ms for H1, and
0.62–3.09 ms across H2–H4. Peak runner RSS in Pass A was 55.93–56.63 MiB. These tiny-image
checks run on a shared development machine, exclude remote-model memory, and do not predict
phone/glasses performance. Local and provider latency boundaries are defined in the guide.

Pass B ran the actual pinned NanoDet Plus 416 adapter once per input frame and shared
its cached detections across methods. It found no laptops in abstract rectangles. Every
method therefore reported 0 correct, 0 incorrect, 101 unknown/missed observations and
0 provider calls. This verifies detector/error accounting, **not detector accuracy**.
YOLOX-S is supported through the existing adapter but was not rerun for this extension.

## Fixed-probe software comparison

H2 and H3 each ran two trials on the same predefined frames 1 and 5 of every sequence.
Each run evaluated 28 observations and made 14 mock calls, with temporal state reset at
every selected observation. Each produced 24 correct, 0 incorrect and 4 unknown proposals.
Default manual acceptance left all 28 accepted identities unknown/pending. Proposal and
accepted-label metrics must not be combined. These accelerated (`--pace .05`) checks
verify mask/repetition logic, not live latency or model nondeterminism.

## Evidence files

Local generated artifacts are ignored by Git; reproduce using the guide:

```text
artifacts/identity-h0-h4/
  baseline-python.log, python-validation-final.log, study-final.log
  android-validation.log
  fixture/{dataset,gallery,calibration,initializations}.json
  collection/collection-plan.json
  final-events/
    A-events-H0-r1/ ... B-events-H4-r1/
      summary.json, sequence-metrics.csv, observations.csv, observations.jsonl
      frames.jsonl, vlm-events.jsonl, recovery-events.jsonl
    comparison.json, comparison.csv, method-summary.csv
    tradeoff-A-events.{png,svg}, tradeoff-B-events.{png,svg}
  probe-check/                 # fixed probe mask; two mock trials/provider
  unconfigured-check/          # explicit not_run results
  browser-final/{results.json,desktop.png,mobile.png}
  design-detector.json
```

The plots were rendered and reviewed. They use sequence means; the table above aggregates
observation counts, so their coverage values need not be identical. Coincident markers
are intentional. No chart treats frames or repeated inference as independent recordings.
Source, image, reference, calibration, detector and initialization fingerprints are saved
for comparison checks. Private notes, passwords, tokens and raw VLM evidence are not logged.

## Implementation status

| Feature | Implemented | Tested | Environment/result | Remaining validation |
|---|---|---|---|---|
| Persistent UUID registry, multiple references, embedding export | Yes | Yes | Synthetic registry; existing HTTP registration regression tests | Real laptop reference quality |
| H0 geometry and operator initialization | Yes | Yes | Deterministic sequences; no appearance calls | Real camera motion/crossings |
| H1 appearance recognition | Yes | Yes | Color-grid synthetic swap/viewpoint tests | Real calibration; optional DINO runtime |
| H2 local VLM endpoint | Yes | Mock only | Vision transport, fallback, timeout tests | Install/runtime-test actual Qwen or compatible model |
| H3 frontier endpoint | Yes | Mock only | Explicit configuration/authorization gates | Authorized real-model correspondence benchmark |
| H4 async escalation | Yes | Yes with mocks | Local abstention/wrong proposal/failure → optional frontier; stale results rejected | Real latency/error/cost tradeoff |
| Acceptance/unknown/uniqueness policy | Yes | Yes | Invalid/stale/duplicate assignments rejected | Calibrated real evidence thresholds |
| Authenticated annotation retrieval | Yes | Yes | Existing backend permissions and session-isolation tests | Integrated real-laptop retrieval run |
| Browser comparison viewer | Yes | Yes | Desktop/mobile Chromium, actual backend ACL test plus mocked browser account race | User review on real recordings |
| A/B passes, probes, logs and charts | Yes | Yes | Same cached detections/reference/mask; hand-counted metric tests | Held-out real data, repeated real inference |
| Five genuine sequences/condition | Plan/schema ready | Not collected | 35 planned; 0 real recordings collected here | User-operated physical scene recording/GT verification |
| Existing Android demo | Preserved | Regression checks passed | Standard unit tests/lint/APK | No new physical-device check this phase |
| Live RayNeo identity integration | No | No | Offline phase only | Bounded stream, per-user epochs, capture-to-label instrumentation |
| Robust MOT/camera compensation/world anchors | No | No | Explicitly outside this baseline | Separate future work |

Files added: `backend/app/identity/{providers,study}.py`,
`scripts/identity_{suite,study_report,viewer,viewer_smoke}.py`,
`scripts/tests/test_identity_study.py`, `backend/tests/test_identity_viewer.py`,
`demo/identity-review.{html,css,js}`, this report, `IDENTITY_H0_H4.md`, and
`IDENTITY_VIEWER_DESIGN.md`.

Files extended: `backend/app/identity/{appearance,controller,gallery,tracker}.py`,
`scripts/identity_experiment.py`, README, and implementation status. Existing requirements,
detector implementations, production routes, permission models and Android source are retained.

## Research conclusion and next measurements

**We cannot yet conclude that visual reasoning improves correctness or is worth its cost.**
The executed fixture actually has slightly higher accepted coverage under H1, and no
configuration makes an incorrect assignment. It cannot discriminate real model quality.

Collect five independent recordings per C1–C6 condition plus ambiguous examples; independently
verify boxes and physical UUIDs. Calibrate on separate development footage, then freeze it.
Run H0/H1 on held-out data, real local/frontier fixed probes, and event-triggered H2–H4 under
matched budgets. Report per-sequence errors, abstentions, explicit return/swap recovery,
response distributions, server memory and actual provider usage. Keep wrong-object labels
as the principal risk alongside correct coverage; report uncertainty at the recording level.
Only then choose an acceptance policy and provider for a flagged live RayNeo integration.
