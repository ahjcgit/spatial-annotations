# Next glasses study · Can the VLM judge when a note belongs on an object?

**Primary question.** On the same incoming view and the same proposed identity, does a VLM with recent visual history let the wearer select the correct physical object before the scene changes more often than the local policy alone? Count displaying the wrong note and leaving an old note on screen as failures even if corrected later. The [archived replay](../experiments/context-labels/temporal-judge/README.md) motivates testing harder transitions: earlier photos changed zero of eight paired decisions.

Use the [experiment runner and field commands](LABEL_JUDGE_RUN.md) and inspect the [executed wrong-hint and second-look pilot](../experiments/context-labels/judge-pilot/README.md).

### 1. Prepare the objects and blind the evaluation

Use three items of the same model and color. Enroll A and B with front, back and side references showing persistent body details such as a dent or seam. Keep C unregistered. Use two different harmless notes. Define identity as the body and record an underside ID the wearer’s camera cannot see. Keep a truth log with body ID, side, accessory, actual manipulation and timestamp. Capture an independent witness view or check the hidden IDs at each reveal. Seal the truth before reviewing predictions. Use opaque request IDs and strip note text, filenames, truth, spoken instructions and setup labels from model inputs.

Reserve a separate practice recording for lighting, camera settings, action rules, thresholds and timing. Freeze the model revision, prompt, context budget, detector, calibration and randomization before the first held-out take. Begin with six practice/feasibility takes, one per row below. For the first scored study record **five independently restaged takes per row (30 takes)** over at least two sessions. Alternate starting sides, concealment side and orientation. Randomize condition order within session. Score the five takes as a small pilot; replicate with another physical pair before claiming generalization.

Use the [30-take operator sheet](../experiments/context-labels/temporal-judge/next-takes.csv). It assigns 15 takes to each session and balances the starting side as closely as five replicates allow. Keep this operator sheet outside model inputs.

### 2. Record transitions that distinguish reasoning from a position shortcut

Record a clear start, an ambiguity and a reveal in each take. Log exactly when each identifying cue is visible and when the current side/identity becomes obsolete. Vary the manipulation independently of the camera motion.

| Condition, five takes each | Operator’s manipulation | What the judge should demonstrate |
|---|---|---|
| Unchanged after cover | Hide both bodies, leave them in place, reveal a distinguishing body mark. | Withhold on unsupported evidence and recover the correct note at reveal. Tests the cost of needless abstention. |
| Move while hidden | Use the same cover and duration, swap the bodies, reveal in reversed positions. | Update the location of each note using current body evidence. The old left/right assignment is a deliberately misleading cue. |
| Substitute a lookalike | Replace B with unenrolled C at the same spot under cover. Keep A visible as a control. | Reject B’s old label on C, even when the location and gross appearance agree. |
| Transfer a familiar accessory | Move B’s lid or sleeve to A or C. Expose the misleading feature first, then the permanent body detail. | Keep the note with its body. Log whether the proposed explanation cites the transferable feature. |
| Continuous crossing and turn | Move both objects through a crossing while the wearer changes angle. Preserve continuous video, then replay a version with the crossing interval withheld. | Compare a genuinely continuous association with the same endpoint after a gap. Treat the two replays as paired versions of one take. |
| No distinguishing evidence, then second look | Hide both body cues; offer a side-step that reveals one. End on an empty scene. | Ask for a specific new view or abstain, recover when evidence appears, and clear the label when the target leaves. |

For obscured or indistinguishable views, record both the physical truth **and whether the available pixels support identity**. A lucky guess is a wrong policy action whenever the protocol requires withholding. Do not fabricate a visual explanation for an invisible mark.

### 3. Compare the judge and the controller separately

Run these arms offline on the exact same recordings. First give all arms the same manually reviewed boxes. Repeat with cached detector outputs and itemize missed detections. Start with a single authorized advanced endpoint. Capture new timings for that endpoint. Each paired inference gets a fresh, stateless context.

