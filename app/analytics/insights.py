from dataclasses import dataclass

import pandas as pd


REQUIRED_COLUMNS = {
    "date",
    "meal_name",
    "quantity_prepared",
    "quantity_consumed",
}
MEAL_COLUMNS = [
    "meal_name",
    "total_prepared",
    "total_consumed",
    "total_surplus",
    "observations",
    "surplus_rate_percent",
]
WEEKDAY_COLUMNS = [
    "weekday",
    "total_surplus",
    "mean_surplus",
    "observations",
]
TREND_COLUMNS = ["date", "total_prepared", "total_consumed", "total_surplus", "observations"]


@dataclass(frozen=True)
class PlanningSignal:
    title: str
    explanation: str
    evidence: str
    observations: int
    limitation: str


@dataclass(frozen=True)
class InsightsResult:
    status: str
    meal_summary: pd.DataFrame
    weekday_summary: pd.DataFrame
    trend_summary: pd.DataFrame
    signals: list[PlanningSignal]
    highest_surplus_weekday: str | None
    lowest_surplus_weekday: str | None
    message: str


def analyze_meal_surplus(data: pd.DataFrame) -> pd.DataFrame:
    prepared = _prepare_data(data)
    if prepared.empty:
        return pd.DataFrame(columns=MEAL_COLUMNS)

    summary = (
        prepared.groupby("meal_name", as_index=False)
        .agg(
            total_prepared=("quantity_prepared", "sum"),
            total_consumed=("quantity_consumed", "sum"),
            total_surplus=("quantity_surplus", "sum"),
            observations=("meal_name", "size"),
        )
        .reindex(columns=MEAL_COLUMNS[:-1])
    )
    summary["surplus_rate_percent"] = summary.apply(
        lambda row: (
            None
            if row["total_prepared"] == 0
            else round(row["total_surplus"] / row["total_prepared"] * 100, 2)
        ),
        axis=1,
    )
    return summary[MEAL_COLUMNS]


def analyze_weekday_surplus(
    data: pd.DataFrame, minimum_observations: int = 2
) -> tuple[pd.DataFrame, str | None, str | None]:
    _validate_minimum_observations(minimum_observations)
    prepared = _prepare_data(data)
    if prepared.empty:
        return pd.DataFrame(columns=WEEKDAY_COLUMNS), None, None

    summary = (
        prepared.assign(weekday=prepared["date"].dt.day_name())
        .groupby("weekday", as_index=False)
        .agg(
            total_surplus=("quantity_surplus", "sum"),
            mean_surplus=("quantity_surplus", "mean"),
            observations=("weekday", "size"),
        )
    )
    summary["mean_surplus"] = summary["mean_surplus"].round(2)
    summary = summary[WEEKDAY_COLUMNS]
    supported = summary[summary["observations"] >= minimum_observations]
    if supported.empty:
        return summary, None, None
    highest = str(supported.loc[supported["mean_surplus"].idxmax(), "weekday"])
    lowest = str(supported.loc[supported["mean_surplus"].idxmin(), "weekday"])
    return summary, highest, lowest


def analyze_surplus_trend(data: pd.DataFrame, frequency: str = "D") -> pd.DataFrame:
    prepared = _prepare_data(data)
    if frequency not in {"D", "W"}:
        raise ValueError("frequency must be 'D' or 'W'.")
    if prepared.empty:
        return pd.DataFrame(columns=TREND_COLUMNS)

    dates = prepared["date"].dt.to_period(frequency).dt.start_time
    trend = (
        prepared.assign(period=dates)
        .groupby("period", as_index=False)
        .agg(
            total_prepared=("quantity_prepared", "sum"),
            total_consumed=("quantity_consumed", "sum"),
            total_surplus=("quantity_surplus", "sum"),
            observations=("meal_name", "size"),
        )
        .rename(columns={"period": "date"})
    )
    trend["date"] = trend["date"].dt.date.astype(str)
    return trend[TREND_COLUMNS]


