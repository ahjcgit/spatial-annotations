# RayNeo presentation measurement workflow

This workflow measures two particular physical objects using real RayNeo camera images: the hand sanitizer (expected COCO class `bottle`) and yellow toy motorcycle (`motorcycle`). The toy is a domain-shift stress case, not a representative sample of full-size motorcycles. Preserve misses and incorrect classifications as results.

## What can be measured now

| Question | Measurement | What it establishes / limit |
|---|---|---|
| Does detection deteriorate with distance? | Trial detection rate at near/middle/far; manually boxed object height as % of image height | Ordinal position and apparent size, **not maximum range in meters** without measured distances |
| Does viewing angle matter? | Front/oblique/side detection rate with distance fixed | Approximate viewpoints, **not accuracy at exact degrees** |
| Does the label follow an object during head movement? | Box-center error, top-center anchor error, residual jitter, consecutive misses, sampled reacquisition | Image-space detector stability. This is a box-anchor proxy; the desktop label itself can switch above/below the box. It does not measure physical optical registration |
| Do objects differ? | Same protocol on sanitizer and toy, plus an empty scene | Two instances only; does not establish general category accuracy |
| Would another detector help? | NanoDet Plus 416 vs YOLOX-S 640 on identical saved images; hit rate and CPU time | Paired offline comparison at native configurations. YOLOX is not yet integrated into the live glasses app |
| What latency can we show? | Median/p95 replay model time; live inference and app pipeline time; source-frame intervals | Measured stages, **not sensor-to-display latency**. CPU-only comparison does not establish GPU speedup |

Current app labels come from repeated detections, not an independent temporal tracker. The demo retrieves personalized notes for the selected bottle. The evaluation captures all detection classes, including motorcycle, even when the bottle-specific demo shows no label. Thus motorcycle detection results must not be presented as a completed motorcycle annotation demo.

## Start the bench

Run from `spatial-annotations`, with the existing live demo backend and dashboard running on ports 8013/8014 and the glasses connected by USB:

```bash
# Existing project backend/vision dependencies are also required.
.venv/bin/python -m pip install -r scripts/requirements-evaluation.txt
.venv/bin/python scripts/setup_vision.py --yolox
.venv/bin/python scripts/evaluate_demo.py serve
```

Open **http://127.0.0.1:8017**. No login. The bench only binds to localhost. Keep the computer's live dashboard tab closed during collection to reduce duplicate ADB polling. The bench preview is a manual snapshot rather than another continuous polling stream.

The app build used for collection should include `sourceFrameTimestampNs`, `acceptedAtElapsedMs`, and `resultAtElapsedMs`. Older builds can still record, but source-time intervals are unavailable. The camera timestamp is a device sensor clock; host monotonic time is a separate clock. Do not subtract one from the other. Android `pipelineMs` starts at accepted-frame processing and ends before publishing, and can include note retrieval when a single target bottle is found. It excludes display presentation and earlier camera exposure/queueing.

## Pilot: 11 trials

The plan contains the following **for each object**:

1. Near, front, still — 5 seconds.
2. Middle, front, still — 5 seconds.
3. Far, front, still — 5 seconds.
4. Middle, oblique, still — 5 seconds.
5. Middle, front, slow head pan — 8 seconds.

Plus one 5-second **empty scene**, with both test objects removed. This is 61 seconds of recording, plus repositioning and review. There are roughly 15–30 saved frames per trial at current rates; allow substantial time for manual annotation. Use the pilot to check practicality before attempting the repeated protocol.

The saved plan shuffles trial order with a reproducible seed to reduce systematic ordering effects. For a setup check it is acceptable to start with sanitizer/middle/front/still; record that departure and do not claim randomized execution. A trial selection remains explicit so no recording starts while the wearer is moving into position.

### Wearer/operator instructions

