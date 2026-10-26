import html

import pandas as pd
import pytest

from dashboard.table_utils import dataframe_to_html_table, render_table


def test_empty_frame_renders_empty_state():
    result = dataframe_to_html_table(pd.DataFrame())
    assert "foodloop-table--empty" in result
    assert "No data available." in result


def test_empty_message_is_escaped():
    result = dataframe_to_html_table(None, empty_message="<script>alert(1)</script>")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_headers_and_cells_are_escaped():
    frame = pd.DataFrame({"name": ["<b>x</b>"], "value": [1.5]})
    result = dataframe_to_html_table(frame)
    assert "&lt;b&gt;x&lt;/b&gt;" in result
    assert "<b>" not in result
    assert "<th scope='col'>name</th>" in result
    assert "<td>1.5</td>" in result


def test_columns_subset_is_respected():
    frame = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    result = dataframe_to_html_table(frame, columns=["b", "missing"])
    assert "<th scope='col'>b</th>" in result
    assert "<th scope='col'>a</th>" not in result
    assert "<th scope='col'>c</th>" not in result


def test_none_and_nan_render_as_empty_cells():
    frame = pd.DataFrame({"x": [None, float("nan")]})
    result = dataframe_to_html_table(frame)
    assert "<td></td>" in result


def test_max_rows_limits_output():
    frame = pd.DataFrame({"x": list(range(10))})
    result = dataframe_to_html_table(frame, max_rows=3)
    assert result.count("<tr>") == 4  # header + 3 body rows


def test_list_of_dicts_is_supported():
    result = dataframe_to_html_table([{"a": 1}, {"a": 2}])
    assert result.count("<tr>") == 3  # header + 2 body rows


def test_render_table_calls_streamlit_markdown(monkeypatch):
    import sys

    class FakeSt:
        def __init__(self):
            self.calls = []

        def markdown(self, text, unsafe_allow_html=False):
            self.calls.append((text, unsafe_allow_html))

    fake = FakeSt()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    import dashboard.table_utils as tu

    tu.render_table(pd.DataFrame({"x": [1]}))
    assert len(fake.calls) == 1
    text, unsafe = fake.calls[0]
    assert "<td>1</td>" in text
    assert unsafe is True
