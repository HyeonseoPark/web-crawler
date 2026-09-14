"""Reusable Playwright Naver blog search. No API or API keys."""
import re
from jobs.naver_map import crawl_script as browser_job

SELECTORS = {
    "card": ".view_wrap, .api_ani_send, [data-search-card]",
    "title": ".title_link, .title_area, [data-title]",
    "author": ".user_info .name, [data-author]",
    "date": ".sub_time, .user_info .date, [data-date]",
    "summary": ".dsc_link, .dsc_txt, [data-summary]",
}
EXTRACT_JS = r"""s => [...document.querySelectorAll(s.card)].map(card => {
 const txt = key => card.querySelector(s[key])?.innerText.trim() || '';
 const title = card.querySelector(s.title);
 const link = title?.matches('a[href]') ? title : title?.querySelector('a[href]');
 return {blog_url: link?.href || '', title: txt('title'), author: txt('author'),
 published_at: txt('date'), summary: txt('summary')};
})"""


def collect(page, limit=50, selectors=None):
    rows, stagnant = {}, 0
    for _ in range(20):
        browser_job.check_page(page)
        before = len(rows)
        # This job intentionally selects only Naver blog post links.
        browser_job.merge_rows(rows, page.evaluate(EXTRACT_JS, selectors or SELECTORS), limit)
        if not rows:
            return [], "empty_or_changed_dom"
        if len(rows) >= limit:
            return list(rows.values()), "limit_reached"
        stagnant = stagnant + 1 if len(rows) == before else 0
        if stagnant >= 2:
            return list(rows.values()), "no_new_results"
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(1500)
    return list(rows.values()), "round_limit"


def search_blogs(query, *, limit=50, selectors=None, permission=False, headed=False):
    if not query.strip() or not 1 <= limit <= 50:
        raise ValueError("검색어와 limit(1~50)을 확인하세요.")
    return browser_job.crawl("", limit, selectors or SELECTORS, permission=permission,
                             headed=headed, search_query=query, collector=collect)


def classify_place(row, name, address):
    compact = lambda value: re.sub(r"\s+", "", value).casefold()
    text = compact(row["title"] + " " + row["summary"])
    if compact(name) not in text:
        return "name_not_found"
    if compact(address) in text:
        return "address_in_snippet"
    return "needs_location_check"
