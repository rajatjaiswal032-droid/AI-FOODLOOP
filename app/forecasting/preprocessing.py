import csv
import io
from dataclasses import dataclass
from typing import BinaryIO

import pandas as pd

from app.core.config import settings


REQUIRED_COLUMNS = {"date", "meal_name", "quantity_prepared", "quantity_consumed"}
OPTIONAL_COLUMNS = {"day_of_week", "event_flag", "weather"}
ALLOWED_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


@dataclass(frozen=True)
class DataQualityReport:
    total_rows: int
    total_columns: int
    valid_rows: int
    invalid_rows: int
    missing_values: dict[str, int]
    duplicate_rows: int
    duplicate_columns: tuple[str, ...]
    missing_required_columns: tuple[str, ...]
    unexpected_columns: tuple[str, ...]
    invalid_date_values: int
    invalid_numeric_values: dict[str, int]
    negative_quantities: dict[str, int]
    earliest_date: str | None
    latest_date: str | None
    distinct_meals: int | None
    prepared_total: float | None
    consumed_total: float | None
    observed_surplus: float | None
    blocking_errors: tuple[str, ...]
    warnings: tuple[str, ...]
    forecast_readiness: str


@dataclass(frozen=True)
class ForecastReadiness:
    status: str
    messages: tuple[str, ...]


def _source_bytes(source: BinaryIO | bytes | str) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        with open(source, "rb") as handle:
            return handle.read()
    return source.read()


def _limits() -> tuple[int, int, int]:
    limits = (
        settings.upload_max_bytes,
        settings.upload_max_rows,
        settings.upload_max_columns,
    )
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in limits):
        raise ValueError("Upload limits must be positive integers.")
    return limits


def _quality_error_report(message: str) -> DataQualityReport:
    return DataQualityReport(
        total_rows=0,
        total_columns=0,
        valid_rows=0,
        invalid_rows=0,
        missing_values={},
        duplicate_rows=0,
        duplicate_columns=(),
        missing_required_columns=(),
        unexpected_columns=(),
        invalid_date_values=0,
        invalid_numeric_values={},
        negative_quantities={},
        earliest_date=None,
        latest_date=None,
        distinct_meals=None,
        prepared_total=None,
        consumed_total=None,
        observed_surplus=None,
        blocking_errors=(message,),
        warnings=(),
        forecast_readiness="NOT READY",
    )


