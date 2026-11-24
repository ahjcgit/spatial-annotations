"""Build a shareable figure from the four chronologically ordered scene decisions."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from replay import DATA, HERE

rows = list(map(json.loads, (HERE / "events.jsonl").read_text().splitlines()))
fig, axes = plt.subplots(1, 4, figsize=(10.8, 4.9))
fig.subplots_adjust(left=.025, right=.975, top=.84, bottom=.23, wspace=.09)
fig.suptitle("Which bottle keeps its label?", fontsize=20, x=.025, ha="left")
for i, (ax, title) in enumerate(zip(axes, ["Enrollment", "Positions exchanged", "Body covered", "Body visible again"]), 1):
    frame = f"qualitative-baseline/trial-{i:02d}"
    row = next(r for r in rows if r["frame"] == frame and r["mode"] in ("start", "history"))
    with Image.open(DATA / frame / "source.jpg") as image:
        ax.imshow(image)
    ax.set_title(title, fontsize=12, loc="left")
    ax.axis("off")
    lines = [f"{a}   {v['action'].lower()} {v['side']}" for a, v in row["actions"].items()]
    ax.text(0, -.06, "\n".join(lines), transform=ax.transAxes, va="top", fontsize=11)
fig.text(.025,.025,"One archived sequence. Actions are offline decisions. The camera did not record motion between these photos.", fontsize=10)
fig.savefig(HERE / "sequence.png", dpi=155)
