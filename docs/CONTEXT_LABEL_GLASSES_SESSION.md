# RayNeo field session · Which object should carry the note?

**Decision to make:** when two objects look alike, does giving an advanced vision model an overview or an earlier verified view help the wearer find the correct object? Count a visible wrong note as an error even if the system corrects it a moment later.

The [VLM label-judge study](VLM_LABEL_JUDGE_STUDY.md) specifies the paired comparisons, manipulation schedule and scoring for the next collection.

### Bring and enroll · 10 minutes

Use two bottles of the **same model, finish and color** with small stable differences, plus an unregistered third if available. For example, A has a dent near its base and B has a worn seam on its handle. If using laptops, try a corner nick and a worn hinge. Inspect both objects before choosing the cues. Use the body as the identity that owns the note. A detachable lid, sleeve, position on the table or neighboring charger can all move independently.

* Give A and B different harmless test notes, e.g. “Bring to desk” and “Leave on shelf.” Keep the mapping on the operator laptop. The model receives neutral candidate aliases and reference photos. Retrieve private or group notes only after accepted identity and authenticated backend authorization. The snapshot bench displays operator-supplied text and can use the harmless test notes directly.
* Photograph each object alone from front, side and back. Keep these reference photos separate from challenge captures. Use a hidden underside ID or an inventory log for operator truth. Keep ID marks, filenames, notes, hands indicating the answer and condition names out of inference inputs.
* Prepare a shuffled order of independent takes. Balance A starting left/right and near/far. Keep camera settings and lighting comparable within each paired replay. Keep one separate practice take for display setup and thresholds. Freeze the test order, prompt, acceptance rule and event checkpoints before scoring.

### Capture · first 45–60 minutes

Start with the first three rows. Record two independently restaged takes per row. Each take has three decision points: an identifiable start, the challenge, and a reveal. For a larger study, collect at least five independent takes per condition across sessions. Annotate whether the prior → current interval was continuously observed, interrupted, or unavailable.

| Priority and condition | What to do | What would count as useful behavior |
|---|---|---|
| 1. Unseen swap and unchanged control | Wearer turns away. Randomly swap both bodies or leave both alone. Return with the objects viewed from a new side, then reveal the body marks. | Correct note follows the body across the swap. A hidden cue may justify a neutral display until the reveal. |
| 2. Viewpoint, occlusion and a second look | Walk around the pair. Place a bag over just the identifying mark, leaving the rest visible. Step sideways to see the mark again. | Measure when the note disappears or stays supported and when it returns. Never attach the hidden bottle's note to the bag. |
| 3. Unregistered replacement and transferable cue | Temporarily replace B with a third same-model bottle at B's old spot. In a separate take, exchange compatible lids or sleeves while the bodies stay put. | No B note on the decoy. No identity switch solely because the accessory moved. Record which supporting body feature is visible. |
| 4. Continuous crossing vs interrupted crossing | Slide the pair past each other in view, then repeat with the crossing behind a screen. Match the final poses. | Test when motion continuity genuinely helps and when re-identification is necessary. Use a continuous video for this condition. |
| 5. Misleading scene and ambiguous evidence | Move A beside B's usual charger or notebook. Turn both distinctive sides away, then remove both objects. Include another take with changed lighting or a reflection. | Familiar surroundings alone never trigger a personal note. Measure rejection on lookalikes, reflections and an empty scene. |
| 6. Delayed result while the wearer moves | Capture a clear view, move the objects or wearer before returning the result, then capture the new view. Use neutral test labels throughout. | Suppress the obsolete result and record the new decision. Score stale labels separately from recognition mistakes. |

**Acquisition.** The existing debug bench produces one JPEG per capture and a fixed list with side cues on the glasses. For viewpoint, swap and occlusion checkpoints, keep each scene stable through the display/readback, then log movement between checkpoints. For continuous crossing, record separate uninterrupted first-person video with a tested recording path. A phone camera can supply an offline comparison if the glasses only produce stills. Mark the camera source and keep its timestamps separate. Sparse stills alone cannot measure time spent tracking through a crossing.

**Bench on the laptop.** Use the [build, install, permission and submission instructions](CODEX_GLASSES_BENCH.md). Plug in the glasses. In the repo, replace SERIAL with the value from ADB and the two names with the independently verified enrollment descriptions. Choose an available bench port. The existing USB control bench accepts loopback requests on the laptop.

```bash
adb devices -l
ss -lnt '( sport = :8028 )'
.venv/bin/python scripts/codex_glasses_bench.py --serial SERIAL \
  --objects "bottle with base dent" "bottle with worn seam" \
  --out "artifacts/context-labels/$(date -u +%Y%m%dT%H%M%SZ)"
# In another terminal, once per checkpoint
curl -fsS -X POST http://127.0.0.1:8028/capture
# Save the actual decision in response.json with returned requestId and sourceSha256
curl -fsS --max-time 75 -H 'Content-Type: application/json' \
  --data-binary @response.json http://127.0.0.1:8028/submit
```