def assess_data_quality(source: BinaryIO | bytes | str) -> DataQualityReport:
    max_bytes, max_rows, max_columns = _limits()
    try:
        raw = _source_bytes(source)
    except (OSError, AttributeError, TypeError) as error:
        return _quality_error_report(f"Unable to read the uploaded file: {error}.")
    if len(raw) > max_bytes:
        return _quality_error_report(
            f"File exceeds the {max_bytes:,}-byte upload limit."
        )
    if not raw.strip():
        return _quality_error_report("The uploaded CSV is empty or whitespace-only.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _quality_error_report(
            "The uploaded CSV must use UTF-8 encoding, with or without a BOM."
        )

    try:
        rows = list(csv.reader(io.StringIO(text), strict=True))
    except csv.Error as error:
        return _quality_error_report(f"The uploaded CSV is malformed: {error}")
    if not rows or not any(cell.strip() for cell in rows[0]):
        return _quality_error_report("The uploaded CSV does not contain a header.")
    header = rows[0]
    duplicate_columns = tuple(
        sorted({column for column in header if header.count(column) > 1 and column})
    )
    if len(header) > max_columns:
        return _quality_error_report(
            f"CSV contains {len(header):,} columns; the limit is {max_columns:,}."
        )
    data_rows = rows[1:]
    if len(data_rows) > max_rows:
        return _quality_error_report(
            f"CSV contains {len(data_rows):,} rows; the limit is {max_rows:,}."
        )
    if any(len(row) != len(header) for row in data_rows):
        return _quality_error_report(
            "The uploaded CSV has inconsistent row lengths or malformed quoted fields."
        )

    try:
        frame = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return _quality_error_report("The uploaded CSV is empty or whitespace-only.")
    except (pd.errors.ParserError, UnicodeDecodeError) as error:
        return _quality_error_report(f"The uploaded CSV is malformed: {error}")
    if frame.empty:
        return _quality_error_report(
            "The uploaded CSV contains a header but no records."
        )

    columns = [str(column) for column in frame.columns]
    missing_required = tuple(sorted(REQUIRED_COLUMNS - set(columns)))
    unexpected = tuple(sorted(set(columns) - ALLOWED_COLUMNS))
    missing_values = {
        str(column): int(count)
        for column, count in frame.isna().sum().items()
        if count
    }
    duplicate_rows = int(frame.duplicated().sum())
    invalid_dates = 0
    invalid_numeric: dict[str, int] = {}
    negative: dict[str, int] = {}
    valid_mask = pd.Series(True, index=frame.index)
    if missing_required:
        valid_mask &= False
    else:
        required_missing = frame[list(REQUIRED_COLUMNS)].isna().any(axis=1)
        valid_mask &= ~required_missing
        parsed_dates = pd.to_datetime(frame["date"], errors="coerce")
        invalid_dates = int(parsed_dates.isna().sum())
        valid_mask &= parsed_dates.notna()
        for column in ("quantity_prepared", "quantity_consumed"):
            numeric = pd.to_numeric(frame[column], errors="coerce")
            invalid_numeric[column] = int(numeric.isna().sum())
            negative[column] = int((numeric < 0).fillna(False).sum())
            valid_mask &= numeric.notna() & (numeric >= 0)
        valid_mask &= frame["meal_name"].astype("string").str.strip().ne("")

    blocking_errors: list[str] = []
    if duplicate_columns:
        blocking_errors.append(
            f"Duplicate column names are ambiguous: {', '.join(duplicate_columns)}."
        )
    if missing_required:
        blocking_errors.append(
            f"Missing required columns: {', '.join(missing_required)}."
        )
    if unexpected:
        blocking_errors.append(f"Unexpected columns: {', '.join(unexpected)}.")
    if missing_values:
        required_missing_values = sorted(set(missing_values) & REQUIRED_COLUMNS)
        if required_missing_values:
            blocking_errors.append(
                "Required columns contain missing values: "
                + ", ".join(required_missing_values)
                + "."
            )
    if invalid_dates:
        blocking_errors.append(f"Column 'date' contains {invalid_dates} invalid value(s).")
    if any(invalid_numeric.values()):
        blocking_errors.append("Required quantity columns contain invalid numeric values.")
    if any(negative.values()):
        blocking_errors.append("Quantities must be non-negative.")
    if duplicate_rows:
        blocking_errors.append(f"The uploaded CSV contains {duplicate_rows} duplicate row(s).")
    if any(frame["meal_name"].astype("string").str.strip().eq("")) if "meal_name" in frame else False:
        blocking_errors.append("Column 'meal_name' cannot contain blank values.")

    valid_rows = int(valid_mask.sum()) if len(valid_mask) else 0
    dates = pd.to_datetime(frame.loc[valid_mask, "date"], errors="coerce") if not missing_required else pd.Series(dtype="datetime64[ns]")
    prepared_total = consumed_total = observed_surplus = None
    distinct_meals = None
    earliest_date = latest_date = None
    if not missing_required:
        valid_frame = frame.loc[valid_mask].copy()
        distinct_meals = int(valid_frame["meal_name"].nunique())
        numeric_prepared = pd.to_numeric(valid_frame["quantity_prepared"], errors="coerce")
        numeric_consumed = pd.to_numeric(valid_frame["quantity_consumed"], errors="coerce")
        prepared_total = float(numeric_prepared.sum())
        consumed_total = float(numeric_consumed.sum())
        observed_surplus = float((numeric_prepared - numeric_consumed).clip(lower=0).sum())
        if not dates.empty:
            earliest_date = dates.min().date().isoformat()
            latest_date = dates.max().date().isoformat()

    warnings: list[str] = []
    if not missing_required and valid_rows < 2:
        warnings.append("Only one valid historical row is available; forecast limitations may be substantial.")
    if missing_values and not (set(missing_values) & REQUIRED_COLUMNS):
        warnings.append("Optional columns contain missing values.")
    if not blocking_errors:
        readiness = "READY WITH WARNINGS" if warnings else "READY"
    else:
        readiness = "NOT READY"
    return DataQualityReport(
        total_rows=len(frame),
        total_columns=len(columns),
        valid_rows=valid_rows,
        invalid_rows=len(frame) - valid_rows,
        missing_values=missing_values,
        duplicate_rows=duplicate_rows,
        duplicate_columns=duplicate_columns,
        missing_required_columns=missing_required,
        unexpected_columns=unexpected,
        invalid_date_values=invalid_dates,
        invalid_numeric_values=invalid_numeric,
        negative_quantities=negative,
        earliest_date=earliest_date,
        latest_date=latest_date,
        distinct_meals=distinct_meals,
        prepared_total=prepared_total,
        consumed_total=consumed_total,
        observed_surplus=observed_surplus,
        blocking_errors=tuple(blocking_errors),
        warnings=tuple(warnings),
        forecast_readiness=readiness,
    )


