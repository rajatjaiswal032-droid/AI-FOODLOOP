import pandas as pd
import pytest

from app.analytics.insights import (
    analyze_insights,
    analyze_meal_surplus,
    analyze_surplus_trend,
    analyze_weekday_surplus,
)


def make_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [
                "2026-01-05",
                "2026-01-06",
                "2026-01-12",
                "2026-01-13",
                "2026-01-14",
                "2026-01-21",
            ],
            "meal_name": ["Rice", "Rice", "Rice", "Soup", "Soup", "Soup"],
            "quantity_prepared": [100, 100, 100, 50, 50, 50],
            "quantity_consumed": [80, 70, 90, 50, 40, 45],
        }
    )


def test_meal_summary_totals_and_rates():
    summary = analyze_meal_surplus(make_data())
    rice = summary.loc[summary["meal_name"] == "Rice"].iloc[0]
    assert rice["total_prepared"] == 300
    assert rice["total_consumed"] == 240
    assert rice["total_surplus"] == 60
    assert rice["observations"] == 3
    assert rice["surplus_rate_percent"] == 20


def test_zero_prepared_quantity_keeps_rate_unavailable():
    data = pd.DataFrame(
        {
            "date": ["2026-01-01"],
            "meal_name": ["Rice"],
            "quantity_prepared": [0],
            "quantity_consumed": [0],
        }
    )
    summary = analyze_meal_surplus(data)
    assert pd.isna(summary.iloc[0]["surplus_rate_percent"])


def test_no_surplus_generates_no_fake_surplus_signal():
    data = make_data()
    data["quantity_consumed"] = data["quantity_prepared"]
    result = analyze_insights(data)
    assert result.status == "available"
    assert result.meal_summary["total_surplus"].sum() == 0
    assert result.signals[0].title == "No supported surplus signal"


def test_weekday_summary_derives_real_weekdays_and_counts():
    summary, highest, lowest = analyze_weekday_surplus(make_data())
    assert set(summary["weekday"]) == {"Monday", "Tuesday", "Wednesday"}
    assert summary["observations"].sum() == 6
    assert highest == "Monday"
    assert lowest == "Wednesday"


def test_trend_is_chronologically_ordered():
    trend = analyze_surplus_trend(make_data())
    assert trend["date"].tolist() == [
        "2026-01-05",
        "2026-01-06",
        "2026-01-12",
        "2026-01-13",
        "2026-01-14",
        "2026-01-21",
    ]
    assert trend["total_surplus"].tolist() == [20, 30, 10, 0, 10, 5]


def test_empty_history_is_explicitly_unavailable():
    empty = pd.DataFrame(
        columns=[
            "date",
            "meal_name",
            "quantity_prepared",
            "quantity_consumed",
        ]
    )
    result = analyze_insights(empty)
    assert result.status == "unavailable"
    assert result.meal_summary.empty
    assert result.signals[0].observations == 0


def test_insufficient_weekday_history_has_no_extreme_claim():
    data = make_data().iloc[[0]].copy()
    summary, highest, lowest = analyze_weekday_surplus(data, minimum_observations=2)
    assert len(summary) == 1
    assert highest is None
    assert lowest is None


@pytest.mark.parametrize(
    "data",
    [
        pd.DataFrame(columns=["date", "meal_name", "quantity_prepared"]),
        pd.DataFrame(
            {
                "date": ["not-a-date"],
                "meal_name": ["Rice"],
                "quantity_prepared": [10],
                "quantity_consumed": [5],
            }
        ),
        pd.DataFrame(
            {
                "date": ["2026-01-01"],
                "meal_name": ["Rice"],
                "quantity_prepared": [None],
                "quantity_consumed": [5],
            }
        ),
    ],
)
def test_invalid_inputs_are_rejected(data):
    with pytest.raises(ValueError):
        analyze_meal_surplus(data)


def test_invalid_trend_frequency_is_rejected():
    with pytest.raises(ValueError, match="frequency"):
        analyze_surplus_trend(make_data(), frequency="M")
