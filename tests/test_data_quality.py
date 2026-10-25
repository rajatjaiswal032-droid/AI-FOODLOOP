import io

import pytest

from app.core.config import settings
from app.forecasting.baseline import forecast_demand
from app.forecasting.preprocessing import (
    assess_data_quality,
    assess_forecast_readiness,
    preprocess_demand_data,
)


VALID_CSV = (
    "date,meal_name,quantity_prepared,quantity_consumed\n"
    "2026-01-01,Rice,100,80\n"
    "2026-01-02,Rice,100,90\n"
)


def test_quality_summary_reports_valid_dataset():
    report = assess_data_quality(VALID_CSV.encode())

    assert report.total_rows == 2
    assert report.total_columns == 4
    assert report.valid_rows == 2
    assert report.invalid_rows == 0
    assert report.earliest_date == "2026-01-01"
    assert report.latest_date == "2026-01-02"
    assert report.distinct_meals == 1
    assert report.prepared_total == 200
    assert report.consumed_total == 170
    assert report.observed_surplus == 30
    assert report.forecast_readiness == "READY"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "empty"),
        (b"   \n\t", "empty"),
        (b"date,meal_name,quantity_prepared,quantity_consumed\n", "header"),
        (b'date,meal_name,quantity_prepared,quantity_consumed\n"2026-01-01,Rice,100,80\n', "malformed"),
    ],
)
def test_quality_summary_reports_empty_and_malformed_files(payload, message):
    report = assess_data_quality(payload)
    assert report.forecast_readiness == "NOT READY"
    assert message in report.blocking_errors[0].lower()


def test_quality_summary_reports_schema_and_value_errors():
    payload = (
        "date,date,meal_name,quantity_prepared,quantity_consumed,extra\n"
        "bad,bad,Rice,-1,not-a-number,value\n"
    ).encode()
    report = assess_data_quality(payload)

    assert report.duplicate_columns == ("date",)
    assert report.missing_required_columns == ()
    assert report.unexpected_columns == ("date.1", "extra")
    assert report.invalid_date_values == 1
    assert report.invalid_numeric_values["quantity_consumed"] == 1
    assert report.negative_quantities["quantity_prepared"] == 1
    assert report.forecast_readiness == "NOT READY"


def test_quality_summary_reports_missing_values_and_duplicate_rows():
    payload = (
        "date,meal_name,quantity_prepared,quantity_consumed\n"
        "2026-01-01,Rice,,80\n"
        "2026-01-01,Rice,,80\n"
    ).encode()
    report = assess_data_quality(payload)

    assert report.missing_values["quantity_prepared"] == 2
    assert report.duplicate_rows == 1
    assert report.invalid_rows == 2
    assert report.blocking_errors


def test_optional_columns_can_be_absent():
    report = assess_data_quality(VALID_CSV.encode())
    assert report.forecast_readiness == "READY"
    assert report.blocking_errors == ()


def test_quality_summary_rejects_unsupported_encoding():
    report = assess_data_quality("date,meal_name\n2026-01-01,Rizé".encode("latin-1"))
    assert "utf-8" in report.blocking_errors[0].lower()


def test_upload_limits_are_enforced(monkeypatch):
    monkeypatch.setattr(settings, "upload_max_bytes", 10)
    assert "byte" in assess_data_quality(VALID_CSV.encode()).blocking_errors[0]

    monkeypatch.setattr(settings, "upload_max_bytes", 5_000_000)
    monkeypatch.setattr(settings, "upload_max_rows", 1)
    assert "rows" in assess_data_quality(VALID_CSV.encode()).blocking_errors[0]

    monkeypatch.setattr(settings, "upload_max_rows", 50_000)
    monkeypatch.setattr(settings, "upload_max_columns", 3)
    assert "columns" in assess_data_quality(VALID_CSV.encode()).blocking_errors[0]


def test_invalid_upload_does_not_reuse_previous_report():
    valid = assess_data_quality(VALID_CSV.encode())
    invalid = assess_data_quality(
        b"date,meal_name,quantity_prepared,quantity_consumed\nbad,Rice,not-number,80\n"
    )

    assert valid.total_rows == 2
    assert invalid.total_rows == 1
    assert invalid.forecast_readiness == "NOT READY"
    assert invalid.prepared_total != valid.prepared_total


def test_forecast_readiness_matches_actual_forecast_requirements():
    data = preprocess_demand_data(io.BytesIO(VALID_CSV.encode()))

    ready = assess_forecast_readiness(data, "Rice", "2026-01-03")
    assert ready.status == "READY WITH WARNINGS"
    assert ready.messages
    assert forecast_demand(data, "Rice", "2026-01-03").recommended_production == 89.25

    not_ready = assess_forecast_readiness(data, "Rice", "2025-12-01")
    assert not_ready.status == "NOT READY"
    with pytest.raises(ValueError, match="No historical observations"):
        forecast_demand(data, "Rice", "2025-12-01")


def test_quality_summary_does_not_mutate_source():
    payload = VALID_CSV.encode()
    assess_data_quality(payload)
    assert payload == VALID_CSV.encode()


def test_dataframe_source_is_supported():
    report = assess_data_quality(io.BytesIO(VALID_CSV.encode()))
    assert report.valid_rows == 2
