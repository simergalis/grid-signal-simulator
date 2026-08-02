"""
Session-transport instrument plane (Simulator Spec 12.10).

Measures WS tick latency and API round-trip from wall-clock observations only.
No imports from any simulation module are permitted here (structural guard
TC-85b).  Session transport latency is always a live wall-clock measurement;
it must never be derivable from, or correlated with, the simulation clock.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

# Observation window: reject timestamps older than this.
# A browser tab backgrounded for > 30 s will simply not produce valid
# observations — that is correct behaviour (stale latency is not useful).
_MAX_AGE_NS: int = 30 * 1_000_000_000  # 30 seconds in nanoseconds

# Prune the consumed-nonce set when it exceeds this size.
# Keeps memory O(ticks per window) regardless of playback speed.
_NONCE_PRUNE_THRESHOLD: int = 500


@dataclass
class InstrumentPlane:
    _ws_samples: deque = field(default_factory=lambda: deque(maxlen=1000))
    _api_samples: deque = field(default_factory=lambda: deque(maxlen=1000))
    # Replay-protection: nonces that have already been observed.
    # Nonces older than _MAX_AGE_NS are pruned on each accepted observation
    # because they cannot be replayed anyway (the age check rejects them first).
    _consumed_nonces: set = field(default_factory=set)

    def stamp_tick(self, payload: dict) -> dict:
        """Stamp t_emit_ns onto the outgoing tick payload (wall clock only).

        The value is serialised as a *string* so JavaScript clients can round-
        trip it without precision loss — monotonic_ns exceeds Number.MAX_SAFE_
        INTEGER after ~104 days of host uptime.
        """
        payload = dict(payload)
        payload["t_emit_ns"] = str(time.monotonic_ns())
        return payload

    def observe_tick(self, t_emit_ns: "int | str") -> bool:
        """Record a WS tick latency sample from the emit timestamp.

        Validates the observation before recording:
          * Future timestamps are rejected (t_emit_ns > now).
          * Stale timestamps older than _MAX_AGE_NS are rejected.
          * Replayed nonces (same t_emit_ns seen before) are rejected.

        Returns True when the observation was recorded, False when rejected.
        Callers should treat False as a signal that the round-trip measurement
        was not valid — do NOT log it as an error; packet reordering and brief
        backgrounding are normal.
        """
        t = int(t_emit_ns)
        now_ns = time.monotonic_ns()
        cutoff_ns = now_ns - _MAX_AGE_NS

        # Reject future timestamps (client clock skew or fabrication).
        if t > now_ns:
            return False
        # Reject stale timestamps (tab was backgrounded too long, or old nonce).
        if t < cutoff_ns:
            return False
        # Replay protection: each nonce may be consumed at most once.
        if t in self._consumed_nonces:
            return False

        # Accept: consume and record.
        self._consumed_nonces.add(t)
        # Prune expired nonces to bound memory — expired nonces can never be
        # replayed (the age check would reject them), so removal is safe.
        if len(self._consumed_nonces) > _NONCE_PRUNE_THRESHOLD:
            self._consumed_nonces = {n for n in self._consumed_nonces if n >= cutoff_ns}

        elapsed_ms = (now_ns - t) / 1_000_000.0
        self._ws_samples.append(elapsed_ms)
        return True

    def observe_api(self, ms: float) -> None:
        """Record an API round-trip measurement in milliseconds."""
        self._api_samples.append(ms)

    def modal_view(self) -> dict:
        """Return the fields rendered in the SESSION TRANSPORT section."""
        ws = list(self._ws_samples)
        api = list(self._api_samples)

        ws_p50 = _percentile(ws, 50) if ws else None
        ws_p95 = _percentile(ws, 95) if ws else None
        ws_p99 = _percentile(ws, 99) if ws else None
        api_p50 = _percentile(api, 50) if api else None
        api_p95 = _percentile(api, 95) if api else None

        return {
            "measured": True,
            "samples": {
                "ws": len(ws),
                "api": len(api),
            },
            "ws_tick_latency_ms": ws_p50,
            "ws_tick_p95_ms": ws_p95,
            "ws_tick_p99_ms": ws_p99,
            "api_roundtrip_ms": api_p50,
            "api_roundtrip_p95_ms": api_p95,
        }


def _percentile(samples: list[float], pct: int) -> float:
    s = sorted(samples)
    idx = max(0, int(len(s) * pct / 100) - 1)
    return s[idx]