For unsupported identities send an empty labels list or omit the unsupported object. If the scene changed during review, submit an empty list, log the reason and recapture. This is a manual freshness check for this bench. Its request ID and image hash bind the reply to the saved image, while the wearer can still turn away. Score the wearer pointing at the body that goes with each note. Record “left/right at capture,” clipped, unreadable or unclear as applicable, plus any incorrect or lingering text. Wearer readback and software frame commit are separate observations.

### Replay the same captures after the session

1. Save the raw frames or clips, shot order and reference gallery before making evaluation crops. Have a reviewer verify visible boxes, physical IDs, decoys, cue visibility and checkpoint times against the operator log. Record uncertain truth as such. Assign opaque filenames; withhold the key from the inference session.
2. Compare geometry + appearance (H1) with three advanced-model inputs on **exactly the same decision points**: **crop + references**, **crop + current overview + references**, and **the preceding inputs + at most two earlier observations**, identified by age and any observation gap. Include a stale-history control with the genuine pre-swap observation. Never include a reveal taken after the decision. Run each condition in a fresh session, shuffle order, fix image limits and report how many image tokens each variant actually consumed. Choose the model revision, prompt, inference settings and call cap in advance. The existing [identity evaluation guide](IDENTITY_H0_H4.md) covers H1/H3 and manual-box versus detector replay. The additional context variants can be submitted independently in fresh sessions and logged explicitly.
3. Use one fixed instruction: “Which enrolled body, if any, owns each outlined surface? Return the region ID, A/B/unknown, the visible distinguishing evidence, and whether it comes from this view or an earlier one. The earlier association may be stale. A nearby item, removable part or familiar side alone is insufficient.” Save raw proposals separately from accepted identities. Require a visible instance-specific cue or documented uninterrupted continuity from a verified view. An unsupported or conflicting proposal stays neutral. A simultaneous duplicate identity stays unresolved.
4. First provide human-reviewed boxes to isolate identity. Then replay the same takes with shared detector outputs and count missed boxes separately. After this paired comparison, measure event-triggered reasoning at actual ambiguity events and compare with H1 on the same stream. Store request start/end, model/version, returned usage, failure, track generation, image hash and accepted/displayed alias. Keep note text and credentials out of inference logs. Compare the event-based system with one using only H1 on the same takes.

### Score per take, then summarize across takes

| Outcome | Measurement |
|---|---|
| Correct coverage / wrong identity / abstention | Divide each count by all expected enrolled-object checkpoints, including detection misses as abstentions. Report all three and counts by condition. |
| False label on a decoy | Decoy/empty checkpoints with any unsupported object label divided by all such checkpoints. Check foreground occluders separately. |
| Identity recovery | From first verifiable cue after the event to the first accepted correct label. Record unrecovered cases. For sparse stills, report checkpoint counts or time intervals rather than continuous latency. |
| Wearer result | Correct body selected, wrong body selected, no label, or unreadable for each prompted note. Count obsolete notes shown after a scene change. Save a screenshot and the wearer's response. |
| Cost and latency | Calls per take and per recorded minute, endpoint request duration, response-to-device commit, and device frame-to-commit. Use a single monotonic clock for each interval. Record tokens/cost if returned. Conversational review includes orchestration. |

Use one log row per take/checkpoint/region/method. Record the take ID, condition, timestamp, image hash, region, true body, cue visibility, proposed/accepted/displayed identity, rejection reason, wearer selection and timing-log path. Keep the truth and wearer response in separate files from the conversation. For solo operation, timestamp the hidden identity check after each take and flag the lack of independent review.

**Usability measurements for the next session.** The [timed replay](../experiments/context-labels/2026-11-24/usability/README.md) supplies an offline reference. For each real ambiguity event, mark the last instant the same body and side cue are still valid, then determine whether the correct label reached the wearer before that deadline. Record the fraction of all expected notes that are correct and on time, the fraction shown stale, and the abstentions. Retain the source timestamps on their own clock. Log model version, queue and request latency, provider usage/cost where available, and Android CPU/RSS per phase. Compare equal-duration no-reasoning and reasoning runs for thermal or measured device power under the same brightness and camera load. Report missing counters explicitly.

**Decision rule.** Prefer added context if it recovers more correct labels at equal or lower wrong-object rates across paired takes and the display still arrives while its supporting view is valid. Treat any note on an unregistered decoy or stale scene as a failure to investigate before displaying private content. Report counts such as “recovered in 3 of 5 occlusions” by independent take. Record the latency and cost of those recoveries before choosing a model or a live refresh policy.
