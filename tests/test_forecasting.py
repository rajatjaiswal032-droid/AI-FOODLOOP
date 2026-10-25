import io

import pandas as pd
import pytest

from app.forecasting.baseline import forecast_demand
from app.forecasting.evaluation import (
    calculate_metrics,
    evaluate_forecast,
    mean_absolute_error,
    root_mean_squared_error,
    weighted_absolute_percentage_error,
)
from app.forecasting.preprocessing import preprocess_demand_data


def make_data():
    csv = """date,meal_name,quantity_prepared,quantity_consumed
2026-01-01,Rice,100,80
2026-01-02,Rice,100,90
"""
    return preprocess_demand_data(io.BytesIO(csv.encode()))


def test_preprocessing_derives_waste_and_day():
    data = make_data()
    assert data["quantity_waste"].tolist() == [20, 10]
    assert data["day_of_week"].tolist() == ["Thursday", "Friday"]


def test_forecast_uses_historical_mean_and_buffer():
    result = forecast_demand(make_data(), "Rice", "2026-01-03", safety_buffer=0.1)
    assert result.expected_demand == 85
    assert result.recommended_production == 93.5
    assert result.observations_used == 2


def test_missing_columns_are_rejected():
    with pytest.raises(ValueError, match="Missing required columns"):
        preprocess_demand_data(io.BytesIO(b"date,meal_name\n2026-01-01,Rice\n"))


def test_forecast_requires_history():
    with pytest.raises(ValueError, match="No historical observations"):
        forecast_demand(make_data(), "Rice", "2025-12-01")


@pytest.mark.parametrize(
    ("csv", "message"),
    [
        ("", "empty"),
        (
            "date,meal_name,quantity_prepared,quantity_consumed\n",
            "header but no records",
        ),
        (
            "date,meal_name,quantity_prepared,quantity_consumed\n"
            "2026-01-01,Rice,-1,10\n",
            "non-negative",
        ),
        (
            "date,meal_name,quantity_prepared,quantity_consumed\n"
            "2026-01-01,Rice,10,8\n"
            "2026-01-01,Rice,10,8\n",
            "duplicate",
        ),
    ],
)
def test_invalid_csv_is_rejected(csv, message):
    with pytest.raises(ValueError, match=message):
        preprocess_demand_data(io.BytesIO(csv.encode()))


def test_weekday_forecast_uses_same_weekday_when_supported():
    csv = """date,meal_name,quantity_prepared,quantity_consumed
2026-01-01,Rice,100,80
2026-01-08,Rice,100,90
2026-01-02,Rice,100,40
2026-01-03,Rice,100,50
"""
    result = forecast_demand(
        preprocess_demand_data(io.BytesIO(csv.encode())),
        "Rice",
        "2026-01-15",
    )
    assert result.method == "weekday_mean"
    assert result.expected_demand == 85
    assert result.observations_used == 2


def test_metrics_calculate_known_values():
    actual = [10, 20, 30]
    predicted = [12, 18, 33]
    assert mean_absolute_error(actual, predicted) == 7 / 3
    assert root_mean_squared_error(actual, predicted) == pytest.approx((17 / 3) ** 0.5)
    assert weighted_absolute_percentage_error(actual, predicted) == pytest.approx(7 / 60 * 100)
    assert calculate_metrics(actual, predicted).wape == pytest.approx(11.6667)


def test_wape_is_unavailable_when_actual_denominator_is_zero():
    assert weighted_absolute_percentage_error([0, 0], [0, 1]) is None


def test_metric_shapes_must_match():
    with pytest.raises(ValueError, match="compatible shapes"):
        mean_absolute_error([1, 2], [1])


def test_evaluation_is_chronological_and_does_not_use_future_rows():
    csv = """date,meal_name,quantity_prepared,quantity_consumed
2026-01-01,Rice,100,10
2026-01-02,Rice,100,20
2026-01-03,Rice,100,30
2026-01-04,Rice,100,1000
"""
    result = evaluate_forecast(
        preprocess_demand_data(io.BytesIO(csv.encode())),
        "Rice",
        test_size=2,
        min_train_observations=2,
    )
    assert result.status == "evaluated"
    assert result.predictions["date"].tolist() == ["2026-01-03", "2026-01-04"]
    assert result.predictions["training_observations"].tolist() == [2, 3]
    assert result.predictions["actual"].tolist() == [30, 1000]


def test_evaluation_handles_empty_and_insufficient_data():
    empty = evaluate_forecast(
        preprocess_demand_data(
            io.BytesIO(
                b"date,meal_name,quantity_prepared,quantity_consumed\n"
                b"2026-01-01,Rice,100,80\n"
            )
        ),
        "Rice",
        min_train_observations=2,
    )
    assert empty.status == "unavailable"
    assert empty.metrics is None

    insufficient = evaluate_forecast(
        pd.DataFrame(columns=["date", "meal_name", "quantity_consumed"]),
        "Rice",
    )
    assert insufficient.status == "unavailable"
