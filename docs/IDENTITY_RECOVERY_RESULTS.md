# Identity recovery implementation and validation — November 13, 2026

The offline prototype is implemented and tested with deterministic fixtures, a mock VLM,
and the actual annotation backend. **No real two-laptop accuracy result or real VLM benchmark
is established.** The live bottle demonstration's Android/backend code was not replaced.

## Executed checks

| Check | Actual outcome | Evidence / scope |
|---|---|---|
| Baseline before edits | 25 backend + 16 script tests passed | Existing source on `demo/model-detection` at `a4b5940`; no baseline test failures |
| Baseline Android | Unit tests, lint, standard debug build passed | 29 passed, 2 optional replay/HTTP tests skipped without their external fixture properties |
| Final Python suite | **67 passed**, one existing Starlette/AnyIO deprecation warning | 41 original + 26 new tests; `artifacts/identity/python-validation-final.log` |
| Standard Android | **29 passed, 2 skipped**; build passed | `artifacts/identity/android-validation.log`; 31 tests in JUnit XML, zero failures/errors |
| Presentation Android package | Tests/lint/build passed with `-PpresentationDemo=true` | `artifacts/identity/android-presentation-validation.log`; standard package rebuilt afterward |
| Android lint | 0 errors, 40 existing warnings | `android/app/build/reports/lint-results-debug.txt`; Android source unchanged |
| Real HTTP registration/retrieval | CLI created two distinct object UUIDs; Alice retrieved 2 notes per object, Bob 1 | Actual local uvicorn/FastAPI/SQLite, synthetic reference crops; `artifacts/identity/http-smoke/results.json` |
| Backend restart | Both objects and all four notes persisted; anonymous lookup returned public notes only | Same database restarted; HTTP retrieval and SQLite row counts checked |
| Permission tests after VLM acceptance | Alice private note available, Bob excluded | Actual backend via ASGI transport, deterministic VLM, corroborated synthetic policy |
| Session/race/network tests | Passed | Pending reasoning/HTTP discarded on user switch; expired auth clears state; network retry succeeds |
| NanoDet adapter smoke | Six generated frames processed on CPU; no laptops detected, all 12 labeled fixture observations missed | Expected for colored rectangles; proves adapter execution only, not detector accuracy |
| Offline A/B/C comparison | Six conditions, 48 frames, 93 labeled observations per mode | Manual boxes, deterministic colored-block fixture and mock VLM; full table below |
| Video import | Passed generated MJPEG decode/timestamp/dimension test | Not a real webcam or laptop video |
| Python source checks | Ruff import/undefined-name checks and formatting passed | New experiment source/tests only |

The optional JVM replay and live HTTP cases retain their pre-existing external-input
requirements; they are not claimed as executed here. Earlier project evidence for those
paths is separate. No physical glasses or emulator UI test was performed for the new
Python identity module.

