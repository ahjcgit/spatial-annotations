# Real-camera VLM snapshot test

`scripts/vlm_camera_probe.py` sends one photograph to a real vision-language model
and saves proposed boxes, descriptive labels, and brief visual evidence. This is a
separate smoke test from the H0–H4 synthetic identity suite. It does not assign
registered object UUIDs, retrieve saved notes, or display VLM output on the glasses.
An explanation is a model claim to review, not proof that its label is correct.

## Codex review selected for this session

To use the Codex assistant's vision, capture a fresh frame without an inference API:

```bash
.venv/bin/python scripts/vlm_camera_probe.py \
  --dashboard http://127.0.0.1:8014 --pause-camera --capture-only \
  --out artifacts/vlm-probes/codex-next-frame
```

Select **Start live** in the dashboard before capturing. Have the Codex assistant
inspect the resulting `source.png`, propose visible labels and approximate boxes,
and save its brief evidence separately. The first such review is in
`artifacts/vlm-probes/session-2026-11-19/codex-frame-01/`: `source.jpg`,
`capture.json`, `codex-result.json`, and `codex-labels.png`.
Its provenance says `codex_conversation_vision`; it is not an API benchmark,
independent ground truth, automatic identity assignment, or a live glasses overlay.
No nested agents are launched. Request latency is unmeasured for conversation review.

The local Qwen setup below was also tried before Codex was selected, and its server
was then stopped. The runtime and downloaded weights remain available for optional
comparisons. The first Qwen response took 44.35 seconds and contained false cup and
laptop proposals; both its original output and visual review were retained.

## Local setup used on this computer

The runtime and weights are outside the repository at
`/home/ahjc/Coding/.toolchain/vlm/`. `provenance.json` records the runtime release,
pinned model revision, download URLs, sizes, and verified SHA-256 checksums.
The initial setup uses llama.cpp b12554 and Qwen3-VL-2B-Instruct Q4_K_M with its
F16 vision projector. Images remain on this computer when using the local endpoint.

Runtime/model references:
[llama.cpp multimodal support](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md),
[official Qwen GGUF repository](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF).

If port 8086 is free, start the local server:

```bash
VLM_DIR=/home/ahjc/Coding/.toolchain/vlm
"$VLM_DIR/b12554/llama-b12554/llama-server" \
  -m "$VLM_DIR/Qwen3VL-2B-Instruct-Q4_K_M.gguf" \
  --mmproj "$VLM_DIR/mmproj-Qwen3VL-2B-Instruct-F16.gguf" \
  --alias qwen3-vl-2b --host 127.0.0.1 --port 8086 \
  -c 4096 -t 4 -tb 4 -np 1 -ngl 0 --no-mmproj-offload \
  --image-min-tokens 1024 --image-max-tokens 1024
```

Wait for `curl -fsS http://127.0.0.1:8086/health` to return `{"status":"ok"}`.
The image-token settings follow this runtime's Qwen grounding warning. They do not
establish localization accuracy. CPU inference can take substantially longer than
the live NanoDet camera demo.

## Run a snapshot

Start the existing model backend and presentation dashboard as described in the
README. Open http://127.0.0.1:8014, select **Start live**, and position the glasses.
Then run from the application repository, using a new output directory each time:

```bash
.venv/bin/python scripts/vlm_camera_probe.py \
  --dashboard http://127.0.0.1:8014 --pause-camera --timeout 240 \
  --out artifacts/vlm-probes/my-first-frame
```

The script waits for an advancing frame ID from the same run, captures the image,
then pauses the camera to reduce competing CPU work. Select **Start live** again
before another capture. The presentation app's old bottle labels remain separate
from this probe's VLM proposals. The VLM receives the photograph and prompt only;
NanoDet predictions and saved notes are not supplied.

Alternatively, test an existing photograph:

```bash
.venv/bin/python scripts/vlm_camera_probe.py --image /path/to/photo.jpg \
  --timeout 240 --out artifacts/vlm-probes/my-photo
```

`--endpoint` and `--model` select another compatible vision server. If it requires
a key, set `VLM_PROBE_API_KEY` privately in the shell; keys are not written to the
artifacts. A hosted endpoint receives the selected image. No API is configured or
called implicitly.

## Inspect results

- `source.png`: decoded source photograph, before resizing.
- `input.jpg`: exact resized JPEG sent to the VLM.
- `response.json`: real provider response and any reported usage/timing.
- `result.json`: validated proposals, input hash, camera metadata when captured
  directly, prompt, request wall time, and success/failure status.
- `proposals.png`: boxes and labels drawn over the input image; uncertain proposals
  are yellow. Coordinate validation checks bounds/order, not visual correctness.

Retain failed attempts. A retry with `--image` is recorded as an image-file run;
the original capture's `result.json` retains its physical camera provenance.
The request timer includes server queueing, image processing, prompt processing,
and generation, but excludes camera acquisition and final glasses display.

Before any accuracy claim, review boxes/labels against the image. Useful next
snapshots include an isolated object, several objects, an empty scene, an oblique
view, and an occluded object. Instance-specific saved notes need separately
registered reference images, identity confirmation, and permission checks.
