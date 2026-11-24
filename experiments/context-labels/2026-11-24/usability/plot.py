"""Render the paired turnaround times. Input is the recorded decision CSV."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from measure import HERE, PILOT, rows

key = {r["probe"]: r for r in rows(PILOT / "key.csv")}
reviews = {(r["probe"], r["mode"]): r for r in rows(HERE / "reviews.csv")}
fig, ax = plt.subplots(figsize=(8, 5.6), layout="constrained")
for index, probe in enumerate(key):
    times = [float(reviews[probe, mode]["total_ms"])/1000 for mode in ("crop", "scene")]
    ax.plot(times, [index, index], color="#bcc5c9", zorder=1)
    for time, shape, color, label in zip(times, ("o", "D"), ("#166188", "#a64016"), ("Crop", "Scene")):
        ax.scatter(time, index, marker=shape, color=color, s=43, label=label if index == 0 else None)
ax.set_yticks(range(len(key)), [f"{probe}   {r['region']}" for probe, r in key.items()])
ax.invert_yaxis()
ax.set_xlim(left=0)
ax.set_xlabel("Seconds from local image preparation to decision receipt")
ax.set_title("Turnaround for the same target with and without its surroundings", loc="left")
ax.legend(loc="lower left", frameon=False)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.tick_params(axis="y", length=0)
ax.grid(axis="x", color="#e3e6e7")
ax.set_axisbelow(True)
fig.savefig(HERE / "paired-latency.png", dpi=160)
