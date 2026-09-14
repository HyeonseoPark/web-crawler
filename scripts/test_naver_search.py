from pathlib import Path
import pytest
from scripts.naver_search import classify_place, search_blogs, collect, SELECTORS


def test_location_evidence():
    row = {"title": "아소토 베이커리", "summary": "서울 중구 수표로10길 19"}
    assert classify_place(row, "아소토베이커리", "수표로10길 19") == "address_in_snippet"
    row["summary"] = "을지로 맛집"
    assert classify_place(row, "아소토베이커리", "수표로10길 19") == "needs_location_check"
    row["title"] = "다른 빵집"
    assert classify_place(row, "아소토베이커리", "수표로10길 19") == "name_not_found"


def test_bounds():
    for query, limit in [("", 50), ("test", 0), ("test", 51)]:
        with pytest.raises(ValueError):
            search_blogs(query, limit=limit)


def test_browser_search_routes_to_reusable_transport(monkeypatch):
    from scripts import naver_search
    calls = []
    monkeypatch.setattr(naver_search.browser_job, "crawl", lambda *a, **kw: calls.append(kw) or ([], "empty"))
    search_blogs("아소토베이커리 중구", permission=True)
    assert calls[0]["search_query"] == "아소토베이커리 중구"
    assert calls[0]["collector"] is collect


def test_dom_and_dedup():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        if not Path(pw.chromium.executable_path).exists():
            pytest.skip("Chromium required for offline DOM test")
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.abort())
            fixture = Path(__file__).resolve().parents[1] / "jobs/naver_search/fixture.html"
            page.set_content(fixture.read_text(encoding="utf-8"))
            rows, reason = collect(page, 2, SELECTORS)
            assert len(rows) == 2 and reason == "limit_reached"
            assert rows[0]["author"] == "테스트"
            assert rows[1]["author"] == ""
        finally:
            browser.close()
