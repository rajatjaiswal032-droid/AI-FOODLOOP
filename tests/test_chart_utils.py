import numpy as np
import pandas as pd
import pytest

from dashboard.chart_utils import finite_chart_frame, finite_chart_series


@pytest.mark.parametrize(
    ("frame", "expected_rows"),
    [
        (pd.DataFrame(columns=["date", "value"]), 0),
        (pd.DataFrame({"date": ["2026-01-01"], "value": [4.0]}), 1),
        (pd.DataFrame({"date": ["2026-01-01", "2026-01-02"], "value": [4.0, 4.0]}), 2),
        (pd.DataFrame({"date": ["2026-01-01", "2026-01-02"], "value": [4.0, np.nan]}), 1),
        (pd.DataFrame({"date": ["2026-01-01", "2026-01-02"], "value": [4.0, np.inf]}), 1),
    ],
)
def test_finite_chart_frame_handles_empty_sparse_and_nonfinite_rows(frame, expected_rows):
    result = finite_chart_frame(frame, ("value",))
    assert len(result) == expected_rows
    assert np.isfinite(result["value"].to_numpy(dtype=float)).all()


def test_finite_chart_frame_does_not_mutate_source():
    source = pd.DataFrame({"value": [1.0, np.nan]})
    finite_chart_frame(source, ("value",))
    assert source["value"].isna().any()


def test_finite_chart_frame_reports_missing_plot_columns():
    with pytest.raises(ValueError, match="missing columns"):
        finite_chart_frame(pd.DataFrame({"value": [1]}), ("missing",))


def test_finite_chart_series_preserves_only_finite_numeric_values():
    series = pd.Series(["1.5", np.nan, np.inf, "-2"])
    result = finite_chart_series(series)
    assert result.tolist() == [1.5, -2.0]