- Wear the glasses. Keep lighting, table/background, camera orientation and object uprightness consistent. Remove the other test object and avoid additional bottles or motorcycles in view.
- Choose three repeatable positions; mark them with paper or existing desk landmarks. Write the landmarks in the notes. Start with an easily visible middle position, then a clearly nearer and a clearly farther one. Do not assign guessed cm values.
- Keep the camera approximately at the same height. Define sanitizer **front** as the printed label toward the camera, and toy **front** as its broad side toward the camera. For oblique/side conditions rotate the object in place; keep its position fixed. Record these definitions because front does not mean the toy's headlight end.
- Choose the planned condition, enter setup notes, and click **Record after 3-second countdown**. Hold still for static trials. Remain in position until the status says captured.
- Slow pan: keep the object stationary; turn your head gently left to right and back, trying to keep the object in view. Do not translate the bottle to follow the glasses. “Slow” is an approximate instruction, not a measured angular velocity.
- Retain failed detections. Redo only a protocol failure such as recording the wrong object, an interrupted app, or an unintended position. The UI can exclude/reinclude a trial only with a reason; it preserves both the original capture and that reason. Record all attempts. Do not retain only the successful one.

All images and results stay locally under ignored `artifacts/evaluation/pilot/`. They can contain the surrounding room: inspect/crop any screenshot intended for public slides separately, retaining the original evaluation images unchanged. Saved measurement records omit note text, user credentials and tokens.

### Ground truth

Select a captured trial in section 2. Draw a tight box around the visible object, including its cap/pump or wheels as applicable, excluding shadow. Use a consistent visible-extent convention for every frame. Save and next. No model prediction is shown while drawing. For nearly still frames, **Copy previous reviewed box** can reuse your preceding annotation, but inspect its fit and redraw if needed before saving; copying does not mark the frame reviewed.

- **Visible:** the object can be identified and boxed, including when the detector missed it.
- **Absent:** the object is outside the image. A missed detection is not absence.
- **Uncertain:** the frame cannot be judged (for example severe blur). This is not a successful or failed detection; it is excluded and lowers usable coverage.

Review every captured frame. Condition-level plots require all frames to be usable and the recording duration to be completed; partial/uncertain trials remain in frame/trial CSVs with coverage, but do not silently become full-coverage scores. An interrupted/uncertain trial should be reported, and a protocol-clean replacement should be recorded when practical. Have a second team member independently review a small random subset (for example 10%) for consistency. Do not copy detector boxes into ground truth.

### Compare and export

Click **Replay both models**. It pauses the glasses demo to reduce competing CPU work, warms each model for three iterations, alternates execution order on successive identical JPEG bytes, and resumes the demo afterward. Close unrelated CPU-heavy applications; keep power mode unchanged. Replays preserve images' checksums and model provenance. Avoid changing annotations while replay/export runs.

Then click **Export metrics and figures**. CSVs and static PNGs appear in `report/`:

- `frame_metrics.csv`: per-frame truth availability, detection success, localization and timing.
- `trial_metrics.csv`: trial hit rate, false-positive rate, median errors, jitter, missed-frame run, reacquisition success/censoring, median/p95 timing and coverage.
- `condition_metrics.csv`: averages of **trial** summaries, with trial counts. Frames within a trial are correlated and are not independent repetitions.
- `summary.json`: definitions, threshold, model metadata, warnings and capture inventory including excluded/failed attempts.
- `detection.png`, `placement.png`, `timing.png`: generated only when applicable evidence exists. Dots are means of trial summaries; error bars are trial min–max, **not confidence intervals**. `n` is trials. With a single trial there is no repeatability estimate.

CLI alternatives:

```bash
# Stop live inference yourself before CLI replay.
.venv/bin/python scripts/evaluate_demo.py replay --root artifacts/evaluation/pilot --repeats 3
.venv/bin/python scripts/evaluate_demo.py analyze --root artifacts/evaluation/pilot
```

Repeated inference runs measure timing variability, not additional physical trials. Changing the dataset after replay requires replaying again for a complete paired comparison.

## Metric definitions and safeguards

