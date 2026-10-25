from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ForecastResult:
    meal_name: str
    forecast_date: str
    expected_demand: float
    recommended_production: float
    safety_buffer: float
    observations_used: int
    method: str = "recent_mean"
    limitation: str = ""


def forecast_demand(
    data: pd.DataFrame,
    meal_name: str,
    forecast_date: str,
    safety_buffer: float = 0.05,
    lookback_days: int = 28,
) -> ForecastResult:
    if not 0 <= safety_buffer <= 1:
        raise ValueError("safety_buffer must be between 0 and 1.")
    target_date = pd.Timestamp(forecast_date)
    if meal_name not in set(data["meal_name"]):
        raise ValueError(f"No observations found for meal '{meal_name}'.")

    history = data[
        (data["meal_name"] == meal_name)
        & (data["date"] < target_date)
        & (data["date"] >= target_date - pd.to_timedelta(lookback_days, unit="D"))
    ]
    if history.empty:
        raise ValueError("No historical observations are available in the lookback window.")

    target_weekday = target_date.day_name()
    weekday_history = history[history["date"].dt.day_name() == target_weekday]
    if len(weekday_history) >= 2:
        forecast_history = weekday_history
        method = "weekday_mean"
        limitation = ""
    else:
        forecast_history = history
        method = "recent_mean"
        limitation = (
            "Not enough same-weekday observations; the recent meal history was used."
            if len(weekday_history) < 2
            else ""
        )

    expected = float(forecast_history["quantity_consumed"].mean())
    return ForecastResult(
        meal_name=meal_name,
        forecast_date=target_date.date().isoformat(),
        expected_demand=round(expected, 2),
        recommended_production=round(expected * (1 + safety_buffer), 2),
        safety_buffer=safety_buffer,
        observations_used=len(forecast_history),
        method=method,
        limitation=limitation,
    )
