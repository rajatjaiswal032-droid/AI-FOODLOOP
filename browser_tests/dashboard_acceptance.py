from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SECRET = "browser-test-secret-key-with-at-least-32-bytes"
ADMIN_USERNAME = "browser-admin@example.com"
ADMIN_PASSWORD = "BrowserAdminPassword!123"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(page: Page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded")
    expect(page.get_by_role("textbox", name="Username")).to_be_visible(timeout=30_000)


@pytest.fixture
def dashboard_server(tmp_path: Path):
    database_path = tmp_path / "browser.db"
    env = os.environ.copy()
    env.update(
        {
            "FOODLOOP_DATABASE_PATH": str(database_path),
            "FOODLOOP_AUTH_SECRET_KEY": SECRET,
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        }
    )
    bootstrap = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.core.auth import bootstrap_admin; "
                f"bootstrap_admin({ADMIN_USERNAME!r}, {ADMIN_PASSWORD!r})"
            ),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert bootstrap.returncode == 0
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "dashboard/streamlit_app.py",
            "--server.headless",
            "true",
            "--server.port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def test_dashboard_startup_authentication_and_csv_validation(
    dashboard_server: str, tmp_path: Path
):
    valid_csv = tmp_path / "valid.csv"
    valid_csv.write_text(
        "date,meal_name,quantity_prepared,quantity_consumed\n"
        "2026-01-01,Lunch,10,8\n"
        "2026-01-02,Lunch,11,9\n",
        encoding="utf-8",
    )
    invalid_csv = tmp_path / "invalid.csv"
    invalid_csv.write_text(
        "date,meal_name,quantity_prepared\n2026-01-01,Lunch,10\n",
        encoding="utf-8",
    )

    with sync_playwright() as playwright_context:
        browser = playwright_context.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            _wait_for_server(page, dashboard_server)
            page.get_by_role("textbox", name="Username").fill("wrong@example.com")
            page.get_by_role("textbox", name="Password").fill("wrong-password")
            page.get_by_role("button", name="Sign in").click()
            expect(page.get_by_text("Invalid credentials.")).to_be_visible(timeout=10_000)

            page.get_by_role("textbox", name="Username").fill(ADMIN_USERNAME)
            page.get_by_role("textbox", name="Password").fill(ADMIN_PASSWORD)
            page.get_by_role("button", name="Sign in").click()
            expect(page.get_by_text("Data-quality summary")).to_be_visible(timeout=15_000)

            uploader = page.locator('input[type="file"]')
            uploader.set_input_files(str(valid_csv))
            expect(page.get_by_text("Forecast readiness:")).to_be_visible(timeout=15_000)
            expect(page.get_by_text("Historical records")).to_be_visible(timeout=15_000)

            uploader.set_input_files(str(invalid_csv))
            expect(page.get_by_text("Forecast readiness: NOT READY")).to_be_visible(
                timeout=15_000
            )
            expect(page.get_by_text("Missing required columns: quantity_consumed.")).to_be_visible(
                timeout=15_000
            )
        finally:
            browser.close()
