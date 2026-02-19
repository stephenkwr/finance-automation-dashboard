# backend/providers/rate_limit.py
import time
import threading


class RateLimiter:
    """
    Simple spacing limiter: ensures at most N calls/min by spacing calls out.
    - This will SLEEP (wait) instead of throwing 429 errors.
    - Good for dev + single-process backend.
    """

    def __init__(self, calls_per_minute: int):
        if calls_per_minute <= 0:
            raise ValueError("calls_per_minute must be > 0")
        self.period = 60.0 / float(calls_per_minute)
        self.lock = threading.Lock()
        self.next_allowed = 0.0

    def wait(self):
        with self.lock:
            now = time.time()
            if now < self.next_allowed:
                time.sleep(self.next_allowed - now)
            self.next_allowed = time.time() + self.period


# rename to match your provider naming (Massive), but keep a backwards alias too.
massive_limiter = RateLimiter(calls_per_minute=5)
polygon_limiter = massive_limiter  # backward compatible alias
