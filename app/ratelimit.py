"""Anfragebegrenzung je Mandant (Token Bucket), damit ein Mandant nicht alle anderen ausbremst.

Der Zähler liegt im Speicher der Instanz. Bei zwei Instanzen verdoppelt sich das
tatsächliche Limit; warum das hier in Ordnung ist, steht in docs/adr/0004.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable


class Ratelimit:
    def __init__(
        self, pro_minute: float, burst: int, uhr: Callable[[], float] = time.monotonic
    ) -> None:
        self.rate = pro_minute / 60  # neue Tokens pro Sekunde
        self.burst = burst
        self.uhr = uhr
        self._eimer: dict[str, tuple[float, float]] = {}  # mandant -> (tokens, zeitpunkt)
        self._lock = threading.Lock()

    def erlauben(self, mandant: str) -> tuple[bool, int]:
        """(erlaubt, Sekunden bis zum nächsten freien Token)."""
        with self._lock:
            jetzt = self.uhr()
            tokens, zuletzt = self._eimer.get(mandant, (float(self.burst), jetzt))
            tokens = min(self.burst, tokens + (jetzt - zuletzt) * self.rate)
            if tokens >= 1:
                self._eimer[mandant] = (tokens - 1, jetzt)
                return True, 0
            self._eimer[mandant] = (tokens, jetzt)
            return False, max(1, math.ceil((1 - tokens) / self.rate))
