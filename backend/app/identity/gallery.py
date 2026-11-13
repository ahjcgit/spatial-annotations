"""Local reference manifest linked to existing backend PhysicalObject UUIDs."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageOps

from .appearance import similarity


def read_image(path):
    with Image.open(path) as im:
        if im.width * im.height > 16_000_000:
            raise ValueError("Reference/frame exceeds 16 MP")
        return ImageOps.exif_transpose(im).convert("RGB")


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(value, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


class Gallery:
    def __init__(self, path, encoder):
        self.path = Path(path)
        self.encoder = encoder
        self.data = json.loads(self.path.read_text())
        self.objects = {}
        self.images = {}
        self.features = {}
        if self.data.get("version") != 1:
            raise ValueError("Unsupported gallery version")
        for obj in self.data["objects"]:
            oid = str(UUID(obj["object_id"]))
            if oid in self.objects or not obj.get("references"):
                raise ValueError("Duplicate object or empty gallery")
            self.objects[oid] = obj
            self.images[oid] = []
            self.features[oid] = []
            for ref in obj["references"]:
                p = (self.path.parent / ref["path"]).resolve()
                if not p.is_relative_to(self.path.parent.resolve()):
                    raise ValueError("Reference outside gallery directory")
                if hashlib.sha256(p.read_bytes()).hexdigest() != ref["sha256"]:
                    raise ValueError("Reference checksum changed")
                im = read_image(p)
                self.images[oid].append(im)
                self.features[oid].append(encoder.encode(im))

    def scores(self, feature):
        return {
            oid: max(similarity(feature, r) for r in refs)
            for oid, refs in self.features.items()
        }

    def verified(self, oid, bbox):
        obj = self.objects[oid]
        obj["last_verified_identity_at"] = datetime.now(timezone.utc).isoformat()
        obj["last_known_position"] = {
            "bbox": list(bbox),
            "coordinate_system": "current image pixels, not a world position",
        }
        save_json(self.path, self.data)


def register(path, object_record, images):
    """Caller obtains object_record using the existing authenticated backend API."""
    path = Path(path)
    oid = str(UUID(object_record["id"]))
    data = (
        json.loads(path.read_text()) if path.exists() else {"version": 1, "objects": []}
    )
    obj = next((o for o in data["objects"] if o["object_id"] == oid), None)
    if obj is None:
        obj = {
            "object_id": oid,
            "name": object_record.get("name") or oid,
            "references": [],
            "last_known_position": None,
            "last_verified_identity_at": None,
        }
        data["objects"].append(obj)
    folder = path.parent / "references" / oid
    folder.mkdir(parents=True, exist_ok=True)
    for source in images:
        im = read_image(source)
        im.thumbnail((1024, 1024))
        temp = folder / "import.png"
        im.save(temp)
        digest = hashlib.sha256(temp.read_bytes()).hexdigest()
        target = folder / (digest + ".png")
        temp.replace(target)
        if not any(r["sha256"] == digest for r in obj["references"]):
            obj["references"].append(
                {"path": str(target.relative_to(path.parent)), "sha256": digest}
            )
    save_json(path, data)
    return obj
