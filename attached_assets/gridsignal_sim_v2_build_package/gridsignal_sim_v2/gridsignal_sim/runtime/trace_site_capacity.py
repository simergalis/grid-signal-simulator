"""Authoritative site-level capacity limits for periodic trace validation."""

from __future__ import annotations

from typing import Mapping

from runtime.periodic_trace_import import TraceDomainConfig


SITE_TRACE_DOMAIN_CAPACITY: Mapping[str, Mapping[str, TraceDomainConfig]] = {
    "equinix-sj-1": {
        "kubernetes": TraceDomainConfig(configured=True, max_units=950, unit="node"),
        "slurm": TraceDomainConfig(configured=True, max_units=950, unit="node"),
        "ray": TraceDomainConfig(configured=True, max_units=21, unit="rack"),
    },
    "equinix-sj-2": {
        "kubernetes": TraceDomainConfig(configured=True, max_units=950, unit="node"),
        "slurm": TraceDomainConfig(configured=True, max_units=950, unit="node"),
        "ray": TraceDomainConfig(configured=True, max_units=21, unit="rack"),
    },
    # These values mirror the existing scenario-turbine-01 configuration.
    "turbine-01": {
        "kubernetes": TraceDomainConfig(configured=True, max_units=950, unit="node"),
        "slurm": TraceDomainConfig(configured=True, max_units=950, unit="node"),
        "ray": TraceDomainConfig(configured=True, max_units=21, unit="rack"),
    },
}