"""Mouth flapping and blinking, as a function of time. No Qt here so it can be tested exactly."""
from __future__ import annotations

import random


class Animator:
    FLAP_MIN, FLAP_MAX = 0.070, 0.120      # seconds between mouth open/close changes while speaking

    def __init__(self, rng: random.Random, blink_min: float, blink_max: float, blink_ms: int):
        self._rng, self._bmin, self._bmax, self._bsec = rng, blink_min, blink_max, blink_ms / 1000.0
        self._mouth = False
        self._toggle_at: float | None = None
        self._next_blink: float | None = None
        self._blink_until = 0.0

    def tick(self, now: float, speaking: bool) -> tuple[bool, bool]:
        """Returns (mouth_open, blinking)."""
        if speaking:
            if self._toggle_at is None:
                self._mouth, self._toggle_at = True, now + self._rng.uniform(self.FLAP_MIN, self.FLAP_MAX)
            elif now >= self._toggle_at:
                self._mouth = not self._mouth
                self._toggle_at = now + self._rng.uniform(self.FLAP_MIN, self.FLAP_MAX)
        else:
            self._mouth, self._toggle_at = False, None
        if self._next_blink is None:
            self._next_blink = now + self._rng.uniform(self._bmin, self._bmax)
        if now >= self._next_blink and now >= self._blink_until:
            self._blink_until = now + self._bsec
            self._next_blink = now + self._rng.uniform(self._bmin, self._bmax)   # gap counted start to start
        return self._mouth, now < self._blink_until
