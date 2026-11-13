"""Recorded-frame input. Ground truth is never passed to the matcher."""

import hashlib
import json
import math
from pathlib import Path
from uuid import UUID

from .gallery import read_image
from .tracker import valid_box


def contained(root, relative):
    p = (root / relative).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError("Dataset path escapes root")
    return p


class Dataset:
    def __init__(self, path):
        self.path = Path(path)
        self.root = self.path.parent
        self.data = json.loads(self.path.read_text())
        if self.data.get("version") != 1 or self.data.get("evidence_kind") not in (
            "real_recording",
            "deterministic_fixture",
        ):
            raise ValueError("Declare version and evidence_kind")
        if not self.data.get("sequences"):
            raise ValueError("No sequences")
        seen = set()
        for s in self.data["sequences"]:
            if s["id"] in seen:
                raise ValueError("Duplicate sequence ID")
            seen.add(s["id"])
            if not s.get("frames"):
                raise ValueError("Sequence has no frames")
            previous = None
            for f in s["frames"]:
                t = f["timestamp_s"]
                if (
                    not isinstance(t, (int, float))
                    or not math.isfinite(t)
                    or t < 0
                    or (previous is not None and t <= previous)
                ):
                    raise ValueError("Timestamps must increase")
                previous = t
                contained(self.root, f["image"])
                for gt in f.get("ground_truth") or []:
                    if gt["object_id"] is not None:
                        UUID(gt["object_id"])
                    if not gt.get("instance_id"):
                        raise ValueError("Ground truth needs physical instance_id")

    def fingerprint(self):
        """Hash labels, configuration, and actual image bytes, not only filenames."""
        digest = hashlib.sha256(self.path.read_bytes())
        names = sorted(
            {f["image"] for s in self.data["sequences"] for f in s["frames"]}
        )
        for name in names:
            digest.update(name.encode())
            digest.update(
                hashlib.sha256(contained(self.root, name).read_bytes()).digest()
            )
        return digest.hexdigest()

    def image(self, frame):
        return read_image(contained(self.root, frame["image"]))

    def boxes(self, frame, image):
        return [
            list(valid_box(d["bbox"], image.size))
            for d in frame.get("detections", [])
            if d.get("label", "laptop") == "laptop"
        ]

    def validate_gt(self, frame, image):
        gt = frame.get("ground_truth")
        if gt is not None:
            seen = set()
            for x in gt:
                valid_box(x["bbox"], image.size)
                if x["instance_id"] in seen:
                    raise ValueError("Repeated instance in frame")
                seen.add(x["instance_id"])
        return gt
