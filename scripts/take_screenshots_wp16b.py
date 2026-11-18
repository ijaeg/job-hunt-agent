"""Takes the seven WP-16b README images (screenshots + one LangSmith trace page).

Based on the Sprint 2 template (``~/projects/turing-college/take_screenshots.py``):
same helper shapes (``click_sidebar_button``/``open_expander``/``hide_popups``/``shot``),
adapted to this app's multipage sidebar nav and chat/shortlist layout.

Start the app first, pointed at its own throwaway database so nothing lands in
Ingo's real data (Addendum, WP-16b step 3):

    DB_PATH=data/screenshots_wp16b.sqlite uv run streamlit run app.py \\
        --server.port 8511 --server.headless true

Then, from the project root:

    uv run --with playwright python scripts/take_screenshots_wp16b.py

The first time, Playwright needs its browser:

    uv run --with playwright playwright install chromium

Demo mode is switched on from the Developer settings page (not relied on from
auto-detection, since the real BA API may be reachable from this machine) before
anything else happens. The script then drives one continuous thread for user
"alex": S1 (the W3 wording chosen in Step 1/Addendum 1) -> approve a
``save_to_tracker`` -> approve a ``remember`` -> visits Tracker, Memory and
Developer settings. This makes real OpenRouter calls (a few cents) against the
demo fixture set (CLAUDE.md invariant 6).

The eighth image, the public S1 trace page, is a LangSmith URL, not this app -
captured separately by navigating there directly (no login needed, spec §9.5,
D-18, Addendum 1).

Writes (PNG, ``docs/images/`` by default):
    chat-shortlist.png       shortlist after S1, one card with evidence and gaps
    agent-steps.png          "Agent steps" expander of that answer, both searches
    approval-dialog.png      S3's save_to_tracker proposal (Approve/Edit/Reject)
    tracker.png              Tracker page after approving S3
    memory.png               Memory page after approving a remembered preference
    developer-settings.png   model, tool toggles, session cost
    langsmith-s1-trace.png   the public S1 share link, tool-call tree visible

Related: spec §3.2, §9.5, FR-07, FR-10 AC2, FR-11, FR-15 AC3, FR-17 AC1,
FR-18 AC1-AC2, D-10, D-12, D-18, WP-16b
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Addendum 1 to WP-16b's prompt (2026-11-18): the only one of the three Step 1
#: wordings whose max elapsed time stayed inside the 60s NFR-03 budget on every run.
S1_QUERY = "Find Softwareentwickler jobs in München from the last 4 weeks, no temp agencies."
S3_QUERY = "Save #1 and remind me in a week."
REMEMBER_QUERY = "Please remember that I prefer hybrid roles."

TURN_TIMEOUT_MS = 180_000  # S1 has run up to ~65s in Step 1's measurement; ample margin
APPROVAL_TIMEOUT_MS = 60_000


def click_sidebar_nav(page: Page, label: str) -> None:
    """Client-side navigation via the sidebar's page links - keeps the Streamlit
    session (and so demo mode, the thread id, session cost) alive, unlike a
    hard ``page.goto()`` to a different route, which starts a fresh session."""
    page.locator('[data-testid="stSidebarNavLink"]', has_text=label).click()
    page.wait_for_timeout(1500)


def open_expander(page: Page, title: str, root: str = "body", index: int = 0) -> None:
    """Opens the ``index``-th expander whose title starts with ``title`` (if closed)."""
    expander = (
        page.locator(f'{root} [data-testid="stExpander"]')
        .filter(has=page.locator("summary", has_text=title))
        .nth(index)
    )
    details = expander.locator("details")
    if details.count() == 0 or details.get_attribute("open") is None:
        expander.locator("summary").click()
        page.wait_for_timeout(800)


def scroll_main_to_top(page: Page) -> None:
    page.evaluate(
        """() => {
            window.scrollTo(0, 0);
            const side = document.querySelector('[data-testid="stSidebar"]');
            document.querySelectorAll('*').forEach(e => {
                if (e.scrollTop > 0 && !(side && side.contains(e))) e.scrollTop = 0;
            });
        }"""
    )
    page.wait_for_timeout(500)


#: Text of Streamlit's own pop-ups that do not belong in the screenshots.
POPUP_TEXTS = ("Help agents write better apps",)


def hide_popups(page: Page) -> None:
    """Hides floating Streamlit notices (same trick as the Sprint 2 template):
    for the innermost element containing one of POPUP_TEXTS, hides the largest
    ancestor that contains no part of the app itself."""
    page.evaluate(
        """(texts) => {
            const app = '[data-testid="stMain"], [data-testid="stSidebar"], '
                + '[data-testid="stChatInput"], [data-testid="stHeader"], section.main';
            const has = (e) => texts.some(t => (e.innerText || '').includes(t));
            for (const el of document.querySelectorAll('body *')) {
                if (!has(el) || [...el.children].some(has)) continue;
                if (el.closest(app)) continue;
                let target = el;
                while (target.parentElement && target.parentElement !== document.body
                       && !target.parentElement.querySelector(app)) {
                    target = target.parentElement;
                }
                target.style.display = 'none';
            }
        }""",
        list(POPUP_TEXTS),
    )


def shot(page: Page, out: Path, name: str, *, full_page: bool = False) -> None:
    """Saves one screenshot, without Streamlit pop-ups."""
    hide_popups(page)
    page.wait_for_timeout(300)
    path = out / name
    page.screenshot(path=str(path), full_page=full_page)
    print(f"saved {path}")


def enable_demo_mode(page: Page) -> None:
    """Switches Demo mode on from Developer settings - not relied on from
    auto-detection (the real BA API may be reachable from this machine)."""
    click_sidebar_nav(page, "Developer settings")
    toggles = page.locator('[data-testid="stCheckbox"]')
    demo_toggle = toggles.filter(has_text="Demo mode")
    checkbox = demo_toggle.locator("input")
    if not checkbox.is_checked():
        demo_toggle.click()
        page.wait_for_timeout(1500)
    assert checkbox.is_checked(), "Demo mode toggle did not turn on"


def send_message(page: Page, text: str) -> None:
    box = page.locator('[data-testid="stChatInputTextArea"]')
    box.fill(text)
    box.press("Enter")
    page.wait_for_timeout(500)


def wait_for_turn(page: Page, prior_agent_steps: int) -> None:
    """Waits until one more "Agent steps" expander has appeared (the turn finished)."""
    page.locator('[data-testid="stExpander"]').filter(
        has=page.locator("summary", has_text="Agent steps")
    ).nth(prior_agent_steps).wait_for(state="attached", timeout=TURN_TIMEOUT_MS)
    page.wait_for_timeout(1000)


def agent_steps_count(page: Page) -> int:
    return (
        page.locator('[data-testid="stExpander"]')
        .filter(has=page.locator("summary", has_text="Agent steps"))
        .count()
    )


def wait_for_approval(page: Page) -> None:
    page.get_by_text("Approval needed:", exact=False).first.wait_for(timeout=APPROVAL_TIMEOUT_MS)
    page.wait_for_timeout(500)


def click_approve(page: Page) -> None:
    page.get_by_role("button", name="Approve").first.click()
    page.wait_for_timeout(500)


def take_app_screenshots(
    page: Page, url: str, out: Path, *, agent_steps_only: bool = False
) -> None:
    page.goto(f"{url}/?user=alex")
    page.wait_for_selector('[data-testid="stSidebar"]', timeout=30_000)
    page.wait_for_timeout(2000)

    enable_demo_mode(page)
    click_sidebar_nav(page, "app")
    page.wait_for_selector("text=Demo data", timeout=10_000)

    # S1 (W3 wording) -> shortlist + agent steps
    steps_before = agent_steps_count(page)
    send_message(page, S1_QUERY)
    wait_for_turn(page, steps_before)
    scroll_main_to_top(page)

    if agent_steps_only:
        open_expander(page, "Agent steps (")
        shot(page, out, "agent-steps.png")
        return

    open_expander(page, "Gaps")
    shot(page, out, "chat-shortlist.png")

    open_expander(page, "Agent steps (")
    shot(page, out, "agent-steps.png")

    # S3: save -> approval dialog -> approve -> Tracker
    send_message(page, S3_QUERY)
    wait_for_approval(page)
    shot(page, out, "approval-dialog.png")
    click_approve(page)
    page.wait_for_timeout(2000)

    click_sidebar_nav(page, "Tracker")
    shot(page, out, "tracker.png")
    click_sidebar_nav(page, "app")
    page.wait_for_timeout(1000)

    # remember a preference -> approve -> Memory
    steps_before = agent_steps_count(page)
    send_message(page, REMEMBER_QUERY)
    wait_for_approval(page)
    click_approve(page)
    page.wait_for_timeout(2000)

    click_sidebar_nav(page, "Memory")
    shot(page, out, "memory.png")

    # Developer settings: model, tool toggles, session cost (now non-zero)
    click_sidebar_nav(page, "Developer settings")
    shot(page, out, "developer-settings.png", full_page=True)


def take_langsmith_screenshot(page: Page, out: Path) -> None:
    results_path = PROJECT_ROOT / "eval" / "results" / "langsmith_wp16b.json"
    data = json.loads(results_path.read_text(encoding="utf-8"))
    s1_run = next(r for r in data["runs"] if r["scenario"] == "S1")
    page.goto(s1_run["share_url"])
    page.wait_for_timeout(5000)
    shot(page, out, "langsmith-s1-trace.png")


def main() -> int:
    parser = argparse.ArgumentParser(description="WP-16b README images (spec §3.2, §9.5).")
    parser.add_argument("--url", default="http://localhost:8511")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "docs" / "images")
    parser.add_argument("--show", action="store_true", help="show the browser window")
    parser.add_argument(
        "--skip-app",
        action="store_true",
        help="Only (re-)take the LangSmith trace screenshot.",
    )
    parser.add_argument(
        "--agent-steps-only",
        action="store_true",
        help="Only (re-)take agent-steps.png (S1, no S3/remember/tracker/memory/dev "
        "settings) - cheaper than a full run when just that image needs a retake.",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.show)
        page = browser.new_page(viewport={"width": 1400, "height": 1200})

        if args.agent_steps_only:
            take_app_screenshots(page, args.url, args.out, agent_steps_only=True)
            browser.close()
            return 0

        if not args.skip_app:
            take_app_screenshots(page, args.url, args.out)

        take_langsmith_screenshot(page, args.out)

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
