"""Compare fixed slots and the existing descriptor on four full-object grayscale crops."""
import csv
import sys
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "backend"))
from app.identity.appearance import ColorGrid, similarity

SOURCE = HERE.parents[1] / "codex-glasses/2026-11-19/qualitative-baseline"
BOXES = {
    "trial-01": [(86, 44, 154, 295), (203, 45, 288, 295)],  # enrolled A left, B right
    "trial-02": [(96, 15, 185, 295), (244, 72, 303, 295)],
    "trial-04": [(92, 15, 179, 295), (241, 74, 302, 296)],
}


def descriptors(trial):
    with Image.open(SOURCE / trial / "source.jpg") as image:
        gray = ImageOps.grayscale(image)
        return [ColorGrid().encode(gray.crop(box)) for box in BOXES[trial]]


if __name__ == "__main__":
    gallery = dict(zip(("A", "B"), descriptors("trial-01")))
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["frame", "side", "box_xyxy", "truth", "fixed_slot", "nearest_reference", "cos_A", "cos_B"])
    for trial in ("trial-02", "trial-04"):
        for side, truth, slot, box, descriptor in zip(
            ("left", "right"), ("B", "A"), ("A", "B"), BOXES[trial], descriptors(trial)
        ):
            scores = {name: similarity(descriptor, ref) for name, ref in gallery.items()}
            best = max(scores, key=scores.get)
            writer.writerow([trial, side, " ".join(map(str, box)), truth, slot, best,
                             f"{scores['A']:.5f}", f"{scores['B']:.5f}"])
