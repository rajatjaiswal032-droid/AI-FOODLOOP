from dataclasses import dataclass
from math import isfinite

import pandas as pd

from app.forecasting.baseline import ForecastResult, forecast_demand
from app.forecasting.preprocessing import ForecastReadiness, assess_forecast_readiness


@dataclass(frozen=True)
class ProductionPlan:
    forecast: ForecastResult
    readiness: ForecastReadiness
    historical_consumption_total: float
    historical_observations: int
    explanation: str


@dataclass(frozen=True)
class ProductionComparison:
    forecast_demand: float
    recommended_production: float
    actual_production: float | None
    actual_consumption: float | None
    production_consumption_difference: float | None
    observed_surplus: float | None
    unmet_demand: float | None
    forecast_vs_actual_consumption: float | None
    recommendation_vs_actual_production: float | None
    forecast_difference_percent: float | None
    recommendation_difference_percent: float | None
    warnings: tuple[str, ...]


def create_production_plan(
    data: pd.DataFrame,
    meal_name: str,
    forecast_date: str,
    safety_buffer: float = 0.05,
    lookback_days: int = 28,
) -> ProductionPlan:
    readiness = assess_forecast_readiness(
        data, meal_name, forecast_date, lookback_days
    )
    if readiness.status == "NOT READY":
        raise ValueError(
            "Production planning is not ready: " + " ".join(readiness.messages)
        )

    forecast = forecast_demand(
        data,
        meal_name,
        forecast_date,
        safety_buffer=safety_buffer,
        lookback_days=lookback_days,
    )
    history = data[
        (data["meal_name"] == meal_name)
        & (data["date"] < pd.Timestamp(forecast_date))
        & (
            data["date"]
            >= pd.Timestamp(forecast_date)
            - pd.to_timedelta(lookback_days, unit="D")
        )
    ]
    historical_consumption_total = float(history["quantity_consumed"].sum())
    explanation = (
        f"Expected demand is the {forecast.method.replace('_', ' ')} of "
        f"{forecast.observations_used} historical consumption observation(s). "
        f"Recommended production applies a {forecast.safety_buffer:.0%} safety buffer "
        f"to the forecast demand."
    )
    return ProductionPlan(
        forecast=forecast,
        readiness=readiness,
        historical_consumption_total=historical_consumption_total,
        historical_observations=len(history),
        explanation=explanation,
    )


def compare_production_plan(
    plan: ProductionPlan,
    actual_production: float | None = None,
    actual_consumption: float | None = None,
) -> ProductionComparison:
    _validate_optional_quantity("actual_production", actual_production)
    _validate_optional_quantity("actual_consumption", actual_consumption)

    warnings: list[str] = []
    production_consumption_difference = None
    observed_surplus = None
    unmet_demand = None
    if actual_production is not None and actual_consumption is not None:
        production_consumption_difference = round(
            actual_production - actual_consumption, 2
        )
        observed_surplus = round(max(production_consumption_difference, 0), 2)
        unmet_demand = round(max(-production_consumption_difference, 0), 2)
    else:
        warnings.append(
            "Observed surplus is unavailable until both actual production and "
            "actual consumption are recorded for the same period."
        )

    forecast_vs_actual_consumption = _difference(
        actual_consumption, plan.forecast.expected_demand
    )
    recommendation_vs_actual_production = _difference(
        actual_production, plan.forecast.recommended_production
    )
    if actual_consumption is None:
        warnings.append("Forecast versus actual consumption is unavailable.")
    if actual_production is None:
        warnings.append("Recommendation versus actual production is unavailable.")

    return ProductionComparison(
        forecast_demand=plan.forecast.expected_demand,
        recommended_production=plan.forecast.recommended_production,
        actual_production=actual_production,
        actual_consumption=actual_consumption,
        production_consumption_difference=production_consumption_difference,
        observed_surplus=observed_surplus,
        unmet_demand=unmet_demand,
        forecast_vs_actual_consumption=forecast_vs_actual_consumption,
        recommendation_vs_actual_production=recommendation_vs_actual_production,
        forecast_difference_percent=_percentage_difference(
            actual_consumption, plan.forecast.expected_demand
        ),
        recommendation_difference_percent=_percentage_difference(
            actual_production, plan.forecast.recommended_production
        ),
        warnings=tuple(warnings),
    )


def _difference(actual: float | None, expected: float) -> float | None:
    return None if actual is None else round(actual - expected, 2)


def _percentage_difference(actual: float | None, expected: float) -> float | None:
    if actual is None or expected == 0:
        return None
    return round((actual - expected) / expected * 100, 2)


def _validate_optional_quantity(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a non-negative finite number.")
    if not isfinite(float(value)) or value < 0:
        raise ValueError(f"{name} must be a non-negative finite number.")
