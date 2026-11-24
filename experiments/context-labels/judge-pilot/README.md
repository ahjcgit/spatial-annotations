# Can the judge correct a wrong tracker suggestion?

**Pilot result.** On two clearly visible bottle bodies, the judge corrected both deliberately flipped suggestions. It did so with the current view alone and again when given the older photo. It withheld both enrolled notes on the covered cap and on unrelated packaging. These were four familiar archived regions, reviewed in one ongoing Codex conversation. The 30-take same-model field study still requires new recordings and independent truth.

| Target in current photo | Genuine nearest-gallery hint | Flipped hint | Judge action in both hint conditions |
|---|---|---|---|
| Orange bottle after swap | B | A | Assign B to the outlined orange body |
| Silver bottle after camera returns | A | B | Assign A to the outlined silver body |
| Cap above bag, body hidden | A | B | Propose B as a candidate and request a body view. Withhold the note |
| Clear food packaging | A | B | Clear the label |

The comparison comprised **20 actual visual reviews** plus four local baseline decisions. Median local preparation-through-decision time across visual reviews was **5.28 s** (3.71–15.98 s). Median local process CPU was **6.47 ms** and median sampled resident memory was **61.74 MiB**. Timing includes image tools, writing the short cue, and returning the answer. Provider compute, tokens, energy and glasses latency were unavailable. The local baseline had no independent calibration for this pair and abstained. Its raw nearest-gallery ranking identified both clearly visible bodies. The deliberately flipped suggestions were controlled interventions; the pilot does not establish improved accuracy over the genuine baseline.

**Second-look test.** In a separate replay, both policies judged the same two initial views of B. The adaptive judge accepted the clearly visible orange body immediately and requested one later view for the covered body. It accepted B after the reveal. The fixed policy also inspected the next available photo after the clear view. Totals were **3 calls for adaptive and 4 for fixed**. The 113.8-second interval from covered photo to reveal came from the original capture schedule. No wearer was following the reviewer's instructions in that recording.

**Detector check.** Actual NanoDet Plus 416 inference with the study's 0.50 box-IoU criterion matched **1 of 7** archived focal boxes. One of the seven was a background negative and one was a cap-only box. The one match was the enrollment view. Check detector coverage early on the new objects. The manual-box pass can still measure identity decisions when the detector misses. The runner exercised 133 scheduled initial decisions per pass with a deterministic mock: 126 mock requests for manual boxes and 18 for cached detections. Those are interface checks.

### Evidence and reproduction

- [Per-arm results](report/report.md), [per-decision suggestions, cues and outcomes](report/decisions.csv), [per-take and condition counts](report/by-take-and-condition.csv), and [resource and timing summary](report/summary.json)
- [Raw hint-challenge responses](run/events.jsonl) and [configuration](run/run.json)
- [Adaptive and fixed-look results](second-look-report/report.md), [each follow-up action](second-look-report/decisions.csv), and [raw second-look responses](second-look-run/events.jsonl)
- [Cached NanoDet outputs with pinned model hash](nanodet-cache.json)
- [Installation, scoring and collection commands](../../../docs/LABEL_JUDGE_RUN.md) and [field-study design](../../../docs/VLM_LABEL_JUDGE_STUDY.md)

The card contains only enrollment photos, the current outlined scene, the allowed causal views and the assigned hint. Ground truth was used only by the scoring step; the conversational reviewer had seen these archive photos in previous work. The same alias receiving a correct note on two replays of the same photo contributes one physical opportunity. A future reveal is scored as a separate observation. All reported label actions were offline.
