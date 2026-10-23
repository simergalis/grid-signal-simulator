"""Stable, recorded resolution of all simulation RNG seeds."""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Mapping


# PROPOSED_HERE: version the keyed derivation so a future seed-contract change
# cannot silently replay a run with different consumer streams. Source: DR
# IMPL-ISL-1 (D4), which requires stable per-consumer derivation.
SEED_DERIVATION_VERSION = "d4-sha256-v1"


def resolve_run_seed_manifest(
    run_seed: int | str | None = None,
    *,
    consumer_names: set[str] | list[str] | tuple[str, ...] = (),
    configured_seeds: Mapping[str, int | str | None] | None = None,
    existing_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a run root and named consumer seeds exactly once.

    A missing root draws one 64-bit value and records it. An existing manifest
    keeps that root and all previously resolved consumers while deterministically
    extending the consumer map for units materialized later in the build.
    """

    if existing_manifest is not None:
        root_seed = existing_manifest.get("root_seed")
        if root_seed is None:
            raise ValueError("existing seed manifest has no root_seed")
        if run_seed is not None and str(run_seed) != str(root_seed):
            raise ValueError("run_seed does not match existing seed manifest")
        resolved_at = existing_manifest.get("resolved_at_utc")
        consumer_seeds = dict(existing_manifest.get("consumer_seeds") or {})
        consumer_sources = dict(existing_manifest.get("consumer_sources") or {})
        requested_seed = existing_manifest.get("requested_run_seed")
        root_was_drawn = bool(existing_manifest.get("root_seed_drawn", False))
    else:
        root_was_drawn = run_seed is None
        root_seed = secrets.randbits(64) if root_was_drawn else run_seed
        requested_seed = run_seed
        resolved_at = datetime.fromtimestamp(time.time(), timezone.utc).isoformat()
        consumer_seeds = {}
        consumer_sources = {}

    configured = dict(configured_seeds or {})
    names = set(consumer_names) | set(configured)
    for name in sorted(names):
        if name in consumer_seeds:
            continue
        configured_seed = configured.get(name)
        if configured_seed is not None:
            try:
                resolved_seed = int(configured_seed)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"seed for {name!r} must be an integer") from exc
            consumer_sources[name] = "explicit_config"
        else:
            root_material = f"{type(root_seed).__name__}:{root_seed}".encode("utf-8")
            digest = hashlib.sha256(
                b"GridSignal/" + SEED_DERIVATION_VERSION.encode("ascii")
                + b"\0" + root_material + b"\0" + name.encode("utf-8")
            ).digest()
            resolved_seed = int.from_bytes(digest[:8], "big", signed=False)
            consumer_sources[name] = "derived_from_run_seed"
        consumer_seeds[name] = resolved_seed

    return {
        "seed_derivation_version": SEED_DERIVATION_VERSION,
        "requested_run_seed": requested_seed,
        "root_seed": root_seed,
        "root_seed_drawn": root_was_drawn,
        "resolved_at_utc": resolved_at,
        "consumer_seeds": consumer_seeds,
        "consumer_sources": consumer_sources,
    }


def seed_consumers_for_spec(spec: Mapping[str, Any]) -> tuple[set[str], dict[str, int | str | None]]:
    """List named RNG consumers and explicit spec seeds without deriving them."""

    names: set[str] = {
        "fabric",
        "solar_sim",
        "advisory_deidentification",
        "scada",
        "price_curve",
        "procurement_price_curve",
    }
    configured: dict[str, int | str | None] = {
        "scada": 42,
        "price_curve": 42,
    }

    kube_clusters = spec.get("kube_clusters") or []
    if kube_clusters:
        for index, cluster in enumerate(kube_clusters):
            key = str(
                cluster.get("cluster_id")
                or cluster.get("tenant_id")
                or f"cluster-{index}"
            )
            name = f"kube:{key}"
            names.add(name)
            configured[name] = cluster.get("rng_seed", 42)
    elif spec.get("kube_config") is not None:
        raw = spec.get("kube_config") or {}
        base = raw.get("rng_seed", 42)
        for tenant, offset in (("A", 0), ("B", 1), ("C", 2)):
            name = f"kube:legacy-shared-fleet:{tenant}"
            names.add(name)
            configured[name] = None if base is None else int(base) + offset

    for key, seed_field, consumer in (
        ("cluster_gen_config", "rng_seed", "cluster_generator"),
        ("stressor_gen_config", "rng_seed", "stressor_generator"),
        ("param_sampling_config", "seed", "parameter_sampler"),
        ("telemetry_corruption_config", "seed", "telemetry_corruption"),
    ):
        value = spec.get(key)
        if value is not None:
            names.add(consumer)
            configured[consumer] = value.get(seed_field)

    for index, unit in enumerate(spec.get("diesel_units") or []):
        asset_id = str(unit.get("asset_id") or f"diesel-{index:03d}")
        names.add(f"diesel:{asset_id}")

    procurement = spec.get("procurement_config") or {}
    configured["procurement_price_curve"] = procurement.get(
        "price_curve_seed", 42
    )

    return names, configured
