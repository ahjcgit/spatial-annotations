"""In-memory sliding-window limits. State is per process; run a single backend worker."""
import math
import threading
import time
from collections import OrderedDict, deque


class SlidingWindow:
    def __init__(self, limit, window_s, max_keys=10_000, clock=time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self.max_keys = max_keys
        self.clock = clock
        self.hits = OrderedDict()
        self.lock = threading.Lock()

    def _recent(self, key, now):
        hits = self.hits.get(key)
        if hits is None:
            return None
        while hits and now - hits[0] >= self.window_s:
            hits.popleft()
        if not hits:
            del self.hits[key]
            return None
        return hits

    def _wait(self, hits, now):
        if hits is None or len(hits) < self.limit:
            return 0
        return max(1, math.ceil(self.window_s - (now - hits[0])))

    def _record(self, key, hits, now):
        if hits is None:
            hits = self.hits[key] = deque()
        hits.append(now)
        self.hits.move_to_end(key)
        while len(self.hits) > self.max_keys:
            self.hits.popitem(last=False)

    def retry_after(self, key):
        """Seconds until `key` is allowed again, or 0. Does not record a hit."""
        with self.lock:
            now = self.clock()
            return self._wait(self._recent(key, now), now)

    def acquire(self, key):
        """Atomically check and record a hit. Returns 0 if allowed, else seconds to wait."""
        with self.lock:
            now = self.clock()
            hits = self._recent(key, now)
            wait = self._wait(hits, now)
            if not wait:
                self._record(key, hits, now)
            return wait

    def hit(self, key):
        with self.lock:
            now = self.clock()
            self._record(key, self._recent(key, now), now)

    def reset(self, key):
        with self.lock:
            self.hits.pop(key, None)


class LoginLimiter:
    """Per-IP attempt limit plus per-(IP, username) failure limit.

    Failures are keyed by IP and username together so a remote attacker cannot lock a
    victim out of their account from other networks.
    """

    def __init__(self, attempts_per_ip, failures_per_account, clock=time.monotonic):
        self.ip = SlidingWindow(attempts_per_ip, 60, clock=clock)
        self.failures = SlidingWindow(failures_per_account, 15 * 60, clock=clock)

    def check(self, ip, username):
        return self.failures.retry_after((ip, username)) or self.ip.acquire(ip)

    def failed(self, ip, username):
        self.failures.hit((ip, username))

    def succeeded(self, ip, username):
        self.failures.reset((ip, username))