| Arm | Inputs and decision |
|---|---|
| Local baseline | Geometry and appearance choose the identity or abstain using frozen development settings. |
| Direct VLM recognition | Gallery and current scene; the VLM proposes identity, evidence and a label action without seeing the tracker's guess. |
| VLM as second reviewer | Supply the identical current input plus the tracker's candidate alias. Ask it to accept, correct, or abstain. Include disagreements and candidate-free cases. |
| Temporal reviewer | Same candidate and current inputs, plus the last verified frame, its age and any observation gap. Compare with a duplicated-current-image control of the same dimensions to isolate the value of history from extra image budget. |
| Event-triggered controller | Use the local result on ordinary movement; invoke the winning reviewer only at conflict, crossing, reappearance or ambiguity. Let it request one new view. Compare with a fixed side-step at the same extra-view budget. |

**Test resistance to a wrong suggestion.** On an explicitly flagged offline copy of held-out requests, substitute the other plausible candidate or no candidate, keeping the pixels fixed. Compare the fraction of wrong suggestions accepted or corrected. Save the genuine detector/tracker run separately. For the history arm, compare correct recent evidence with genuine but stale pre-swap evidence. Never send future reveal frames in a pre-reveal request. Repeat nondeterministic model calls up to three times within a preauthorized call/cost cap. These repeats measure response variation within one take.

**Judge output.** Store region ID, proposed alias or unknown, recommended action, one observable cue and which image contains it. Actions include show, keep, move, verify, request another view, and clear. The host validates the current request ID, track generation, contradictory simultaneous identities and scene freshness before applying anything. It resolves permitted notes with the active user’s authenticated backend. A model proposal cannot grant access. Keep proposals, accepted actions, actual screen commits and wearer responses as separate fields.

### 4. Score usefulness, safety and cost together

* **Primary:** fraction of all planned target opportunities where the correct note reaches the correct body before the view becomes stale. Denominator includes detector misses, withheld notes, timeouts and late replies. Report per take, then per condition.
* **Wrong-object risk:** wrong-body notes per target opportunity, any false note per decoy/empty checkpoint, and takes with any wrong note. Measure time a stale note remains visible. Report verify/clear decisions separately from failures to recognize identifiable bodies.
* **Judgment:** count correct acceptances, corrections of wrong candidates, incorrect overrides of correct candidates, and justified abstentions. Independently code whether the cited cue is visible and instance-specific. Have a second reviewer resolve disagreements where available.
* **Recovery and resource use:** log ambiguity onset, cue reveal, request dispatch/receipt, label commit and wearer selection. Compute intervals within a single clock domain; summarize each stage separately. Report recovery failures, correct labels gained per extra call, calls per recorded minute, token usage, cost, CPU time, sampled resident memory, thermal state and energy when a meter or device counter is available. Use matched brightness, camera load and duration for idle/local-only and reasoning runs. Instrument the endpoint separately if its GPU counters are accessible.
* **Decision:** promote temporal review only if it gains correct-on-time notes across paired takes without increasing wrong-object or decoy labels. Investigate any false private note before a wearer-facing trial. A request for another view is valuable only when the extra correct answers justify the extra wait and movement. With five takes per condition, present counts and paired outcomes; an observed zero cannot establish a zero error rate.

### 5. Use glasses time where it matters

Preflight the snapshot bench and record its version using the [field-session checklist and commands](CONTEXT_LABEL_GLASSES_SESSION.md). Capture the six practice takes using harmless notes. The current debug bench supports discrete snapshots and side cues. Use a validated continuous recording path for motion and a clear camera-source label for any external recording. Once the offline comparison selects a policy, run a counterbalanced wearer test with the baseline and that policy. Ask the wearer to point to the body named by each note, allow “cannot tell,” and record correctness, response time and whether the label was still current. Preserve held-out sequences, references, truth, model configuration, raw proposals, policy decisions, screenshots, resource traces and failures together under one run ID.
