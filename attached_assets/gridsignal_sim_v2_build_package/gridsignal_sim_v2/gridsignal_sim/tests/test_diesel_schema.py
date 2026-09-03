"""Schema and fleet-generation coverage for Addendum H diesel blocks."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from api.schemas import (
    DieselPowerBlockSpec,
    ScenarioSpec,
    binomial_survival,
    generate_diesel_fleet,
    solve_min_fleet_size,
)


def test_binomial_survival_boundary_cases() -> None:
    assert binomial_survival(5, 0.5, 0) == 1.0
    assert binomial_survival(5, 0.5, 6) == 0.0
    assert binomial_survival(1, 1.0, 1) == 1.0
    assert binomial_survival(1, 0.0, 1) == 0.0
    assert binomial_survival(2, 0.5, 1) == pytest.approx(0.75)


def test_solve_min_fleet_size_is_bounded_and_minimal() -> None:
    solved = solve_min_fleet_size(4, 0.985, 0.999)

    assert solved == 6
    assert binomial_survival(solved, 0.985, 4) >= 0.999
    assert binomial_survival(solved - 1, 0.985, 4) < 0.999


def test_solve_min_fleet_size_fails_loudly_when_target_is_unreachable() -> None:
    with pytest.raises(ValueError, match="could not reach target reliability"):
        solve_min_fleet_size(
            n_active=1,
            p_start=0.0,
            target_reliability=0.5,
            max_n_total=3,
        )


@pytest.mark.parametrize("target_capacity_mw", [10.0, 50.0, 100.0, 73.25])
def test_generate_diesel_fleet_scales_to_any_target_capacity(
    target_capacity_mw: float,
) -> None:
    block = DieselPowerBlockSpec(
        enabled=True,
        target_capacity_mw=target_capacity_mw,
    )
    fleet = generate_diesel_fleet(block)
    n_active = math.ceil(target_capacity_mw / block.unit_rating_mw)

    assert len(fleet) == solve_min_fleet_size(
        n_active,
        block.p_start,
        block.target_reliability,
    )
    assert sum(unit.role == "primary" for unit in fleet) == n_active
    assert sum(unit.role == "standby" for unit in fleet) == len(fleet) - n_active
    assert all(unit.rated_mw == block.unit_rating_mw for unit in fleet)
    assert sum(unit.rated_mw for unit in fleet if unit.role == "primary") >= target_capacity_mw


def test_generate_diesel_fleet_staggers_only_primary_units() -> None:
    block = DieselPowerBlockSpec(
        enabled=True,
        target_capacity_mw=10.0,
        unit_rating_mw=3.0,
        start_stagger_interval_s=2.0,
    )
    fleet = generate_diesel_fleet(block)
    primaries = [unit for unit in fleet if unit.role == "primary"]
    standbys = [unit for unit in fleet if unit.role == "standby"]

    assert [unit.asset_id for unit in fleet] == [
        f"diesel-{index:03d}" for index in range(len(fleet))
    ]
    assert [unit.start_offset_s for unit in primaries] == [0.0, 2.0, 4.0, 6.0]
    assert all(unit.start_offset_s is None for unit in standbys)
    assert all(
        unit.min_stable_load_mw == pytest.approx(0.9)
        for unit in fleet
    )
    assert all(unit.authority_tier == "advisory_only" for unit in fleet)


def test_scenario_validation_materializes_enabled_diesel_units() -> None:
    spec = ScenarioSpec(
        name="diesel-schema-test",
        diesel_power_block={
            "enabled": True,
            "target_capacity_mw": 50.0,
        },
    )

    assert len(spec.diesel_units) == 20
    assert len([unit for unit in spec.diesel_units if unit.role == "primary"]) == 17
    assert spec.model_dump()["diesel_units"][0]["asset_id"] == "diesel-000"


def test_disabled_or_absent_diesel_block_materializes_empty_fleet() -> None:
    assert ScenarioSpec(name="no-diesel").diesel_units == []
    assert ScenarioSpec(
        name="disabled-diesel",
        diesel_power_block={
            "enabled": False,
            "target_capacity_mw": 50.0,
        },
    ).diesel_units == []


def test_enabled_diesel_block_requires_target_capacity() -> None:
    with pytest.raises(ValidationError, match="target_capacity_mw"):
        DieselPowerBlockSpec(enabled=True)


def test_enabled_diesel_block_rejects_non_positive_capacity_at_load_time() -> None:
    with pytest.raises(ValidationError, match="target_capacity_mw must be greater than 0"):
        ScenarioSpec(
            name="invalid-diesel",
            diesel_power_block={
                "enabled": True,
                "target_capacity_mw": 0.0,
            },
        )
