"""Browser tests: accessibility (axe-core, WCAG 2.1 A/AA + best practices) and key user journeys."""
import pytest

from .conftest import sign_in

pytest.importorskip("playwright")
axe_module = pytest.importorskip("axe_playwright_python.sync_playwright")

AXE_TAGS = {"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]}}


def assert_accessible(pg, label: str) -> None:
    violations = axe_module.Axe().run(pg, options=AXE_TAGS).response["violations"]
    summary = [f"{v['id']} ({v['impact']}): {n['target'][0]}" for v in violations for n in v["nodes"]]
    assert not summary, f"accessibility violations on {label}:\n" + "\n".join(summary)


def set_theme(pg, theme: str) -> None:
    pg.add_init_script(f"localStorage.setItem('sh-theme', '{theme}')")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_login_page_is_accessible(page, theme):
    set_theme(page, theme)
    page.goto(page.base_url + "/")
    assert_accessible(page, f"login/{theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_admin_screens_are_accessible(page, theme):
    set_theme(page, theme)
    sign_in(page, "admin")
    page.wait_for_selector("canvas")
    assert_accessible(page, f"dashboard/{theme}")

    page.click("#tabs button:nth-child(2)")
    page.select_option("select[aria-label=Medicine]", index=1)
    page.wait_for_selector("canvas")
    assert_accessible(page, f"forecast/{theme}")

    page.click("#tabs button:nth-child(3)")
    page.wait_for_selector("form.card")
    assert_accessible(page, f"entry/{theme}")


def test_staff_facility_view_is_accessible(page):
    sign_in(page, "staff1")
    page.wait_for_selector("canvas")
    assert_accessible(page, "staff facility view")


def test_every_page_has_one_h1_and_main_landmark(page):
    page.goto(page.base_url + "/")
    assert page.locator("main:visible h1").count() == 1
    sign_in(page, "admin")
    assert page.locator("h1").count() >= 1
    assert page.locator("main:visible").count() == 1


def test_keyboard_users_can_skip_navigation(page):
    sign_in(page, "admin")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip-link"
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main"


def test_switching_tabs_moves_focus_to_content_and_marks_current_tab(page):
    sign_in(page, "admin")
    page.click("#tabs button:nth-child(2)")
    page.wait_for_selector("select[aria-label=Medicine]")
    assert page.evaluate("document.activeElement.id") == "main"
    assert page.locator('#tabs button[aria-current="page"]').count() == 1
    assert page.locator("#tabs button[aria-selected]").count() == 0  # invalid ARIA on a plain button


def test_charts_offer_their_data_as_a_table(page):
    sign_in(page, "admin")
    page.wait_for_selector("details.data-table")
    page.click("details.data-table summary")
    assert page.locator("details.data-table tbody tr").count() == 14


def test_language_switch_updates_page_language_and_labels(page):
    sign_in(page, "admin")
    page.select_option("#lang", "hi")
    page.wait_for_function("document.documentElement.lang === 'hi'")
    assert "जिला" in page.locator("#tabs").inner_text()
    assert page.locator("h1.sr-only").inner_text() == "जिला डैशबोर्ड"


def test_dashboard_shows_flagged_centres_and_transfers(page):
    sign_in(page, "admin")
    assert page.locator(".flag").count() >= 1
    assert page.locator(".transfer").count() >= 1
    assert not page.js_errors


def test_staff_sees_only_own_facility_tabs_and_can_report(page):
    sign_in(page, "staff1")
    assert "District dashboard" not in page.locator("#tabs").inner_text()
    page.click("#tabs button:nth-child(2)")
    page.wait_for_selector("form.card")
    page.fill("input[name=patients]", "77")
    page.locator("form.card").nth(1).locator("button").click()
    page.wait_for_selector("#notice[role=status]:not(:empty)")
    assert page.locator("#notice").inner_text() == "Saved."
    assert not page.js_errors


def test_validation_errors_are_announced_as_alerts(page):
    sign_in(page, "staff1")
    page.click("#tabs button:nth-child(2)")
    page.wait_for_selector("form.card")
    page.fill("input[name=total]", "5")
    page.fill("input[name=occupied]", "9")  # more occupied than total -> server rejects
    page.locator("form.card").nth(2).locator("button").click()
    page.wait_for_selector("#notice[role=alert]:not(:empty)")


def test_wrong_password_shows_error_and_stays_on_login(page):
    page.goto(page.base_url + "/")
    page.fill("input[name=username]", "admin")
    page.fill("input[name=password]", "definitely-wrong")
    page.click("button.primary")
    page.wait_for_function("document.getElementById('login-error').textContent.length > 0")
    assert page.locator("#login-view").is_visible()
