"""Run creation-selector checks against isolated local Chromium DOM, never X/CDP."""
from pathlib import Path
import time

import pytest
from scripts import x_article as xa


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        if not Path(p.chromium.executable_path).is_file():
            pytest.skip("Install Playwright Chromium for local DOM tests")
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


@pytest.mark.parametrize("label", ["create", "write", "撰写", "Create"])
def test_current_and_legacy_buttons_open_article(page, label):
    page.set_content(f'<main><button aria-label="{label}" onclick="document.body.dataset.clicked=1"><svg></svg></button></main>')
    xa._open_new_article(page)
    assert page.locator("body").get_attribute("data-clicked") == "1"


@pytest.mark.parametrize("html", [
    '<main><p>撰写</p></main>',
    '<nav><button aria-label="create">create</button></nav><main>Articles</main>',
    '<main><button aria-label="create" hidden></button></main>',
    '<main><button aria-label="create" disabled></button></main>',
    '<main><button aria-label="create"></button><button aria-label="write"></button></main>',
    '<main><button aria-label="create post"></button></main>',
])
def test_missing_disabled_or_ambiguous_entry_fails_without_wait(page, html):
    page.set_content(html)
    start = time.monotonic()
    with pytest.raises(xa.ArticleCreateEntryError, match="创建入口异常"):
        xa._article_create_button(page)
    assert time.monotonic() - start < 3


def test_hidden_duplicate_does_not_mask_current_visible_control(page):
    page.set_content('<main><button hidden aria-label="create"></button><button aria-label="create" onclick="document.body.dataset.clicked=1"></button></main>')
    xa._open_new_article(page)
    assert page.locator("body").get_attribute("data-clicked") == "1"


def test_missing_entry_cannot_delete_or_retry_drafts(page, monkeypatch):
    page.set_content('<main><p>Articles</p></main>')
    monkeypatch.setattr(page, "goto", lambda _: None)
    monkeypatch.setattr(page, "wait_for_timeout", lambda _: None)
    calls = []
    monkeypatch.setattr(xa, "_delete_same_title_drafts", lambda *_: calls.append("deleted"))
    with pytest.raises(xa.ArticleCreateEntryError):
        xa.build_draft_with_retry(page, {"title": "Example"}, [], Path("unused.png"))
    assert calls == []


def test_creation_timeout_does_not_trigger_rebuild(monkeypatch):
    calls = []
    class Button:
        def click(self, **kwargs):
            calls.append("clicked")
            raise RuntimeError("Timeout 5000ms exceeded")
    monkeypatch.setattr(xa, "_article_create_button", lambda _: Button())
    monkeypatch.setattr(xa, "build_draft", lambda page, *_: xa._open_new_article(page))
    with pytest.raises(xa.ArticleCreateEntryError, match="不自动重建"):
        xa.build_draft_with_retry(object(), {}, [], Path("unused.png"))
    assert calls == ["clicked"]
