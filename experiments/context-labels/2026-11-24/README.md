# What does the surrounding image add to a bottle label?

On November 24 we used conversational Codex vision to read 12 regions from four archived RayNeo photographs twice. Three plain patches could be identified only after we showed the rest of the bottle. A nutrition label on a bag remained unassigned even though the registered bottle was directly behind it.

| Presented evidence | Correct bottle identity / 9 target regions | Wrong bottle | Withheld on bottle | Background left unlabeled / 3 |
|---|---:|---:|---:|---:|
| Grayscale patch + A/B references | 6 | 0 | 3 | 3 |
| Same target outlined in its grayscale scene + same references | 9 | 0 | 0 | 3 |

**Unit of analysis:** a region of an archived photo. The nine target regions share three two-bottle photos. An additional target-free photo supplies two of the three negative regions. The reference pair comes from a fifth photo. These counts describe this particular read.

The [timed follow-up](usability/README.md) repeats all 24 visual decisions and records per-decision turnaround, CPU, resident memory and input size.

### Inspect the experiment

1. Open the [enrollment pair](references.png). A has a narrow screw closure, tapered shoulders and vertical lettering. B has a wide hinged closure and prominent collar.
2. Read the [shuffled grayscale patches](probes.png). For each card, decide whether the target surface belongs to A, B, or neither/insufficient evidence. Record one visible reason. Only the card ID is printed.
3. Inspect the same targets outlined in the [first](context-1.jpg), [second](context-2.jpg) and [third](context-3.jpg) scene sheets. The answer applies to the outlined **surface**, even if a familiar object is nearby. The pages preserve source dimensions and remove color. The crop cards fit their tiles and therefore have a different apparent scale.
4. Compare the [crop decisions](decisions.csv), [scene decisions](context-decisions.csv), [region coordinates and source hashes](key.csv), and [scores](results.json).

**What changed.** P02 and P11 looked like smooth gray material. In the wider image the surface continues to B’s hinged lid. P04 showed a reflection. The adjacent lettering and neck associate it with A. P10 outlined the foreground bag, so proximity to B provided no basis for displaying B’s note. On P08 the latch alone identified B within the enrolled pair. The same latch on a second bottle of the same model could produce a wrong personal label.

**What moving the bottles changed.** In the [enrollment photo](../../codex-glasses/2026-11-19/qualitative-baseline/trial-01/source.jpg) A is on the left. In the [swapped photo](../../codex-glasses/2026-11-19/qualitative-baseline/trial-02/source.jpg) and [uncovered photo](../../codex-glasses/2026-11-19/qualitative-baseline/trial-04/source.jpg), B is on the left. Keeping enrollment sides would misplace all four labels on those two clear snapshots. Both full scenes have visible cues to the correct pair. In the [intervening photo](../../codex-glasses/2026-11-19/qualitative-baseline/trial-03/source.jpg), the bag hides B's body. If the label follows the body and the cap could belong to a lookalike, withhold the personal note until a body detail is visible. These snapshots establish ordering and appearance. They do not record the motion between captures.

**Cheap appearance comparison.** We also ran the repository's CPU `color-grid-v1` descriptor on the two clear post-swap photos above. We manually boxed each entire bottle, converted the boxes and enrollment crops to grayscale, and ranked both references by cosine similarity. Fixed enrollment sides were correct on **0/4** bodies. Nearest appearance ranked A first on all four bodies, giving **2/4** correct. Both B crops also ranked closest to A. These are raw rankings with no rejection threshold. H1 additionally tracks over time and can abstain after calibration. This check uses four whole bottles, so its denominator differs from the 12-region context experiment. [Per-box coordinates and scores](clear-swap.csv)

**Scope.** This was an actual conversational image read. The same session selected the regions, knew the previous pilot and read the crop condition first. It had access to the key when interpreting the full scenes. We used source membership as the scoring key. There was no independent adjudicator, masked evaluator, timed provider call, held-out pair, hardware display, or permission lookup in this replay. The two enrolled bottles differ in construction. Enlarging the view supplies more pixels and more object parts. The result motivates testing spatial context. It cannot isolate temporal reasoning, establish instance recognition among identical products, or estimate production error rates.

### Reproduce the inputs and counts

From the repository root, with Pillow installed in the project environment:

```bash
.venv/bin/python experiments/context-labels/2026-11-24/make_inputs.py
python3 experiments/context-labels/2026-11-24/score.py
# Requires the existing identity environment (NumPy + Pillow)
.venv/bin/python experiments/context-labels/2026-11-24/clear_swap.py
```

The scorer recomputes the paired results from the saved reads. An independent replication should show the two conditions to fresh model sessions in randomized order, using opaque IDs and withholding the key. The [RayNeo session protocol](../../../docs/CONTEXT_LABEL_GLASSES_SESSION.md) defines the next test.
