"""네이버 장소 블로그 리뷰 메타데이터 → CSV. 본문 방문·차단 우회 없음."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from output_path import make_result_dir  # noqa: E402
from utils import RateLimiter, detect_pii, detect_softblock  # noqa: E402

FIELDS = ("blog_url", "title", "author", "published_at", "summary")
USER_AGENT = "WebCrawlerNaverMap/1.0 (+https://github.com/HyeonseoPark/web-crawler)"
DEFAULT_SELECTORS = {
    "card": "li",
    "title": "[data-review-title], h3, .title, strong",
    "author": "[data-review-author], .author, .nickname",
    "date": "time, [data-review-date], .date",
    "summary": "[data-review-summary], .summary, .desc, .dsc, p",
}
# Candidate semantic selectors, not a claim of live Naver DOM verification.
EXTRACT_JS = r"""(selectors) => {
  const text = el => el ? el.innerText.trim().replace(/\s+/g, ' ') : '';
  return [...document.querySelectorAll('a[href]')].filter(a => {
    try { return ['blog.naver.com', 'm.blog.naver.com'].includes(new URL(a.href).hostname); }
    catch { return false; }
  }).map(a => {
    const card = a.closest(selectors.card);
    if (!card || !card.getClientRects().length) return null;
    const date = card.querySelector(selectors.date);
    return {
      blog_url: a.href,
      title: text(card.querySelector(selectors.title)) || text(a),
      author: text(card.querySelector(selectors.author)),
      published_at: date ? (date.getAttribute('datetime') || text(date)) : '',
      summary: text(card.querySelector(selectors.summary))
    };
  }).filter(Boolean);
}"""


def place_id(value: str) -> str:
    if re.fullmatch(r"[0-9]+", value):
        return value
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "map.naver.com", "pcmap.place.naver.com", "m.place.naver.com"
    }:
        raise argparse.ArgumentTypeError("네이버 장소 ID 또는 HTTPS 장소 URL을 지정하세요.")
    match = re.search(r"/(?:place|restaurant|cafe|entry/place)/(\d+)(?:/|$)", parsed.path)
    if not match:
        raise argparse.ArgumentTypeError("URL에서 장소 ID를 찾지 못했습니다. 숫자 ID를 사용하세요.")
    return match[1]


def canonical_blog_url(value: str) -> str:
    """프로필 링크는 제외하고 모바일/PC/쿼리형 게시물 URL을 하나로 통합."""
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or parsed.hostname not in {
        "blog.naver.com", "m.blog.naver.com"
    }:
        return ""
    match = re.fullmatch(r"/([A-Za-z0-9_-]+)/(\d+)/?", parsed.path)
    if match:
        return f"https://blog.naver.com/{match[1]}/{match[2]}"
    query = parse_qs(parsed.query)
    blog = query.get("blogId", [""])[0]
    post = query.get("logNo", [""])[0]
    if parsed.path == "/PostView.naver" and re.fullmatch(r"[A-Za-z0-9_-]+", blog) and post.isdigit():
        return f"https://blog.naver.com/{blog}/{post}"
    return ""


def merge_rows(rows: dict[str, dict], candidates: list[dict], limit: int) -> None:
    for item in candidates:
        url = canonical_blog_url(item.get("blog_url", ""))
        title = str(item.get("title") or "").strip()
        if not url or not title:
            continue
        row = {key: str(item.get(key) or "").strip() for key in FIELDS}
        row["blog_url"] = url
        if url in rows:
            for key in FIELDS:
                if not rows[url][key]:
                    rows[url][key] = row[key]
        elif len(rows) < limit:
            rows[url] = row


def robots_delay(status: int, body: str, url: str) -> float:
    """robots 조회 실패/거부는 허용으로 간주하지 않는다."""
    from protego import Protego
    if status in {404, 410}:
        return 1.0
    if status != 200 or "<html" in body.lower():
        raise PermissionError(f"robots.txt 확인 실패 (HTTP {status})")
    policy = Protego.parse(body)
    # A named bot must not sidestep a general prohibition.
    if not all(policy.can_fetch(url, agent) for agent in (USER_AGENT, "*")):
        raise PermissionError("robots.txt가 대상 경로 수집을 금지합니다.")
    return max(1.0, float(policy.crawl_delay(USER_AGENT) or 0), float(policy.crawl_delay("*") or 0))


def check_page(page) -> None:
    if "nid.naver.com" in page.url:
        raise PermissionError("로그인이 필요하여 중단합니다.")
    text = page.locator("body").inner_text()
    # This is rendered text, not raw HTML; short legitimate review lists are valid.
    verdict = detect_softblock(text, status=200, min_size=0)
    if verdict["blocked"] or re.search(
        r"captcha|비정상적인 접근|접근이 제한|자동입력 방지|보안 확인|로그인이 필요", text, re.I
    ):
        raise PermissionError("접근 제한 또는 보안 확인 화면에서 중단합니다.")


def collect(page, limit: int, selectors: dict, max_rounds: int = 20) -> tuple[list[dict], str]:
    rows: dict[str, dict] = {}
    stagnant = 0
    for _ in range(max_rounds):
        check_page(page)
        before = len(rows)
        merge_rows(rows, page.evaluate(EXTRACT_JS, selectors), limit)
        if not rows:
            return [], "no_reviews_or_selector_mismatch"
        if len(rows) >= limit:
            return list(rows.values()), "limit_reached"
        stagnant = stagnant + 1 if len(rows) == before else 0
        if stagnant >= 2:
            return list(rows.values()), "no_new_reviews"
        # Click only an unambiguous visible load-more control; never visit posts.
        more = page.get_by_role("button", name=re.compile(r"^(?:블로그 리뷰\s*)?더보기$"))
        links = page.get_by_role("link", name=re.compile(r"^(?:블로그 리뷰\s*)?더보기$"))
        visible = [loc for group in (more, links) for loc in group.all() if loc.is_visible()]
        if len(visible) == 1:
            visible[0].click()
        else:
            page.locator("a[href*='blog.naver.com']").last.scroll_into_view_if_needed()
            page.mouse.wheel(0, 900)
        page.wait_for_timeout(1500)
    return list(rows.values()), "round_limit"


def crawl(identifier: str, limit: int, selectors: dict, *, permission: bool = False,
          headed: bool = False) -> tuple[list[dict], str]:
    if not permission:
        raise PermissionError(
            "네이버 약관상 자동 수집에는 사전 허락이 필요합니다. 허락받은 경우에만 "
            "--naver-permission을 사용하세요. robots/접근 제한은 계속 준수합니다."
        )
    from playwright.sync_api import sync_playwright
    target = f"https://pcmap.place.naver.com/restaurant/{identifier}/review/ugc"
    with sync_playwright() as pw:
        # No saved login, CDP, stealth, proxy, private API replay, or retry ladder.
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(user_agent=USER_AGENT, service_workers="block")
        request = pw.request.new_context(user_agent=USER_AGENT, timeout=15000)
        policies: dict[str, tuple[int, str]] = {}
        failures: list[str] = []
        limiter = RateLimiter(delay=1.0, max_requests=120)

        def guard(route):
            req = route.request
            if failures:
                route.abort()
                return
            if req.resource_type not in {"document", "xhr", "fetch"}:
                route.continue_()
                return
            try:
                parsed = urlsplit(req.url)
                if parsed.scheme != "https" or not (
                    parsed.hostname == "naver.com" or (parsed.hostname or "").endswith(".naver.com")
                ):
                    route.abort()
                    return
                if parsed.hostname == "nid.naver.com":
                    raise PermissionError("로그인 요청이 감지되었습니다.")
                origin = f"https://{parsed.netloc}"
                if origin not in policies:
                    limiter.wait()
                    response = request.get(origin + "/robots.txt", max_redirects=0)
                    policies[origin] = (response.status, response.text())
                delay = robots_delay(*policies[origin], req.url)
                limiter.delay = max(limiter.delay, delay)
                limiter.wait()
                # Do not allow automatic redirects to an unchecked path/origin.
                response = route.fetch(max_redirects=0, max_retries=0, timeout=15000)
                if response.status >= 300:
                    raise PermissionError(f"HTTP {response.status}: 리다이렉트 또는 오류에서 중단합니다.")
                route.fulfill(response=response)
            except Exception as exc:
                failures.append(str(exc))
                route.abort()

        def response_guard(response):
            if response.request.resource_type in {"document", "xhr", "fetch"} and response.status >= 400:
                failures.append(f"HTTP {response.status}: 수집을 중단합니다.")

        context.route("**/*", guard)
        context.on("response", response_guard)
        page = context.new_page()
        page.set_default_timeout(15000)
        try:
            page.goto(target, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            if failures:
                raise PermissionError(failures[0])
            rows, reason = collect(page, limit, selectors)
            if failures:
                raise PermissionError(failures[0])
            return rows, reason
        except Exception:
            if failures:
                raise PermissionError(failures[0]) from None
            raise
        finally:
            request.dispose()
            context.close()
            browser.close()


def write_results(rows: list[dict], destination: Path, reason: str, *, dry_run: bool = False):
    if not rows:
        return None
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / ("blog_reviews.demo.csv" if dry_run else "blog_reviews.csv")
    # Exclusive creation prevents failed/repeated runs from overwriting earlier results.
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "'" + row[k] if row[k].lstrip().startswith(("=", "+", "-", "@")) else row[k]
                             for k in FIELDS})
    report = {"collected": len(rows), "stop_reason": reason, "dry_run": dry_run,
              "missing": {k: sum(not row[k] for row in rows) for k in FIELDS}}
    print(json.dumps(report, ensure_ascii=False))
    for warning in detect_pii(rows):
        print(f"[PII 경고] {warning}")
    return path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--place", type=place_id, default="1141254769", help="장소 ID 또는 네이버지도 URL")
    parser.add_argument("--limit", type=int, default=50, help="수집 상한 1~50 (기본 50)")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--selectors", type=Path, help="DOM 변경 시 카드/필드 선택자 JSON")
    parser.add_argument("--naver-permission", action="store_true", help="네이버의 자동 수집 사전 허락을 받은 경우에만 지정")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="합성 HTML로 검증, 외부 네트워크 접근 없음")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 50:
        parser.error("--limit은 1~50이어야 합니다.")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        selectors = DEFAULT_SELECTORS.copy()
        if args.selectors:
            custom = json.loads(args.selectors.read_text(encoding="utf-8"))
            if not isinstance(custom, dict) or set(custom) - set(selectors) or not all(
                isinstance(v, str) and v.strip() for v in custom.values()
            ):
                raise ValueError("selectors는 card/title/author/date/summary 문자열 매핑이어야 합니다.")
            selectors.update(custom)
        if args.dry_run:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page()
                page.route("**/*", lambda route: route.abort())
                page.set_content((Path(__file__).parent / "fixtures" / "reviews.html").read_text(encoding="utf-8"))
                rows = {}
                merge_rows(rows, page.evaluate(EXTRACT_JS, selectors), args.limit)
                rows, reason = list(rows.values()), "synthetic_fixture"
                browser.close()
        else:
            rows, reason = crawl(args.place, args.limit, selectors,
                                 permission=args.naver_permission, headed=args.headed)
        if not rows:
            print(f"[STOP] 0건: {reason}. 결과를 저장하지 않았습니다.")
            return 4
        destination = args.output_dir or make_result_dir(f"네이버지도_{args.place}")
        path = write_results(rows, destination, reason, dry_run=args.dry_run)
        print(f"CSV: {path}")
        return 0
    except PermissionError as exc:
        print(f"[BLOCKED] {exc}")
        return 3
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
