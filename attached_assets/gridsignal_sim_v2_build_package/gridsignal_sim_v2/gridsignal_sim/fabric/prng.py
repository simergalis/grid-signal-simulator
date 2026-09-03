"""
Counter-based, tuple-addressed PRNG (Simulator Spec 12.7).

Every draw is addressed by (seed, substream, tick, address).  SHA-256 hashes
the concatenated key, then maps the first 8 bytes to a float in [0, 1).
Because the address is explicit rather than implicit in a sequence position,
draws are independent of evaluation order and of whether earlier ticks have
been evaluated.  This is the property random.seed() does not have and the
reason TC-77 (reproducibility) and TC-78 (substream isolation) exist.

Substreams are declared up-front.  An undeclared substream raises ValueError
so that a typo in a substream name produces a hard failure at the first draw
rather than a silent divergence that only surfaces in a scenario assertion.
"""

from __future__ import annotations

import hashlib
import math
import struct

SUBSTREAMS: frozenset[str] = frozenset(
    {
        "fabric.ecmp",
        "fabric.jitter",
        "fabric.faults",
        "fabric.pfc",
        "fabric.loss",
    }
)


def _u64(seed: int, substream: str, tick: int, address: str) -> int:
    """Return a 64-bit unsigned integer drawn from the addressed cell."""
    if substream not in SUBSTREAMS:
        raise ValueError(
            f"undeclared PRNG substream {substream!r}; "
            f"declare it in fabric.prng.SUBSTREAMS first"
        )
    key = f"{seed}:{substream}:{tick}:{address}".encode()
    digest = hashlib.sha256(key).digest()
    return struct.unpack(">Q", digest[:8])[0]


def _to_float(n: int) -> float:
    """Map a 64-bit unsigned integer to [0, 1)."""
    return n / (2**64)


def uniform(seed: int, substream: str, tick: int, address: str) -> float:
    """Uniform draw on [0, 1)."""
    return _to_float(_u64(seed, substream, tick, address))


def normal(seed: int, substream: str, tick: int, address: str) -> float:
    """Standard normal draw via inverse-CDF of a uniform draw."""
    u = _to_float(_u64(seed, substream, tick, address))
    # Clamp away from exact 0 and 1 to keep erfinv finite.
    u = max(1e-15, min(1.0 - 1e-15, u))
    return _icdf_normal(u)


def lognormal(
    seed: int, substream: str, tick: int, address: str, median: float, sigma: float
) -> float:
    """
    Lognormal draw.  ``median`` is the median of the distribution;
    ``sigma`` is the shape (standard deviation of the underlying normal).
    """
    z = normal(seed, substream, tick, address)
    return median * math.exp(sigma * z)


def randint(
    seed: int, substream: str, tick: int, address: str, n: int
) -> int:
    """Uniform integer draw on [0, n)."""
    u = _to_float(_u64(seed, substream, tick, address))
    return int(u * n)


# ---------------------------------------------------------------------------
# Inverse-CDF for standard normal (rational approximation, Abramowitz &
# Stegun 26.2.16, maximum absolute error < 4.5e-4 -- adequate for a
# simulation shaping parameter, far cheaper than scipy).
# ---------------------------------------------------------------------------


def _icdf_normal(p: float) -> float:
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    sign = 1.0 if p >= 0.5 else -1.0
    q = p if p >= 0.5 else 1.0 - p
    t = math.sqrt(-2.0 * math.log(1.0 - q))
    num = c0 + c1 * t + c2 * t * t
    den = 1.0 + d1 * t + d2 * t * t + d3 * t * t * t
    return sign * (t - num / den)
