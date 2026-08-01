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


@dataclass
class InstrumentPlane:
    _ws_samples: deque = field(default_factory=lambda: deque(maxlen=1000))
    _api_samples: deque = field(default_factory=lambda: deque(maxlen=1000))

    def stamp_tick(self, payload: dict) -> dict:
        """Stamp t_emit_ns onto the outgoing tick payload (wall clock only)."""
        payload = dict(payload)
        payload["t_emit_ns"] = time.monotonic_ns()
        return payload

    def observe_tick(self, t_emit_ns: int) -> None:
        """Record a WS tick latency sample from the emit timestamp."""
        now_ns = time.monotonic_ns()
        elapsed_ms = (now_ns - t_emit_ns) / 1_000_000.0
        if elapsed_ms >= 0.0:
            self._ws_samples.append(elapsed_ms)

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
