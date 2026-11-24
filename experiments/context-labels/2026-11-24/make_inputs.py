"""Rebuild the image inputs with Pillow. Coordinates are upright source pixels."""
import csv
import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parents[1] / "codex-glasses" / "2026-11-19"
# Crop origins describe source membership only. They are never printed on probe cards.
swap = "qualitative-baseline/trial-02"
hidden = "qualitative-baseline/trial-03"
repeat = "large-text/trial-04"
empty = "large-text/trial-02"
cases = [
    (swap, "A", "closure", (248, 75, 300, 128)),
    (swap, "B", "closure", (98, 18, 185, 100)),
    (repeat, "A", "closure", (267, 93, 310, 145)),
    (hidden, "B", "occluded closure", (87, 15, 183, 108)),
    (swap, "A", "body detail", (252, 147, 297, 263)),
    (repeat, "A", "body detail", (269, 149, 309, 276)),
    (swap, "B", "body interior", (119, 152, 148, 234)),
    (repeat, "B", "body interior", (152, 155, 184, 235)),
    (swap, "A", "body interior", (253, 184, 261, 221)),
    (empty, "none", "distractor", (58, 217, 151, 277)),
    (hidden, "none", "occluder", (7, 138, 84, 272)),
    (empty, "none", "distractor", (286, 128, 401, 206)),
]
random.Random(24391).shuffle(cases)


def sheet(items, columns):
    result = Image.new("RGB", (columns * 168, ((len(items) + columns - 1) // columns) * 176), "white")
    draw = ImageDraw.Draw(result)
    for i, (label, im) in enumerate(items):
        x, y = i % columns * 168, i // columns * 176
        tile = ImageOps.contain(im, (152, 142), Image.Resampling.LANCZOS)
        result.paste(tile, (x + (168 - tile.width)//2, y + (146 - tile.height)//2))
        draw.text((x+8,y+150), label, fill="black")
    return result


if __name__ == "__main__":
    ref = Image.open(ARCHIVE / "qualitative-baseline/trial-01/source.jpg")
    sheet([("A",ref.crop((86,44,154,295))),("B",ref.crop((203,45,288,295)))],2).save(HERE/"references.png")
    items = []
    scenes = []
    with (HERE/"key.csv").open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["probe","source","source_sha256","source_identity","region","xyxy"])
        for i, (source, identity, region, box) in enumerate(cases, 1):
            path = ARCHIVE/source/"source.jpg"
            tag = f"P{i:02}"
            with Image.open(path) as source_image:
                gray = ImageOps.grayscale(source_image)
                items.append((tag, gray.crop(box)))
                # Keep the target interior intact even for narrow strips.
                scene = gray.convert("RGB")
                x1, y1, x2, y2 = box
                ImageDraw.Draw(scene).rectangle((x1-2, y1-2, x2+1, y2+1), outline="#ef3737", width=2)
                scenes.append((tag, scene))
            writer.writerow([tag,source,hashlib.sha256(path.read_bytes()).hexdigest(),identity,region," ".join(map(str,box))])
    sheet(items,4).save(HERE/"probes.png")
    # Retain native resolution in the context panels.
    for offset in range(0, len(scenes), 4):
        page = Image.new("RGB", (960, 1328), "white")
        draw = ImageDraw.Draw(page)
        for index, (tag, scene) in enumerate(scenes[offset:offset+4]):
            x, y = index % 2 * 480, index // 2 * 664
            page.paste(scene, (x, y))
            draw.text((x+8, y+644), tag, fill="black")
        page.save(HERE/f"context-{offset//4+1}.jpg", quality=90)