def assess_forecast_readiness(
    data: pd.DataFrame,
    meal_name: str,
    forecast_date: str,
    lookback_days: int = 28,
) -> ForecastReadiness:
    if not lookback_days > 0:
        return ForecastReadiness("NOT READY", ("Lookback days must be greater than zero.",))
    try:
        target_date = pd.Timestamp(forecast_date)
    except (TypeError, ValueError):
        return ForecastReadiness("NOT READY", ("Forecast date is invalid.",))
    if meal_name not in set(data["meal_name"]):
        return ForecastReadiness("NOT READY", (f"No observations found for meal '{meal_name}'.",))
    history = data[
        (data["meal_name"] == meal_name)
        & (data["date"] < target_date)
        & (data["date"] >= target_date - pd.to_timedelta(lookback_days, unit="D"))
    ]
    if history.empty:
        return ForecastReadiness(
            "NOT READY",
            ("No historical observations are available before the forecast date in the lookback window.",),
        )
    messages: list[str] = []
    if len(history) < 2:
        messages.append("Only one observation is available for this forecast.")
    if len(history[history["date"].dt.day_name() == target_date.day_name()]) < 2:
        messages.append("Not enough same-weekday observations; the recent meal history will be used.")
    return ForecastReadiness(
        "READY WITH WARNINGS" if messages else "READY",
        tuple(messages),
    )


def preprocess_demand_data(source: BinaryIO | str) -> pd.DataFrame:
    raw = _source_bytes(source)
    report = assess_data_quality(raw)
    if report.total_rows == 0:
        raise ValueError(report.blocking_errors[0])
    if report.blocking_errors:
        raise ValueError(report.blocking_errors[0])
    try:
        frame = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
    except pd.errors.EmptyDataError as error:
        raise ValueError("The uploaded CSV is empty.") from error
    if frame.empty:
        raise ValueError("The uploaded CSV contains a header but no records.")

    cleaned = frame.copy()
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")
    if cleaned["date"].isna().any():
        raise ValueError("Column 'date' contains invalid dates.")

    for column in ("quantity_prepared", "quantity_consumed"):
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
        if cleaned[column].isna().any() or (cleaned[column] < 0).any():
            raise ValueError(f"Column '{column}' must contain non-negative numbers.")

    cleaned["meal_name"] = cleaned["meal_name"].astype("string").str.strip()
    if cleaned["meal_name"].isna().any() or (cleaned["meal_name"] == "").any():
        raise ValueError("Column 'meal_name' cannot contain blank values.")

    cleaned["quantity_waste"] = (
        cleaned["quantity_prepared"] - cleaned["quantity_consumed"]
    ).clip(lower=0)
    cleaned["day_of_week"] = cleaned["date"].dt.day_name()
    return cleaned.sort_values("date").reset_index(drop=True)
