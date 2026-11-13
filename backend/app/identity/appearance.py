"""Replaceable descriptors. No downloaded weights or learned identity thresholds by default."""

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def normalized(values):
    v = np.asarray(values, dtype=np.float32).reshape(-1)
    if not v.size or not np.isfinite(v).all() or np.linalg.norm(v) < 1e-8:
        raise ValueError("Invalid descriptor")
    return v / np.linalg.norm(v)


def similarity(a, b):
    if len(a) != len(b):
        raise ValueError("Descriptor dimensions differ")
    return float(np.clip(np.dot(a, b), -1, 1))


class ColorGrid:
    """Small spatial RGB descriptor; lighting/viewpoint-sensitive, not a learned embedding."""

    name = "color-grid-v1"

    def encode(self, image):
        a = np.asarray(image.convert("RGB").resize((12, 12)), dtype=np.float32) / 255
        return normalized(
            np.concatenate(
                [
                    a.reshape(-1),
                    np.histogram(a, bins=16, range=(0, 1), density=True)[0] / 16,
                ]
            )
        )

    def metadata(self):
        return {"name": self.name, "learned": False, "dimensions": 448}


class DinoLocal:
    """Optional DINOv2-Small from a user-provided local checkout + checkpoint. CPU only."""

    def __init__(self, repo, weights):
        import torch

        self.torch = torch
        path = Path(weights)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.name = "dinov2-vits14:" + digest
        self.model = torch.hub.load(
            str(Path(repo).resolve()), "dinov2_vits14", source="local", pretrained=False
        )
        state = torch.load(path, map_location="cpu", weights_only=True)
        self.model.load_state_dict(state, strict=True)
        self.model.eval()

    def encode(self, image):
        # Fixed RGB resize and ImageNet normalization, recorded as part of this adapter version.
        a = (
            np.asarray(
                image.convert("RGB").resize((224, 224), Image.Resampling.BICUBIC),
                dtype=np.float32,
            )
            / 255
        )
        a = (a - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
        tensor = self.torch.from_numpy(a.transpose(2, 0, 1).copy()).float().unsqueeze(0)
        with self.torch.inference_mode():
            return normalized(self.model(tensor).squeeze().numpy())

    def metadata(self):
        return {
            "name": self.name,
            "learned": True,
            "input": "RGB stretch 224; ImageNet mean/std",
            "runtime": "torch CPU",
        }


class Calibration:
    def __init__(self, data, model):
        self.data = data
        if data["embedding_model"] != model:
            raise ValueError("Calibration descriptor mismatch")
        if not data.get("development_set"):
            raise ValueError("Calibration must identify its development set")
        for key in ("appearance_min", "appearance_margin"):
            if (
                not isinstance(data.get(key), (int, float))
                or not np.isfinite(data[key])
                or not 0 <= data[key] <= 1
            ):
                raise ValueError("Invalid calibration: " + key)
        if data.get("vlm_min") is not None:
            if not data.get("vlm_development_set"):
                raise ValueError(
                    "VLM acceptance requires separate development evidence"
                )
            for key in ("vlm_min", "vlm_margin"):
                if (
                    not isinstance(data.get(key), (int, float))
                    or not np.isfinite(data[key])
                    or not 0 <= data[key] <= 1
                ):
                    raise ValueError("Invalid VLM calibration")

    @classmethod
    def load(cls, path, model):
        return cls(json.loads(Path(path).read_text()), model)

    def accept(self, scores, object_id=None, vlm=False):
        if not scores:
            return False
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        object_id = object_id or ranked[0][0]
        floor = self.data.get("vlm_min") if vlm else self.data["appearance_min"]
        margin = self.data.get("vlm_margin") if vlm else self.data["appearance_margin"]
        if floor is None or margin is None or object_id not in scores:
            return False
        other = max([v for k, v in scores.items() if k != object_id], default=0.0)
        return scores[object_id] >= floor and scores[object_id] - other >= margin
