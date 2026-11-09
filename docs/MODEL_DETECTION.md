# Optional object detection, without printed QR codes

The app can now send one camera frame to the configured local backend, which runs
**NanoDet Plus 416 (OpenCV CPU)**. It returns categories, confidence scores and boxes.
Android freezes the frame, highlights the selected detection, asks which registered
object it represents, then retrieves that object's normally permission-filtered notes.

**A category is not a persistent identity.** Both Mug A and Mug B are `cup`. The user
must explicitly confirm A or B; the model does not distinguish identical physical mugs.
The internal UUID still identifies each database record, but this mode never reads a
printed QR. A mistaken user selection can retrieve the wrong object's *authorized*
notes. QR remains the reliable automatic instance-identification option.

This is image-space detection, not SLAM, tracking, pose estimation or world anchoring.
No training, cloud inference, paid API or proprietary SDK is required.

## Browser testing and integrated setup

The companion now supports **photo upload → model boxes → category selection → explicit
object confirmation → authorized notes**. Use the numbered [README test guide](../README.md).
The browser also provides an optional webcam preview and single-frame capture. It requires
HTTPS or localhost; photo upload works over ordinary LAN HTTP. Opening a preview uploads
nothing, and capture/stop/sign-out releases camera tracks. New input or category selection
clears previous notes; late responses cannot restore a signed-out selection.

For a fresh reproducible model demo, install the optional dependencies and run:

```bash
.venv/bin/python scripts/setup_vision.py --sample
source scripts/dev_env.sh
.venv/bin/python scripts/demo.py --vision --port 8013 --output artifacts/local-demo
```

Check that the port is free first. This creates/reuses its own dataset, sets cup categories
without overwriting other metadata, runs actual blank-frame inference, and verifies
persistence/build/tests. The manual server procedure below remains useful for an existing DB.

## Start on this computer

The prepared model backend is **http://192.168.1.76:8012**, sharing the existing demo
SQLite database with the QR service on 8011. Both listen on `0.0.0.0`. Local credentials
are in `artifacts/vision/demo-data.json` (untracked, mode 0600).

For a new setup, run the ordinary [quickstart](DEMO_QUICKSTART.md) first, then:

```bash
uv pip install --python .venv/bin/python -r backend/requirements-vision.txt
.venv/bin/python scripts/setup_vision.py
# Verify 8012 is free; choose another port if occupied. Never stop an unrelated service.
ss -lnt '( sport = :8012 )'
DATABASE_URL="sqlite:///$PWD/artifacts/demo/demo.db" \
VISION_MODEL_PATH="$PWD/artifacts/models/nanodet.onnx" \
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8012
```

On the companion at the new port, sign in as the object owner, look up A and B, and
set **Register / update object → Visual category → cup → Save object** for each.
Other NanoDet categories can be listed with `GET /vision/status`. Object metadata is
public; annotation permissions are unchanged. Up to 100 matching object records are
returned, so this is intended for a small demonstration dataset.

Install `android/app/build/outputs/apk/debug/app-debug.apk`, set its backend URL to the
model-enabled server, sign in, then choose **Detect objects · model**. Camera exposure
settles for four frames before one rotated grayscale JPEG is uploaded. Select a detected
category and explicitly confirm the physical object. Refresh/navigation work as in QR mode.
If the model is missing or a request fails, an error is shown; stop/retry or use QR.

Images are processed in memory and not saved by the API. Requests require authentication,
JPEG/PNG, at most 2 MiB and 4 million pixels. Concurrent inference returns 429 (retry).
CPU inference runs off the HTTP event loop and camera conversion runs off Android's UI
thread. Stop/rescan/account changes cancel requests and dismiss stale selection dialogs.

## Reproduce photo or webcam inference

The test photograph is Rachel Michetti's CC0 coffee image, courtesy of Pikolo Espresso
Bar, distributed by [scikit-image](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.coffee).
It depicts a coffee cup, **not either of the user's actual mugs**. Selecting Mug A/B in
replay explicitly simulates that human association.

```bash
mkdir -p artifacts/vision
curl -fsSL https://raw.githubusercontent.com/scikit-image/scikit-image/v0.19.3/skimage/data/coffee.png -o artifacts/vision/coffee.png
# Expected SHA256: cc02f8ca188b167c775a7101b5d767d1e71792cf762c33d6fa15a4599b5a8de7
.venv/bin/python scripts/vision_probe.py --data artifacts/vision/demo-data.json --image artifacts/vision/coffee.png
# When a webcam is exposed to the host:
.venv/bin/python scripts/vision_probe.py --data artifacts/vision/demo-data.json --webcam 0
```

On another computer, copy your local seed JSON to `artifacts/vision/demo-data.json`, keep
it mode 0600, and change only its `backend` URL to your LAN model endpoint. The probe logs
in with those local credentials but records only inference results, not credentials.
The webcam probe captures a frame after warmup; it does not validate Android Camera2.

For the already configured image-file emulator (run UI scripts sequentially):

```bash
source scripts/dev_env.sh
.venv/bin/python scripts/emulator_model_test.py \
  --camera-image-file /home/ahjc/projects/m202a/.toolchain/demo-scenes/current.png
.venv/bin/python scripts/record_sharing_demo.py
```

The model camera test uses the actual Android APK and backend, a photograph replayed
through the emulator's Camera2 input, explicit human-style A/B selection, and a blank
negative frame. It is **not a real webcam or physical RayNeo test**. The sharing recording
shows Alice, Bob, revocation and B isolation; identities in that separate recording are
explicitly supplied through manual SIMULATION. Credential entry is excluded from footage.

## Model provenance and measurement limits

[OpenCV Zoo NanoDet](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_nanodet)
is Apache-2.0. Its unmodified Python adapter and license are in `backend/app/vendor/nanodet/`.
Weights download from [OpenCV's official model mirror](https://huggingface.co/opencv/object_detection_nanodet)
and must match SHA256 `4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186`.
Weights are local ignored artifacts, not committed. `requirements-vision.txt` pins GUI-capable OpenCV 4.13.0.92, shared with the webcam utility;
OpenCV 5.0 output layout failed with the upstream wrapper. The dependency set is optional;
the ordinary QR backend remains usable without OpenCV.

`inference_ms` measures only the model forward pass plus its output decoding/NMS using
the backend monotonic clock. It excludes model loading, image upload/decode and user
confirmation. `vision_probe.py` also reports actual HTTP round-trip duration. Android
`model_confirmed_lookup` telemetry starts after the user's selection and measures note
retrieval/display; its QR recognition fields are null. Do not report these as automatic
instance recognition times or as a population-level accuracy estimate.