def generate_planning_signals(
    data: pd.DataFrame, minimum_observations: int = 2
) -> list[PlanningSignal]:
    _validate_minimum_observations(minimum_observations)
    prepared = _prepare_data(data)
    if prepared.empty:
        return [
            PlanningSignal(
                title="Insufficient history",
                explanation="No historical records are available for a planning signal.",
                evidence="0 observations",
                observations=0,
                limitation="Collect validated records before interpreting patterns.",
            )
        ]

    signals: list[PlanningSignal] = []
    meal_summary = analyze_meal_surplus(prepared)
    for row in meal_summary.itertuples(index=False):
        if row.observations >= minimum_observations and row.total_surplus > 0:
            signals.append(
                PlanningSignal(
                    title=f"Review repeated surplus for {row.meal_name}",
                    explanation=(
                        "Historical records show surplus for this meal. Review the next "
                        "production quantity alongside expected attendance and recent demand."
                    ),
                    evidence=(
                        f"{row.total_surplus:g} surplus across {row.observations} observations "
                        f"({row.surplus_rate_percent:.2f}% of prepared quantity)."
                    ),
                    observations=int(row.observations),
                    limitation="This descriptive pattern does not establish a cause or guarantee future surplus.",
                )
            )

    weekday_summary, highest, lowest = analyze_weekday_surplus(
        prepared, minimum_observations
    )
    supported = weekday_summary[
        weekday_summary["observations"] >= minimum_observations
    ]
    if highest and lowest and highest != lowest and len(supported) >= 2:
        high_value = float(
            supported.loc[supported["weekday"] == highest, "mean_surplus"].iloc[0]
        )
        low_value = float(
            supported.loc[supported["weekday"] == lowest, "mean_surplus"].iloc[0]
        )
        signals.append(
            PlanningSignal(
                title="Weekday surplus pattern to review",
                explanation=f"{highest} has the highest observed mean surplus among supported weekdays.",
                evidence=f"{highest}: {high_value:g} average surplus; {lowest}: {low_value:g}.",
                observations=int(supported["observations"].sum()),
                limitation="Weekday comparison is descriptive and does not establish causation.",
            )
        )

    if not signals:
        signals.append(
            PlanningSignal(
                title="No supported surplus signal",
                explanation="The validated history does not show a repeated surplus pattern under the current threshold.",
                evidence=f"{len(prepared)} observations reviewed.",
                observations=len(prepared),
                limitation="A lack of signal is not proof that future surplus cannot occur.",
            )
        )
    return signals


def analyze_insights(
    data: pd.DataFrame, minimum_observations: int = 2, frequency: str = "D"
) -> InsightsResult:
    _validate_minimum_observations(minimum_observations)
    prepared = _prepare_data(data)
    if prepared.empty:
        return InsightsResult(
            status="unavailable",
            meal_summary=pd.DataFrame(columns=MEAL_COLUMNS),
            weekday_summary=pd.DataFrame(columns=WEEKDAY_COLUMNS),
            trend_summary=pd.DataFrame(columns=TREND_COLUMNS),
            signals=generate_planning_signals(prepared, minimum_observations),
            highest_surplus_weekday=None,
            lowest_surplus_weekday=None,
            message="Insights unavailable: no validated historical records are available.",
        )

    weekday_summary, highest, lowest = analyze_weekday_surplus(
        prepared, minimum_observations
    )
    return InsightsResult(
        status="available",
        meal_summary=analyze_meal_surplus(prepared),
        weekday_summary=weekday_summary,
        trend_summary=analyze_surplus_trend(prepared, frequency),
        signals=generate_planning_signals(prepared, minimum_observations),
        highest_surplus_weekday=highest,
        lowest_surplus_weekday=lowest,
        message="Insights are descriptive summaries of the validated historical records.",
    )


def _prepare_data(data: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame):
        raise ValueError("Analytics input must be a pandas DataFrame.")
    missing = REQUIRED_COLUMNS - set(data.columns)
    if missing:
        raise ValueError(f"Analytics input is missing columns: {', '.join(sorted(missing))}")
    if data.empty:
        return data.copy()

    prepared = data.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    if prepared["date"].isna().any():
        raise ValueError("Analytics input contains invalid dates.")
    for column in ("quantity_prepared", "quantity_consumed"):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
        if prepared[column].isna().any() or (prepared[column] < 0).any():
            raise ValueError(f"Analytics input column '{column}' must contain non-negative numbers.")
    if prepared["meal_name"].isna().any() or (
        prepared["meal_name"].astype("string").str.strip() == ""
    ).any():
        raise ValueError("Analytics input column 'meal_name' cannot contain missing values.")
    prepared["quantity_surplus"] = (
        prepared["quantity_prepared"] - prepared["quantity_consumed"]
    ).clip(lower=0)
    return prepared.sort_values("date", kind="stable").reset_index(drop=True)


def _validate_minimum_observations(minimum_observations: int) -> None:
    if minimum_observations <= 0:
        raise ValueError("minimum_observations must be greater than zero.")
