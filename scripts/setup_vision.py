#!/usr/bin/env python3
"""Download the Apache-2.0 OpenCV Zoo model from its pinned official revision."""
import hashlib
from pathlib import Path
from urllib.request import urlopen
REVISION = '48b10fa505aeb51fbd127fc60a5c660040e823b7'
SHA256 = '4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186'
path = Path('artifacts/models/nanodet.onnx')
path.parent.mkdir(parents=True, exist_ok=True)
if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
    # Official OpenCV mirror; checksum pins exactly the Zoo revision above.
    url = 'https://huggingface.co/opencv/object_detection_nanodet/resolve/main/object_detection_nanodet_2022nov.onnx'
    with urlopen(url, timeout=60) as response:
        content = response.read(4_000_000)
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise SystemExit('Model checksum mismatch; refusing to install.')
    path.write_bytes(content)
print(f'Verified {path.resolve()} SHA256 {SHA256}')
