"""Small greedy motion/appearance association baseline, not a full MOT tracker."""

import math
from dataclasses import dataclass, field

import numpy as np

from .appearance import similarity


def iou(a, b):
    area = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - area
    return area / union if union > 0 else 0.0


def valid_box(box, size):
    if len(box) != 4 or not all(
        isinstance(x, (float, int)) and math.isfinite(x) for x in box
    ):
        raise ValueError("Invalid pixel bbox")
    x1, y1, x2, y2 = box
    w, h = size
    if not 0 <= x1 < x2 <= w or not 0 <= y1 < y2 <= h:
        raise ValueError("Bbox outside frame")
    return tuple(float(x) for x in box)


@dataclass
class Track:
    track_id: int
    bbox: tuple
    feature: object
    crop: object
    timestamp: float
    generation: int = 0
    visible: bool = True
    velocity: object = field(default_factory=lambda: np.zeros(4))
    object_id: str | None = None
    previous_object_id: str | None = None
    identity_state: str = "unknown"
    match_source: str | None = None
    match_score: float | None = None
    reason: str = "new_track"
    scores: dict = field(default_factory=dict)
    proposal: dict | None = None
    event: int = 0
    attempts: int = 0
    last_request: float = float("-inf")
    request_active: bool = False
    event_feature: object = None
    needs_gap_check: bool = False

    def invalidate(self, reason):
        if self.object_id:
            self.previous_object_id = self.object_id
        self.object_id = None
        self.identity_state = "uncertain"
        self.match_source = None
        self.match_score = None
        if self.reason != reason or self.event_feature is None:
            self.proposal = None
            self.generation += 1
            self.event += 1
            self.attempts = 0
            self.request_active = False
            self.event_feature = self.feature.copy()
        self.reason = reason

    def output(self):
        return {
            "track_id": self.track_id,
            "generation": self.generation,
            "bbox": list(self.bbox),
            "object_id": self.object_id,
            "identity_state": self.identity_state,
            "match_source": self.match_source,
            "match_score": self.match_score,
            "reason": self.reason,
            "vlm_proposal": dict(self.proposal) if self.proposal else None,
        }


class Tracker:
    def __init__(self, config):
        self.config = config
        self.tracks = {}
        self.next_id = 1
        self.last_timestamp = None

    def reset(self):
        self.tracks.clear()
        self.last_timestamp = None  # IDs never reused within a runner

    def update(self, observations, timestamp):
        if not math.isfinite(timestamp) or (
            self.last_timestamp is not None and timestamp <= self.last_timestamp
        ):
            raise ValueError("Frame timestamps must increase within a session")
        self.last_timestamp = timestamp
        for tid, t in list(self.tracks.items()):
            if timestamp - t.timestamp > self.config.track_ttl_s:
                del self.tracks[tid]
        edges = []
        for tid, t in self.tracks.items():
            dt = timestamp - t.timestamp
            pred = np.array(t.bbox) + t.velocity * min(dt, 0.5)
            for j, o in enumerate(observations):
                overlap = iou(pred, o["bbox"])
                appearance = similarity(t.feature, o["feature"])
                center = lambda b: np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])
                near = np.linalg.norm(center(pred) - center(o["bbox"])) < 2 * max(
                    t.bbox[2] - t.bbox[0], t.bbox[3] - t.bbox[1]
                )
                if overlap > 0.05 or (near and appearance > 0.9):
                    edges.append((0.6 * overlap + 0.4 * appearance, tid, j))
        used_t = set()
        used_o = set()
        assigned = {}
        for _, tid, j in sorted(edges, reverse=True):
            if tid not in used_t and j not in used_o:
                assigned[j] = tid
                used_t.add(tid)
                used_o.add(j)
        for tid, t in self.tracks.items():
            if tid not in used_t and t.visible:
                t.visible = False
                t.generation += 1
                t.proposal = None
                t.request_active = False
                if t.object_id:
                    t.accepted_generation = t.generation
        visible = []
        for j, o in enumerate(observations):
            if j in assigned:
                t = self.tracks[assigned[j]]
                gap = timestamp - t.timestamp
                t.needs_gap_check = gap > self.config.gap_s
                t.velocity = (np.array(o["bbox"]) - np.array(t.bbox)) / max(gap, 1e-6)
                # Material appearance change invalidates in-flight reasoning even on the same track.
                if (
                    similarity(t.feature, o["feature"])
                    < self.config.temporal_similarity
                ):
                    t.generation += 1
                    t.event += 1
                    t.attempts = 0
                    t.request_active = False
                    t.proposal = None
                    t.event_feature = o["feature"].copy()
                t.bbox = o["bbox"]
                t.feature = o["feature"]
                t.crop = o["crop"]
                t.timestamp = timestamp
                t.visible = True
            else:
                t = Track(self.next_id, o["bbox"], o["feature"], o["crop"], timestamp)
                self.next_id += 1
                self.tracks[t.track_id] = t
            visible.append(t)
        return visible