Commands executed for regression checks:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests scripts/tests -q
source scripts/dev_env.sh
android/gradlew -p android -PpresentationDemo=true testDebugUnitTest lintDebug assembleDebug --console=plain
android/gradlew -p android testDebugUnitTest lintDebug assembleDebug --console=plain
```

The final standard APK remains at `android/app/build/outputs/apk/debug/app-debug.apk`.
No new identity feature is inside that APK; live integration is a next-phase task.
The temporary HTTP smoke backend used a separate ignored database and was stopped after
validation; existing running project services were not replaced.

## Deterministic fixture comparison

These runs were executed sequentially at recorded-time pace 1, using the same dataset,
reference gallery and synthetic calibration, default **manual** proposal acceptance,
and a 100-attempt/minute software-test budget. B selects every fourth frame without prior
track identity. A and C process each frame. The mock uses crop descriptors, never ground truth.

| Configuration | Evaluated observations | Correct accepted | Incorrect accepted | Unknown/pending | VLM request attempts |
|---|---:|---:|---:|---:|---:|
| A: lightweight association | 93 | 75 | 0 | 18 | 0 |
| B: standalone selected mock correspondence | 93 | 0 | 0 | 93 | 12 |
| C: event-triggered hybrid with mock | 93 | 66 | 0 | 27 | 3 |

B produced 19 correct, 0 incorrect, and 4 unknown **proposal observations** on selected
frames. Those proposals were not automatically accepted. C retained proposals across
subsequent frames: 8 correct and 14 unknown proposal observations. These are frame counts,
not independent VLM calls. The separately tested corroborated policy accepts supported
mock proposals, including a backend authorization test; it was not enabled in this table.

C abstained after a position swap and a long observation gap pending verification. It
therefore has lower accepted coverage than A in this manual-policy fixture. **This result
does not show that the hybrid improves identity accuracy.** Both had zero wrong assignments
on this deliberately simple software fixture. Real laptop data and a real model are needed
to answer the research question.

Measured software timings:

| Measurement | Result | Interpretation |
|---|---|---|
| B request-worker median | 6.93 ms, n=12 | Mock contains a deliberate 5 ms delay; not VLM/API latency |
| C request-worker median | 5.88 ms, n=3 | Same mock; not VLM/API latency |
| A local median range across conditions | 2.01–2.93 ms | Crop/descriptor/greedy association on tiny generated images |
| C local median range across conditions | 2.18–3.05 ms | Same scope, with recovery scheduling |
| Request P95 | Withheld | Fewer than 20 requests in each mode |
| Provider token usage / API cost | null | Mock provides no usage or pricing evidence |
| HTTP retrieval coverage / wrong-object label rate | null in A/B/C runs | Comparison ran without a backend; actual HTTP was checked separately |

All six conditions are present: stationary, position swap, moving, temporary disappearance,
new session, and ambiguous identity. These constructed sequences are not independent
real-world trials, and the counts must not be presented as generalization estimates.

Local, ignored evidence directory:

```text
artifacts/identity/final-20261113/
  baseline/, vlm/, hybrid/
    summary.json, sequence-metrics.csv, observations.csv, observations.jsonl
    tracks.jsonl, vlm-events.jsonl, preview/*.png
  comparison/
    comparison.json, comparison.csv, comparison.svg, comparison.png
```

The comparison figure was rendered and visually reviewed. It separates accepted identities
from proposals. Dataset fingerprints include manifest/label content and the actual image
bytes; model hashes, library versions, gates, acceptance policy, and replay settings are
recorded in each summary. Raw images, databases, credentials and generated evidence are
not committed. Reproduce them using [IDENTITY_RECOVERY.md](IDENTITY_RECOVERY.md).

## Feature status

| Feature | Implemented | Tested | Environment / result | Hardware validation needed |
|---|---|---|---|---|
| Existing physical UUIDs + multiple reference galleries | Yes | Yes | Local manifest + actual HTTP registration, persistence checked | No |
| Lightweight appearance + temporal association | Yes | Yes | Synthetic known/unknown, swap, movement, overlap, brief miss and long gap tests | Real-image evaluation still needed |
| Optional local DINOv2 adapter | Yes | No | Requires separately installed runtime/checkpoint; no model download performed | No, but real CPU/runtime validation needed |
| OpenAI-compatible vision transport | Yes | Mock transport only | Payload, JSON validation, usage parsing, failures tested | Real endpoint/model smoke still needed |
| Async event-triggered controller | Yes | Yes | Stale generations/crops/session, timeout, cooldown, global budget, concurrency, cancellation tested | Live frame scheduling not yet integrated |
| Proposal vs acceptance separation | Yes | Yes | Manual default; calibrated corroboration demonstrated with mock | Real acceptance calibration needed |
| Access-controlled annotation retrieval | Yes | Yes | Alice/Bob private/group filtering, revocation, pending switch, expired auth, network recovery | No for backend; wearable rendering deferred |
| Dataset/video loader and A/B/C metrics | Yes | Yes | Six fixture conditions, generated video import, hand-counted metric checks | Real laptop footage needed |
| Existing NanoDet detector reuse | Yes | Adapter executed | Actual model on six synthetic frames, zero laptop detections | Real laptop detection test needed |
| Existing YOLOX adapter option | Yes | Not executed in this phase | Existing evaluator reused; weights not present in this checkout | No, recorded-frame validation needed |
| Offline bounding-box previews | Yes | Yes | Generated annotated PNGs; no private note text exported | No |
| Standard + presentation Android regressions | Preserved | Yes | Unit tests/lint/build pass; no Android source changes | New identity pipeline not integrated |
| Live RayNeo identity recovery | No | No | Next phase | Yes |
| World anchoring / SLAM | No | No | Outside this phase | Not claimed |

## Changes and architecture

- New `backend/app/identity/`: local gallery, replaceable descriptors/calibration,
  greedy tracker, provider adapter, asynchronous controller, session-aware annotation
  client, dataset reader and evaluator.
- New `scripts/identity_experiment.py`: registration, synthetic fixture, video import,
  development calibration, replay and comparison commands.
- New `scripts/requirements-identity.txt`: optional dependency set using existing pinned
  backend/evaluation requirements; no new large model dependency by default.
- New `scripts/tests/test_identity.py`, `scripts/tests/test_identity_evaluation.py`,
  `backend/tests/test_identity_integration.py`: 26 tests.
- README, this report, the execution guide, implementation status, and `.gitignore` updated.
- Existing `PhysicalObject`, annotation schema/endpoints, Kotlin app, live detector,
  companion, and presentation code are unchanged.

A local track is identified by an integer plus generation and session epoch. Only an
accepted association carries a persistent UUID. Uncertainty clears that UUID before
scheduling reasoning. The worker cannot overwrite a newer generation or session; its
structured proposal must pass validation and a separate acceptance policy. Annotation
retrieval then checks the active session through the existing authenticated API.

Remaining limitations are explicit: no real laptop benchmark, no real VLM inference,
uncalibrated real-world appearance gates, untested DINO runtime, simple greedy tracking,
manual local gallery maintenance, and no Android/live-service integration. No improvement
in physical-object recognition has been claimed from mock tests.
