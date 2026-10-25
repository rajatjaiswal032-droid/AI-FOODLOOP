from __future__ import annotations

import numpy as np
import pandas as pd


def finite_chart_frame(
    frame: pd.DataFrame, numeric_columns: tuple[str, ...]
) -> pd.DataFrame:
    """Return only chart rows with finite values in every plotted column."""
    if frame.empty:
        return frame.copy()
    missing = [column for column in numeric_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Chart data is missing columns: {', '.join(missing)}.")
    numeric = frame.loc[:, list(numeric_columns)].apply(pd.to_numeric, errors="coerce")
    valid = numeric.notna().all(axis=1) & np.isfinite(numeric).all(axis=1)
    return frame.loc[valid].copy()


def finite_chart_series(series: pd.Series) -> pd.Series:
    """Return a numeric chart series without NaN or infinite points."""
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.notna() & np.isfinite(numeric)
    return numeric.loc[valid]
