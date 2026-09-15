"""Offline contracts; synthetic HTML is intentionally not a live Naver capture."""
import argparse
import csv
from pathlib import Path

import pytest

from jobs.naver_map.crawl_script import (
    AD_HOST_SUFFIXES, DEFAULT_SELECTORS, EXTRACT_JS, FIELDS, LOAD_MORE, canonical_blog_url, collect, crawl,
    main, merge_rows, parse_args, place_id, robots_delay, write_results,
)


@pytest.mark.parametrize("value", ["1141254769", "https://map.naver.com/p/entry/place/1141254769",
    "https://pcmap.place.naver.com/restaurant/1141254769/review/ugc"])
def test_place_id(value):
    assert place_id(value) == "1141254769"


@pytest.mark.parametrize("value", ["https://evil.invalid/place/123", "javascript:123", "-1"])
def test_bad_place(value):
    with pytest.raises(argparse.ArgumentTypeError):
        place_id(value)


def test_defaults_and_limit():
    assert parse_args([]).limit == 50
    for limit in ("0", "51", "-1"):
        with pytest.raises(SystemExit):
            parse_args(["--limit", limit])


def test_url_normalization_and_profile_exclusion():
    assert canonical_blog_url("https://m.blog.naver.com/writer/123?x=1") == "https://blog.naver.com/writer/123"
    assert canonical_blog_url("https://blog.naver.com/PostView.naver?logNo=123&blogId=writer") == "https://blog.naver.com/writer/123"
    for url in ("https://blog.naver.com/writer", "https://blog.naver.com.evil.invalid/a/123"):
        assert canonical_blog_url(url) == ""


def test_dedup_limit_and_missing_fields():
    rows = {}
    merge_rows(rows, [{"blog_url": f"https://blog.naver.com/a/{n}", "title": f"후기 {n}"} for n in range(60)], 50)
    assert len(rows) == 50
    merge_rows(rows, [{"blog_url": "https://m.blog.naver.com/a/0", "title": "중복", "author": "A"}], 50)
    assert rows["https://blog.naver.com/a/0"]["author"] == "A"
    assert rows["https://blog.naver.com/a/0"]["title"] == "후기 0"
    assert rows["https://blog.naver.com/a/0"]["published_at"] == ""


@pytest.mark.parametrize("status,body", [(403, ""), (429, ""), (503, ""), (302, ""),
    (200, "<html>challenge</html>"), (200, "User-agent: *\nDisallow: /"),
    (200, "User-agent: *\nDisallow: /restaurant/")])
def test_robots_fails_closed(status, body):
    with pytest.raises(PermissionError):
        robots_delay(status, body, "https://pcmap.place.naver.com/restaurant/123")


@pytest.mark.parametrize("status,body", [(403, ""), (200, "<html>challenge</html>"),
    (200, "User-agent: *\nDisallow: /")])
def test_ignore_robots_is_explicit_opt_in(status, body):
    url = "https://pcmap.place.naver.com/restaurant/123"
    assert robots_delay(status, body, url, ignore_robots=True) == 1
    # crawl-delay 는 금지를 무시해도 지킨다
    assert robots_delay(200, "User-agent: *\nDisallow: /\nCrawl-delay: 4", url, ignore_robots=True) == 4


def test_robots_delay_and_missing_file():
    assert robots_delay(404, "", "https://example.invalid/") == 1
    assert robots_delay(200, "User-agent: *\nAllow: /\nCrawl-delay: 5", "https://example.invalid/") == 5


def test_permission_stops_before_browser():
    with pytest.raises(PermissionError):
        crawl("1141254769", 50, DEFAULT_SELECTORS)


