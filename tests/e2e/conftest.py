"""Shared fixtures for browser tests: a real server on a free port plus a Playwright browser.

These tests are skipped automatically when Playwright (or a browser) is not installed:
    pip install playwright axe-playwright-python && playwright install chromium
"""
import socket
import threading
import time
from datetime import date

import pytest

from smarthealth import config
from smarthealth.app import create_app
from smarthealth.seed import seed

PASSWORD = "E2e-Passw0rd!x"
TODAY = date.today()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def base_url(tmp_path_factory):
    uvicorn = pytest.importorskip("uvicorn")
    config.PBKDF2_ITERATIONS = 1000
    # A file database (not :memory:) so the browser's parallel requests each get their own connection.
    db_file = tmp_path_factory.mktemp("e2e") / "e2e.db"
    app = create_app(f"sqlite:///{db_file.as_posix()}", secret="e2e-secret", clock=lambda: TODAY)
    with app.state.session_factory() as db:
        seed(db, TODAY, password=PASSWORD)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "test server did not start"
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        for launch in (lambda: playwright.chromium.launch(),
                       lambda: playwright.chromium.launch(channel="msedge"),
                       lambda: playwright.chromium.launch(channel="chrome")):
            try:
                instance = launch()
                break
            except Exception as error:  # noqa: BLE001 - fall through to the next browser flavour
                print(f"browser launch failed, trying next: {error}")
        else:
            pytest.skip("no Playwright browser available")
        yield instance
        instance.close()


@pytest.fixture()
def page(browser, base_url):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = context.new_page()
    pg.base_url = base_url
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.js_errors = errors
    yield pg
    context.close()


def sign_in(pg, username: str) -> None:
    pg.goto(pg.base_url + "/")
    pg.fill("input[name=username]", username)
    pg.fill("input[name=password]", PASSWORD)
    pg.click("button.primary")
    pg.wait_for_selector(".kpis")
