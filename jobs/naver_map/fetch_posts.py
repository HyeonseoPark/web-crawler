"""blog_reviews.csv 의 네이버 블로그 글 본문 → posts.json (로컬 저장 전용).

- 모바일 글 페이지(m.blog.naver.com/<id>/<logNo>)를 사다리 2단(plain_session)으로 받는다.
- 각 호스트의 robots.txt 를 먼저 보고, 이 도구의 User-Agent 와 `*` 모두 허용한 경로만 받는다.
- 본문 텍스트는 파일에만 쓰고 **화면에는 출력하지 않는다** (건수·글자 수만 출력).
  blog.naver.com robots.txt 가 AI 학습·RAG 목적의 봇 접근을 금지하므로, 이 파일은
  AI 에게 넘기지 말고 `judge_tasty.py`(규칙 기반, AI 없음) 로만 처리한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))
from utils import RateLimiter, check_robots, detect_softblock, plain_session  # noqa: E402
from jobs.naver_map.crawl_script import USER_AGENT, canonical_blog_url  # noqa: E402

# 스마트에디터 ONE → 구 에디터(se2) → 아주 옛 글 순서로 시도한다.
BODY_SELECTORS = (
    ".se-main-container .se-text-paragraph",
    ".se_component_wrap .se_textarea",
    "#viewTypeSelector",
    ".post_ct",
)


def mobile_url(blog_url: str) -> str:
    canonical = canonical_blog_url(blog_url)
    if not canonical:
        raise ValueError(f"네이버 블로그 글 주소가 아닙니다: {blog_url}")
    blog_id, log_no = re.fullmatch(r"https://blog\.naver\.com/([^/]+)/(\d+)", canonical).groups()
    return f"https://m.blog.naver.com/{blog_id}/{log_no}"


def extract_paragraphs(page) -> list[str]:
    for selector in BODY_SELECTORS:
        nodes = page.css(selector)
        lines = [" ".join(str(node.get_all_text(separator=" ", strip=True)).split()) for node in nodes]
        lines = [line for line in lines if line]
        if lines:
            return lines
    return []


def fetch_all(urls: list[str], delay: float, session_factory=plain_session,
              robots=check_robots) -> list[dict]:
    limiter = RateLimiter(delay=max(1.0, delay), max_requests=len(urls) + 5)
    results = []
    robots_cache: dict[tuple[str, str], dict] = {}

    def robots_for(target: str, agent: str) -> dict:
        # 허용 여부는 경로마다 다르지만 모든 글이 /<id>/<logNo> 형태라 호스트+에이전트 단위로 한 번 받는다
        key = (target.split("/")[2], agent)
        if key not in robots_cache:
            robots_cache[key] = robots(target, agent)
        return robots_cache[key]

    with session_factory() as session:
        for index, url in enumerate(urls, 1):
            target = mobile_url(url)
            record = {"index": index, "blog_url": canonical_blog_url(url), "fetched_url": target,
                      "status": None, "paragraphs": [], "error": ""}
            verdicts = [robots_for(target, agent) for agent in (USER_AGENT, "*")]
            if any(v["error"] or not v["allowed"] for v in verdicts):
                record["error"] = "robots.txt 가 허용하지 않거나 확인 실패"
                results.append(record)
                continue
            limiter.delay = max(limiter.delay, *(v["crawl_delay"] or 0 for v in verdicts))
            limiter.wait()
            try:
                page = session.get(target, headers={"User-Agent": USER_AGENT}, timeout=20)
                record["status"] = page.status
                body = str(page.body[:200000], "utf-8", "replace") if isinstance(page.body, bytes) else str(page.body)
                if page.status != 200:
                    record["error"] = f"HTTP {page.status}"
                elif detect_softblock(body, status=page.status, min_size=0)["blocked"]:
                    raise PermissionError("차단/보안 확인 화면이 감지되어 중단합니다.")
                else:
                    record["paragraphs"] = extract_paragraphs(page)
                    if not record["paragraphs"]:
                        record["error"] = "본문 영역을 찾지 못함 (비공개·삭제·구조 변경 가능)"
            except PermissionError:
                raise
            except Exception as exc:  # 한 글 실패로 전체를 멈추지 않는다
                record["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            results.append(record)
            # 본문은 출력하지 않는다 — 숫자만
            chars = sum(len(p) for p in record["paragraphs"])
            print(f"[{index:>2}/{len(urls)}] HTTP {record['status']} 문단 {len(record['paragraphs']):>3} "
                  f"글자 {chars:>6} {record['error']}", flush=True)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="crawl_script.py 가 만든 blog_reviews.csv")
    parser.add_argument("--output-dir", type=Path, required=True, help="posts.json 을 둘 로컬 폴더")
    parser.add_argument("--delay", type=float, default=2.5, help="요청 간 최소 간격(초, 1 이상)")
    args = parser.parse_args(argv)
    if args.delay < 1:
        parser.error("--delay는 1초 이상이어야 합니다.")
    with args.csv_path.open(encoding="utf-8-sig", newline="") as handle:
        urls = [row["blog_url"] for row in csv.DictReader(handle) if row.get("blog_url")]
    if not urls:
        print("[STOP] CSV 에 블로그 주소가 없습니다.")
        return 4
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        results = fetch_all(urls, args.delay)
    except PermissionError as exc:
        print(f"[BLOCKED] {exc}")
        return 3
    path = args.output_dir / "posts.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(bool(r["paragraphs"]) for r in results)
    print(f"본문 확보 {ok}/{len(results)} → {path}")
    return 0 if ok else 4


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