def test_csv_bom_quotes_formula_and_preserves_existing(tmp_path):
    rows = [{key: "" for key in FIELDS}]
    rows[0].update(blog_url="https://blog.naver.com/a/1", title='한글, "제목"', summary="=1+1")
    path = write_results(rows, tmp_path, "limit_reached")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        result = list(csv.DictReader(handle))
    assert result[0]["title"] == rows[0]["title"]
    assert result[0]["summary"] == "'=1+1"
    original = path.read_bytes()
    assert write_results([], tmp_path, "empty") is None
    with pytest.raises(FileExistsError):
        write_results(rows, tmp_path, "again")
    assert path.read_bytes() == original


@pytest.fixture(scope="session")
def browser_available():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        # Complete driver initialization before closing this discovery-only context.
        request = pw.request.new_context()
        request.dispose()
        if not Path(pw.chromium.executable_path).exists():
            pytest.skip("Chromium not installed; run playwright install chromium for offline DOM tests")


@pytest.fixture
def browser_page(browser_available):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())
        yield page
        browser.close()


def test_real_dom_extraction(browser_page):
    fixture = Path(__file__).resolve().parents[1] / "jobs/naver_map/fixtures/reviews.html"
    browser_page.set_content(fixture.read_text(encoding="utf-8"))
    rows = {}
    merge_rows(rows, browser_page.evaluate(EXTRACT_JS, DEFAULT_SELECTORS), 50)
    assert len(rows) == 2
    first = next(iter(rows.values()))
    assert first["author"] == "테스트 작성자 A"
    assert first["published_at"] == "2026-09-01"
    assert first["summary"].startswith("테스트용 요약")


def test_pagination_and_stop(browser_page):
    browser_page.set_content('''<ul><li><a href="https://blog.naver.com/a/1"><h3>One</h3></a></li></ul>
    <button onclick="document.querySelector('ul').insertAdjacentHTML('beforeend',
    '<li><a href=https://blog.naver.com/a/2><h3>Two</h3></a></li>');this.remove()">더보기</button>''')
    rows, reason = collect(browser_page, 2, DEFAULT_SELECTORS)
    assert len(rows) == 2
    assert reason == "limit_reached"


def test_load_more_skips_photo_link(browser_page):
    """실사이트 구조: 그냥 '더보기'는 사진 페이지 링크, 리뷰 추가는 href="#" 인 '펼쳐서 더보기'."""
    browser_page.set_content('''<a href="/restaurant/1/photo" onclick="document.title='wrong';return false">더보기</a>
    <ul><li><a href="https://blog.naver.com/a/1"><h3>One</h3></a></li></ul>
    <a href="#" role="button" onclick="document.querySelector('ul').insertAdjacentHTML('beforeend',
    '<li><a href=https://blog.naver.com/a/2><h3>Two</h3></a></li>');this.remove();return false">펼쳐서 더보기</a>''')
    rows, reason = collect(browser_page, 2, DEFAULT_SELECTORS)
    assert (len(rows), reason) == (2, "limit_reached")
    assert browser_page.title() != "wrong"


def test_load_more_pattern_and_ad_hosts():
    assert LOAD_MORE.match("펼쳐서 더보기") and LOAD_MORE.match("더보기")
    assert not LOAD_MORE.match("사진 더보기")
    assert "nam.veta.naver.com".endswith(AD_HOST_SUFFIXES)
    assert not "pcmap-api.place.naver.com".endswith(AD_HOST_SUFFIXES)


def test_delay_must_be_at_least_one_second():
    assert parse_args(["--delay", "2.5"]).delay == 2.5
    with pytest.raises(SystemExit):
        parse_args(["--delay", "0.2"])


def test_empty_and_captcha_stop(browser_page):
    browser_page.set_content("<body>리뷰 없음</body>")
    assert collect(browser_page, 50, DEFAULT_SELECTORS)[0] == []
    browser_page.set_content("<body>자동입력 방지 CAPTCHA</body>")
    with pytest.raises(PermissionError):
        collect(browser_page, 50, DEFAULT_SELECTORS)


def test_dry_run(tmp_path, browser_available):
    assert main(["--dry-run", "--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / "blog_reviews.demo.csv").exists()
