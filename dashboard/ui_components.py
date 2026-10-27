"""Reusable Streamlit UI feedback helpers for AI FOODLOOP."""

from __future__ import annotations

import contextlib
from typing import Iterator


def show_success(message: str) -> None:
    import streamlit as st

    st.success(message)


def show_error(message: str) -> None:
    import streamlit as st

    st.error(message)


def show_info(message: str) -> None:
    import streamlit as st

    st.info(message)


def show_warning(message: str) -> None:
    import streamlit as st

    st.warning(message)


def show_empty(message: str, *, hint: str | None = None) -> None:
    import streamlit as st

    st.info(message)
    if hint:
        st.caption(hint)


@contextlib.contextmanager
def loading(message: str = "Loading...") -> Iterator[None]:
    import streamlit as st

    with st.spinner(message):
        yield