- **Detection hit:** highest-confidence prediction of the expected category, confidence ≥ 0.35, intersection-over-union (IoU) ≥ 0.50 with the reviewed box. Wrong category, missing prediction or insufficient overlap is a miss. This evaluates selecting the highest-score expected-category candidate; it is not COCO mAP and is not the app's stricter exactly-one-bottle label-display rule.
- **False-positive frame rate:** fraction of reviewed absent frames with a prediction of the expected class; in empty scenes, either bottle or motorcycle counts. Additional unrelated categories are retained in raw predictions but not counted by this target-focused metric.
- **Placement proxy:** distance between predicted and true box top-centers, as % of image diagonal. Also export center error. These errors are conditional on a prediction: always show detection coverage alongside them. They are not text readability or pixel-perfect renderer tests.
- **Residual jitter:** change in (predicted center − true center) across consecutive reviewed sampled frames, in % image diagonal. Object/head movement is removed using ground truth. Report separately for still and moving trials. This does not prove temporal tracking or capture-to-display stability.
- **Dropout:** longest consecutive visible-frame miss run. Unit is **recorded frames**, not seconds or unseen sensor frames.
- **Reacquisition:** time from first reviewed visible frame after absence to first IoU50 hit. Host-observed timing is coarse and includes polling variability. A first-frame hit is 0 ms **at this sampling resolution**, not instant physical response. Report unreacquired/censored events as well; successful-only medians can otherwise mislead.
- **Model time:** OpenCV CPU call including adapter preprocessing, forward pass and NMS. Replay `total_ms` additionally includes JPEG decoding and outer resize. Live `total_ms` is the different app pipeline measurement: do not compare these columns as equivalent end-to-end measurements. Both models use two OpenCV threads; their native sizes/preprocessing/NMS settings differ (NanoDet 416, NMS .6; YOLOX-S 640, NMS .5). Identical confidence numbers do not imply calibrated operating points.

Primary model references: [OpenCV Zoo YOLOX](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox), [OpenCV Zoo NanoDet](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_nanodet). Both pretrained models/adapters are reused work, not team-trained models. Team contributions here are device integration, capture/export, evaluation, and personalized annotation behavior.

## Repeated protocol and next experiments

```bash
.venv/bin/python scripts/evaluate_demo.py serve --profile full --root artifacts/evaluation/full --port 8018
```

The full plan adds middle/side/still, middle/front/fast_pan and middle/front/exit_reenter, and uses three independently repositioned repetitions of all conditions, including empty scenes: **51 trials**. It varies one factor at a time rather than testing every distance × angle combination. A new root prevents overwriting pilot data or mixing different plans. Review burden can exceed an hour; finish a smaller stated subset well rather than implying all 51 are complete.

For exit/reenter, start with the object visible for about 2 seconds, turn away for about 2 seconds, then return for the remaining time. Annotate the absence explicitly. Fast pan should use the same sweep endpoints as slow pan; angular speed remains approximate. If trajectories and rates need to be compared quantitatively, add measured motion/IMU synchronization later.

For optical alignment, run a **separate wearer study**: calibrate the label at the middle position, keep calibration fixed, then rate overlap/readability at near/far and after head movement (for example inside/partially overlapping/off-object; readable yes/no). Record user, eye configuration, display mode and adjustment values. These are subjective observations, not metric 3-D registration error. Accurate physical error needs a calibrated camera/display mapping or an external through-lens reference setup. Do not use desktop screenshot error as a substitute.

For stronger model conclusions, add multiple physical instances/backgrounds and hold them out from parameter tuning. Freeze thresholds before final evaluation. A useful next ablation is current re-detection alone versus temporal smoothing/tracking, evaluated on the **same recorded motion sequences** and paired with latency/lag. Better inference hardware can then be compared using those same frames and timing definitions.

## Milestone 3 use

For P10's November 12 checkpoint, the initial four-slide PDF is due **November 10, 2026, 4:00 p.m. Los Angeles time**, per the supplied course instructions. Prioritize a completed pilot and honest evidence over the full matrix. One compact figure can show detection rate and processing time for both objects/models, with a static example and explicit trial counts. Label results “preliminary; approximate geometry; one instance per object; alternative model evaluated by recorded-image replay.” Put the larger protocol, optical alignment limitation and tracking risk on slide 4. Do not claim ranges, exact viewing angles, world-locked AR or general object accuracy from this pilot.
