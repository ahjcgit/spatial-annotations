"""Event-triggered asynchronous recovery. Only this policy can accept VLM proposals."""

import asyncio
import time
from collections import Counter, deque
from datetime import datetime, timezone

from .appearance import similarity
from .tracker import Tracker, iou, valid_box
from .vlm import InvalidResponse, ProviderFailure, validate


class IdentityPipeline:
    def __init__(
        self,
        gallery,
        config,
        calibration=None,
        adapter=None,
        mode="hybrid",
        clock=time.monotonic,
    ):
        if not config.enabled:
            raise ValueError("Set IDENTITY_EXPERIMENT_ENABLED=true")
        if mode not in ("baseline", "hybrid", "vlm"):
            raise ValueError("Unsupported mode")
        if config.acceptance == "corroborated" and (
            calibration is None or calibration.data.get("vlm_min") is None
        ):
            raise ValueError(
                "Corroborated acceptance needs VLM development-set calibration"
            )
        self.gallery = gallery
        self.config = config
        self.calibration = calibration
        self.adapter = adapter
        self.mode = mode
        self.clock = clock
        self.tracker = Tracker(config)
        self.epoch = 0
        self.tasks = set()
        self.rate = deque()
        self.events = []
        self.counters = Counter()
        self.last_local_ms = 0

    def reset(self):
        self.epoch += 1
        self.tracker.reset()
        for task in self.tasks:
            task.cancel()

    async def close(self):
        self.reset()
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def settle(self):
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    def snapshot(self):
        return [t.output() for t in self.tracker.tracks.values() if t.visible]

    def valid_identity(self, tid, generation, oid, epoch):
        t = self.tracker.tracks.get(tid)
        return bool(
            epoch == self.epoch
            and t
            and t.visible
            and t.generation == generation
            and t.object_id == oid
            and t.identity_state == "matched"
        )

    def _accept(self, t, oid, source):
        if any(
            x.visible and x.track_id != t.track_id and x.object_id == oid
            for x in self.tracker.tracks.values()
        ):
            return False
        t.object_id = oid
        t.previous_object_id = oid
        t.identity_state = "matched"
        t.match_source = source
        t.match_score = t.scores.get(oid)
        t.reason = "accepted"
        t.accepted_generation = t.generation
        t.accepted_feature = t.feature.copy()
        return True

    def confirm(self, track_id, generation, object_id):
        """Explicit operator confirmation, never invoked by the VLM itself."""
        t = self.tracker.tracks.get(track_id)
        if (
            not t
            or not t.visible
            or t.generation != generation
            or object_id not in self.gallery.objects
        ):
            return False
        if not self._accept(t, object_id, "human_confirmation"):
            return False
        self.gallery.verified(object_id, t.bbox)
        return True

    async def step(self, image, bboxes, timestamp):
        started = time.perf_counter()
        obs = []
        for bbox in bboxes:
            box = valid_box(bbox, image.size)
            crop = image.crop(box)
            obs.append(
                {
                    "bbox": box,
                    "crop": crop,
                    "feature": self.gallery.encoder.encode(crop),
                }
            )
        tracks = self.tracker.update(obs, timestamp)
        overlaps = {
            t.track_id
            for t in tracks
            for u in tracks
            if u.track_id != t.track_id
            and iou(t.bbox, u.bbox) >= self.config.overlap_iou
        }
        choices = {}
        for t in tracks:
            t.scores = self.gallery.scores(t.feature)
            ranked = sorted(t.scores, key=t.scores.get, reverse=True)
            top = ranked[0] if ranked else None
            reliable = bool(self.calibration and self.calibration.accept(t.scores))
            if t.track_id in overlaps:
                t.invalidate("overlapping_tracks")
            elif self.mode == "vlm":
                t.invalidate("standalone_observation")
            elif t.object_id and (
                getattr(t, "accepted_generation", -1) != t.generation
                or similarity(t.feature, t.accepted_feature)
                < self.config.temporal_similarity
            ):
                t.invalidate("appearance_changed")
            elif (
                t.needs_gap_check and self.mode == "hybrid" and self.config.vlm_enabled
            ):
                t.invalidate("observation_gap")
            elif t.object_id and top != t.object_id:
                t.invalidate("appearance_motion_conflict")
            elif t.object_id and t.match_source == "human_confirmation":
                continue
            elif (
                t.object_id
                and t.match_source == "vlm_corroborated"
                and self.calibration.accept(t.scores, t.object_id, vlm=True)
            ):
                continue
            elif reliable and not (
                self.mode == "hybrid"
                and self.config.vlm_enabled
                and t.reason
                in (
                    "appearance_changed",
                    "appearance_motion_conflict",
                    "observation_gap",
                )
            ):
                choices[t.track_id] = top
            else:
                reason = (
                    "ambiguous_appearance"
                    if top
                    and self.calibration
                    and t.scores[top] >= self.calibration.data["appearance_min"]
                    else "unknown_appearance"
                )
                if t.reason not in (
                    "appearance_changed",
                    "appearance_motion_conflict",
                    "observation_gap",
                ):
                    t.invalidate(reason)
                else:
                    t.object_id = None
                t.identity_state = (
                    "pending_verification"
                    if t.request_active or (t.proposal and t.proposal["object_id"])
                    else (
                        "uncertain" if reason == "ambiguous_appearance" else "unknown"
                    )
                )
        # Resolve simultaneous assignments as a set; never let iteration order choose a winner.
        counts = Counter(choices.values())
        for t in tracks:
            if t.track_id in choices:
                oid = choices[t.track_id]
                occupied = any(
                    u.track_id != t.track_id
                    and u.visible
                    and u.object_id == oid
                    and u.track_id not in choices
                    for u in tracks
                )
                if counts[oid] > 1 or occupied:
                    t.invalidate("duplicate_identity")
                    for u in tracks:
                        if u.object_id == oid:
                            u.invalidate("duplicate_identity")
                else:
                    self._accept(t, oid, "appearance")
        self._schedule(tracks)
        self.last_local_ms = (time.perf_counter() - started) * 1000
        return self.snapshot()

    def _schedule(self, tracks):
        if self.mode == "baseline" or not self.config.vlm_enabled or not self.adapter:
            return
        now = self.clock()
        while self.rate and now - self.rate[0] >= 60:
            self.rate.popleft()
        if (
            len(self.tasks) >= self.config.concurrency
            or len(self.rate) >= self.config.requests_per_minute
        ):
            return
        # A successful unknown/proposal consumes the event; only failures may retry after cooldown.
        chosen = [
            t
            for t in tracks
            if t.object_id is None
            and not t.request_active
            and t.attempts < self.config.max_attempts
            and not getattr(t, "completed_event", None) == (self.epoch, t.generation)
            and now - t.last_request >= self.config.cooldown_s
        ]
        chosen = chosen[: self.config.max_tracks_per_request]
        if not chosen:
            return
        if len(self.gallery.objects) > self.config.max_objects:
            self.counters["gallery_limit"] += 1
            for t in chosen:
                t.completed_event = (self.epoch, t.generation)
            return
        request = {
            "epoch": self.epoch,
            "request_id": self.counters["requests"] + 1,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "created_at": now,
            "references": {
                oid: ims[: self.config.max_references]
                for oid, ims in self.gallery.images.items()
            },
            "observations": [],
        }
        for t in chosen:
            t.request_active = True
            t.attempts += 1
            t.last_request = now
            t.identity_state = "pending_verification"
            request["observations"].append(
                {
                    "track_id": t.track_id,
                    "generation": t.generation,
                    "timestamp": t.timestamp,
                    "reason": t.reason,
                    "previous_object_id": t.previous_object_id,
                    "crop": t.crop.copy(),
                    "feature": t.feature.copy(),
                }
            )
        self.rate.append(now)
        self.counters["requests"] += 1
        task = asyncio.create_task(self._recover(request))
        self.tasks.add(task)

        def finished(done):
            self.tasks.discard(done)
            # A task cancelled before its first turn never enters _recover/finally.
            if done.cancelled():
                self.counters["cancelled_before_dispatch"] += 1
                self._record_event(
                    request, "discarded", "cancelled_before_dispatch", None, 0, {}, None
                )

        task.add_done_callback(finished)

    def _current(self, request):
        if (
            request["epoch"] != self.epoch
            or self.clock() - request["created_at"] > self.config.response_ttl_s
        ):
            return False
        for o in request["observations"]:
            t = self.tracker.tracks.get(o["track_id"])
            if (
                not t
                or not t.visible
                or t.object_id is not None
                or t.generation != o["generation"]
                or t.timestamp - o["timestamp"] > self.config.response_ttl_s
            ):
                return False
            if similarity(t.feature, o["feature"]) < self.config.temporal_similarity:
                return False
        return True

    async def _recover(self, request):
        started = self.clock()
        category = None
        usage = {}
        outcome = "failed"
        accepted = 0
        try:
            result = await asyncio.wait_for(
                self.adapter.match(request), timeout=self.config.timeout_s
            )
            usage = result.get("usage", {})
            if not isinstance(usage, dict):
                usage = {}
            matches = validate(result["response"], request)
            if not self._current(request):
                category = "stale_result"
                outcome = "discarded"
                return
            submitted = {o["track_id"] for o in request["observations"]}
            occupied = {
                t.object_id
                for t in self.tracker.tracks.values()
                if t.visible and t.object_id and t.track_id not in submitted
            }
            if any(m["object_id"] in occupied for m in matches if m["object_id"]):
                raise InvalidResponse("Object already on another track")
            for m in matches:
                t = self.tracker.tracks[m["track_id"]]
                t.completed_event = (self.epoch, t.generation)
                t.proposal = m
                t.object_id = None
                t.match_source = None
                t.match_score = None
                if m["object_id"] is None:
                    t.identity_state = "unknown"
                else:
                    t.identity_state = "pending_verification"
                    if (
                        self.config.acceptance == "corroborated"
                        and self.calibration.accept(t.scores, m["object_id"], vlm=True)
                        and t.reason != "overlapping_tracks"
                    ):
                        accepted += int(
                            self._accept(t, m["object_id"], "vlm_corroborated")
                        )
            outcome = "validated"
            self.counters["accepted"] += accepted
        except asyncio.CancelledError:
            category = "cancelled"
            outcome = "discarded"
        except (asyncio.TimeoutError, TimeoutError):
            category = "timeout"
        except InvalidResponse:
            category = "invalid_response"
        except ProviderFailure:
            category = "provider_error"
        except Exception:
            category = "adapter_error"  # Never log provider payload, explanations or credentials.
        finally:
            if category:
                self.counters[category] += 1
            for o in request["observations"]:
                t = self.tracker.tracks.get(o["track_id"])
                if (
                    t
                    and request["epoch"] == self.epoch
                    and t.generation == o["generation"]
                ):
                    t.request_active = False
                    if outcome != "validated" and not t.object_id:
                        t.identity_state = "unknown"
            safe_usage = {
                k: v
                for k, v in usage.items()
                if k in ("prompt_tokens", "completion_tokens", "total_tokens")
                and type(v) is int
                and v >= 0
            }
            cost = None
            if (
                all(k in safe_usage for k in ("prompt_tokens", "completion_tokens"))
                and self.config.input_usd_per_million is not None
                and self.config.output_usd_per_million is not None
            ):
                cost = (
                    safe_usage["prompt_tokens"] * self.config.input_usd_per_million
                    + safe_usage["completion_tokens"]
                    * self.config.output_usd_per_million
                ) / 1e6
            self._record_event(
                request,
                outcome,
                category,
                (self.clock() - started) * 1000,
                accepted,
                safe_usage,
                cost,
            )

    def _record_event(
        self, request, outcome, category, latency_ms, accepted, usage, cost
    ):
        self.events.append(
            {
                "event": "vlm_request",
                "request_id": request["request_id"],
                "submitted_at": request["submitted_at"],
                "model": self.config.model,
                "observations": [
                    {k: o[k] for k in ("track_id", "generation", "timestamp", "reason")}
                    for o in request["observations"]
                ],
                "outcome": outcome,
                "failure_category": category,
                "latency_ms": latency_ms,
                "track_count": len(request["observations"]),
                "accepted": accepted,
                "usage": usage,
                "estimated_cost_usd": cost,
            }
        )
