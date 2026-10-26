"""Safe HTML table rendering helpers for the Streamlit dashboard.

The dashboard previously relied on ``st.dataframe``, which routes data through
PyArrow. On Windows systems where Application Control blocks PyArrow this
prevented the dashboard from rendering any tabular data. This module provides a
small, dependency-light renderer that converts tabular data into an HTML table
without PyArrow and without executing any untrusted content.
"""

from __future__ import annotations

import html
from typing import Any, Iterable

import pandas as pd


def _to_frame(data: Any) -> pd.DataFrame:
    """Coerce supported tabular inputs into a DataFrame copy."""
    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        return data.copy()
    if isinstance(data, (list, tuple)):
        if not data:
            return pd.DataFrame()
        return pd.DataFrame(list(data))
    if isinstance(data, dict):
        return pd.DataFrame([data])
    try:
        return pd.DataFrame(data)
    except (ValueError, TypeError):
        return pd.DataFrame()


def _format_cell(value: Any) -> str:
    """Render a single cell value as safe, escaped text."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return f"{value:,.0f}"
        return f"{value:,.6g}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def dataframe_to_html_table(
    data: Any,
    *,
    columns: Iterable[str] | None = None,
    empty_message: str = "No data available.",
    max_rows: int | None = None,
) -> str:
    """Convert tabular data into a safe, escaped HTML table string."""
    frame = _to_frame(data)
    if columns is not None:
        available = [column for column in columns if column in frame.columns]
        if available:
            frame = frame.loc[:, available]
    if frame.empty:
        return (
            "<div class='foodloop-table foodloop-table--empty'>"
            f"<p>{html.escape(empty_message)}</p>"
            "</div>"
        )

    if max_rows is not None and len(frame) > max_rows:
        frame = frame.head(max_rows)

    header_cells = "".join(
        f"<th scope='col'>{html.escape(str(column))}</th>"
        for column in frame.columns
    )
    body_rows = []
    for _, row in frame.iterrows():
        cells = "".join(
            f"<td>{html.escape(_format_cell(value))}</td>"
            for value in row.tolist()
        )
        body_rows.append(f"<tr>{cells}</tr>")
    body = "".join(body_rows)

    return (
        "<div class='foodloop-table-wrap'>"
        "<table class='foodloop-table'>"
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
    )


def render_table(
    data: Any,
    *,
    columns: Iterable[str] | None = None,
    empty_message: str = "No data available.",
    max_rows: int | None = None,
) -> None:
    """Render tabular data in Streamlit without using PyArrow."""
    import streamlit as st

    st.markdown(
        dataframe_to_html_table(
            data, columns=columns, empty_message=empty_message, max_rows=max_rows
        ),
        unsafe_allow_html=True,
    )
