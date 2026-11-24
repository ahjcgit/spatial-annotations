"""Warm CPU baseline. One update decodes one archived JPEG and ranks two manual boxes."""
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clear_swap import descriptors, similarity


def run(trial, gallery):
    labels = []
    for descriptor in descriptors(trial):
        scores = {name: similarity(descriptor, ref) for name, ref in gallery.items()}
        labels.append(max(scores, key=scores.get))
    return labels


if __name__ == "__main__":
    gallery = dict(zip(("A", "B"), descriptors("trial-01")))
    trials = ("trial-02", "trial-04")
    for trial in trials:
        run(trial, gallery)
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["repeat", "frame", "wall_ms", "cpu_ms", "rss_mib", "process_vm_hwm_mib", "left", "right"])
    for i in range(100):
        trial = trials[i % 2]
        cpu = time.process_time_ns()
        start = time.monotonic_ns()
        left, right = run(trial, gallery)
        elapsed = time.monotonic_ns() - start
        used = time.process_time_ns() - cpu
        with open("/proc/self/status") as status:
            mem = {k: int(v.split()[0]) / 1024 for k, v in
                   (s.split(":", 1) for s in status if s.startswith(("VmRSS:", "VmHWM:")))}
        writer.writerow([i+1, trial, elapsed / 1e6, used / 1e6, mem["VmRSS"], mem["VmHWM"], left, right])
