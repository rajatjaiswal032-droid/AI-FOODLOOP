import io

import pandas as pd
import pytest

from app.forecasting.planning import (
    compare_production_plan,
    create_production_plan,
)
from app.forecasting.preprocessing import preprocess_demand_data


def make_data() -> pd.DataFrame:
    return preprocess_demand_data(
        io.BytesIO(
            b"date,meal_name,quantity_prepared,quantity_consumed\n"
            b"2026-01-01,Rice,100,80\n"
            b"2026-01-02,Rice,100,90\n"
        )
    )


def test_production_plan_reuses_forecast_and_explains_calculation():
    plan = create_production_plan(
        make_data(), "Rice", "2026-01-03", safety_buffer=0.1
    )

    assert plan.forecast.expected_demand == 85
    assert plan.forecast.recommended_production == 93.5
    assert plan.forecast.safety_buffer == 0.1
    assert plan.historical_observations == 2
    assert "10% safety buffer" in plan.explanation
    assert plan.readiness.status == "READY WITH WARNINGS"


def test_production_plan_blocks_missing_history():
    with pytest.raises(ValueError, match="Production planning is not ready"):
        create_production_plan(make_data(), "Rice", "2025-12-01")


@pytest.mark.parametrize("buffer", [-0.1, 1.1])
def test_production_plan_rejects_invalid_buffer(buffer):
    with pytest.raises(ValueError, match="safety_buffer"):
        create_production_plan(make_data(), "Rice", "2026-01-03", buffer)


def test_comparison_reports_observed_surplus_and_differences():
    plan = create_production_plan(make_data(), "Rice", "2026-01-03")
    comparison = compare_production_plan(plan, actual_production=100, actual_consumption=80)

    assert comparison.observed_surplus == 20
    assert comparison.unmet_demand == 0
    assert comparison.production_consumption_difference == 20
    assert comparison.forecast_vs_actual_consumption == -5
    assert comparison.recommendation_vs_actual_production == 10.75
    assert comparison.forecast_difference_percent == pytest.approx(-5.88)
    assert comparison.recommendation_difference_percent == pytest.approx(12.04)
    assert comparison.warnings == ()


def test_comparison_reports_shortage_without_calling_it_surplus():
    plan = create_production_plan(make_data(), "Rice", "2026-01-03")
    comparison = compare_production_plan(plan, actual_production=70, actual_consumption=80)

    assert comparison.production_consumption_difference == -10
    assert comparison.observed_surplus == 0
    assert comparison.unmet_demand == 10


def test_comparison_keeps_unavailable_observations_as_none():
    plan = create_production_plan(make_data(), "Rice", "2026-01-03")
    comparison = compare_production_plan(plan)

    assert comparison.actual_production is None
    assert comparison.actual_consumption is None
    assert comparison.observed_surplus is None
    assert comparison.forecast_difference_percent is None
    assert len(comparison.warnings) == 3


def test_comparison_handles_zero_percentage_denominator():
    data = preprocess_demand_data(
        io.BytesIO(
            b"date,meal_name,quantity_prepared,quantity_consumed\n"
            b"2026-01-01,Rice,0,0\n"
        )
    )
    plan = create_production_plan(data, "Rice", "2026-01-02")
    comparison = compare_production_plan(plan, actual_production=0, actual_consumption=0)

    assert comparison.forecast_difference_percent is None
    assert comparison.recommendation_difference_percent is None


@pytest.mark.parametrize(
    "field,value",
    [("actual_production", -1), ("actual_consumption", float("nan"))],
)
def test_comparison_rejects_invalid_observations(field, value):
    plan = create_production_plan(make_data(), "Rice", "2026-01-03")
    kwargs = {field: value}
    with pytest.raises(ValueError, match=field):
        compare_production_plan(plan, **kwargs)
