import time
from typing import Dict, Tuple
from fastapi import HTTPException, status

class LoginRateLimiter:
    """
    In-memory sliding-window rate limiter for authentication endpoints.
    Protects against brute-force login attacks.
    """
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        # key: (failed_attempts, first_attempt_timestamp, lockout_until)
        self._records: Dict[str, Tuple[int, float, float]] = {}

    def _cleanup(self, now: float):
        keys_to_delete = [
            k for k, (count, start_t, lockout) in self._records.items()
            if now > lockout and (now - start_t) > self.window_seconds * 2
        ]
        for k in keys_to_delete:
            del self._records[k]

    def check_rate_limit(self, identifier: str):
        now = time.time()
        self._cleanup(now)

        if identifier in self._records:
            count, start_t, lockout_until = self._records[identifier]
            if now < lockout_until:
                retry_after = int(lockout_until - now) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many failed login attempts. Please try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)}
                )
            if (now - start_t) > self.window_seconds:
                # Window expired, reset
                self._records[identifier] = (0, now, 0.0)

    def record_failure(self, identifier: str):
        now = time.time()
        if identifier not in self._records:
            self._records[identifier] = (1, now, 0.0)
            return

        count, start_t, lockout_until = self._records[identifier]
        if (now - start_t) > self.window_seconds:
            self._records[identifier] = (1, now, 0.0)
            return

        new_count = count + 1
        if new_count >= self.max_attempts:
            lockout = now + self.window_seconds
            self._records[identifier] = (new_count, start_t, lockout)
        else:
            self._records[identifier] = (new_count, start_t, 0.0)

    def record_success(self, identifier: str):
        if identifier in self._records:
            del self._records[identifier]

login_rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=300)
