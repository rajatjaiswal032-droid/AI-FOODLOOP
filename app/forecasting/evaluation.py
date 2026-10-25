from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Sequence

import pandas as pd

from app.forecasting.baseline import forecast_demand


@dataclass(frozen=True)
class EvaluationMetrics:
    mae: float
    rmse: float
    wape: float | None


@dataclass(frozen=True)
class EvaluationResult:
    status: str
    meal_name: str
    evaluation_start: str | None
    evaluation_end: str | None
    evaluated_observations: int
    metrics: EvaluationMetrics | None
    predictions: pd.DataFrame
    message: str


def mean_absolute_error(actual: Sequence[float], predicted: Sequence[float]) -> float:
    actual_values, predicted_values = _validated_values(actual, predicted)
    return sum(abs(actual_value - predicted_value) for actual_value, predicted_value in zip(actual_values, predicted_values)) / len(actual_values)


def root_mean_squared_error(actual: Sequence[float], predicted: Sequence[float]) -> float:
    actual_values, predicted_values = _validated_values(actual, predicted)
    squared_errors = [
        (actual_value - predicted_value) ** 2
        for actual_value, predicted_value in zip(actual_values, predicted_values)
    ]
    return sqrt(sum(squared_errors) / len(squared_errors))


def weighted_absolute_percentage_error(
    actual: Sequence[float], predicted: Sequence[float]
) -> float | None:
    actual_values, predicted_values = _validated_values(actual, predicted)
    denominator = sum(abs(actual_value) for actual_value in actual_values)
    if denominator == 0:
        return None
    numerator = sum(
        abs(actual_value - predicted_value)
        for actual_value, predicted_value in zip(actual_values, predicted_values)
    )
    return numerator / denominator * 100


def calculate_metrics(
    actual: Sequence[float], predicted: Sequence[float]
) -> EvaluationMetrics:
    return EvaluationMetrics(
        mae=round(mean_absolute_error(actual, predicted), 4),
        rmse=round(root_mean_squared_error(actual, predicted), 4),
        wape=_rounded_or_none(weighted_absolute_percentage_error(actual, predicted)),
    )


def evaluate_forecast(
    data: pd.DataFrame,
    meal_name: str,
    test_size: int = 3,
    min_train_observations: int = 2,
    lookback_days: int = 28,
) -> EvaluationResult:
    _validate_evaluation_configuration(test_size, min_train_observations)
    unavailable = _unavailable_result(meal_name)

    if data.empty:
        return unavailable("Evaluation unavailable: the dataset is empty.")
    required_columns = {"date", "meal_name", "quantity_consumed"}
    missing_columns = required_columns - set(data.columns)
    if missing_columns:
        columns = ", ".join(sorted(missing_columns))
        return unavailable(f"Evaluation unavailable: missing columns: {columns}.")

    working = data.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    if working["date"].isna().any():
        return unavailable("Evaluation unavailable: invalid dates were found.")
    working["quantity_consumed"] = pd.to_numeric(
        working["quantity_consumed"], errors="coerce"
    )
    if working["quantity_consumed"].isna().any() or (
        working["quantity_consumed"] < 0
    ).any():
        return unavailable(
            "Evaluation unavailable: consumption values must be non-negative numbers."
        )

    meal_data = (
        working[working["meal_name"] == meal_name]
        .sort_values("date", kind="stable")
        .reset_index(drop=True)
    )
    if len(meal_data) <= min_train_observations:
        return unavailable(
            "Evaluation unavailable: insufficient historical observations for a "
            "chronological holdout."
        )

    split_index = len(meal_data) - min(test_size, len(meal_data) - min_train_observations)
    prediction_rows: list[dict[str, object]] = []
    skipped = 0
    for position in range(split_index, len(meal_data)):
        observation = meal_data.iloc[position]
        history = meal_data.iloc[:position]
        try:
            forecast = forecast_demand(
                history,
                meal_name,
                observation["date"].date().isoformat(),
                safety_buffer=0,
                lookback_days=lookback_days,
            )
        except ValueError:
            skipped += 1
            continue
        prediction_rows.append(
            {
                "date": observation["date"].date().isoformat(),
                "meal_name": meal_name,
                "actual": float(observation["quantity_consumed"]),
                "predicted": forecast.expected_demand,
                "training_observations": len(history),
                "method": forecast.method,
            }
        )

    predictions = pd.DataFrame(
        prediction_rows,
        columns=[
            "date",
            "meal_name",
            "actual",
            "predicted",
            "training_observations",
            "method",
        ],
    )
    if predictions.empty:
        return unavailable(
            "Evaluation unavailable: no test observations had sufficient prior history."
        )

    metrics = calculate_metrics(
        predictions["actual"].tolist(), predictions["predicted"].tolist()
    )
    message = (
        f"Chronological holdout evaluated {len(predictions)} observation(s)."
    )
    if skipped:
        message += f" {skipped} observation(s) were unavailable due to insufficient history."
    if metrics.wape is None:
        message += " WAPE is unavailable because total actual consumption is zero."

    return EvaluationResult(
        status="evaluated",
        meal_name=meal_name,
        evaluation_start=str(predictions["date"].iloc[0]),
        evaluation_end=str(predictions["date"].iloc[-1]),
        evaluated_observations=len(predictions),
        metrics=metrics,
        predictions=predictions,
        message=message,
    )


def _validated_values(
    actual: Sequence[float], predicted: Sequence[float]
) -> tuple[list[float], list[float]]:
    actual_values = [float(value) for value in actual]
    predicted_values = [float(value) for value in predicted]
    if not actual_values:
        raise ValueError("At least one observation is required to calculate metrics.")
    if len(actual_values) != len(predicted_values):
        raise ValueError("Actual and predicted values must have compatible shapes.")
    if not all(isfinite(value) for value in actual_values + predicted_values):
        raise ValueError("Actual and predicted values must be finite numbers.")
    return actual_values, predicted_values


def _rounded_or_none(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _validate_evaluation_configuration(test_size: int, min_train_observations: int) -> None:
    if test_size <= 0:
        raise ValueError("test_size must be greater than zero.")
    if min_train_observations <= 0:
        raise ValueError("min_train_observations must be greater than zero.")


def _unavailable_result(meal_name: str):
    def create(message: str) -> EvaluationResult:
        return EvaluationResult(
            status="unavailable",
            meal_name=meal_name,
            evaluation_start=None,
            evaluation_end=None,
            evaluated_observations=0,
            metrics=None,
            predictions=pd.DataFrame(
                columns=[
                    "date",
                    "meal_name",
                    "actual",
                    "predicted",
                    "training_observations",
                    "method",
                ]
            ),
            message=message,
        )

    return create
