r"""나라장터에서 2026년 공고명에 'AI'가 포함된 입찰공고를 수집한다.

실행(저장소 루트 PowerShell):
    .\.venv\Scripts\python.exe jobs\g2b_ai_2026\crawl_script.py
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from export_excel import export_to_excel  # noqa: E402
from output_path import make_result_dir  # noqa: E402
from utils import detect_pii  # noqa: E402


PROFILE_PATH = REPO_ROOT / "fingerprints" / "g2b_go_kr" / "profile.json"
HOME_URL = "https://www.g2b.go.kr/"
API_URL_PART = "selectBidPbacScrollTypeList.do"
YEAR = 2026
KEYWORD = "AI"
PAGE_SIZE = 100
REQUEST_DELAY_SECONDS = 1.0


def _date_value(year: int, is_start: bool, sample: object) -> object:
    month_day = "0101" if is_start else "1231"
    digits = f"{year}{month_day}"
    if isinstance(sample, int):
        return int(digits)
    sample = str(sample)
    if "." in sample:
        return f"{digits[:4]}.{digits[4:6]}.{digits[6:]}"
    if "/" in sample:
        return f"{digits[:4]}/{digits[4:6]}/{digits[6:]}"
    if "-" in sample:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return digits


def set_year_range(payload: dict, year: int) -> list[str]:
    """캡처한 WebSquare 요청의 공고일 시작·종료값을 해당 연도로 바꾼다.

    나라장터 내부 키의 세부 표기가 바뀌더라도 날짜 필드명과 현재 날짜값을 함께
    확인한다. 시작·종료 두 필드를 확정하지 못하면 짧은 기본 조회기간으로 잘못
    수집하지 않도록 즉시 중단한다.
    """
    changed: list[str] = []
    candidates: list[str] = []
    date_pattern = re.compile(r"^20\d{2}(?:[-./]?\d{2}){2}$")
    date_key_pattern = re.compile(r"(?:date|dt|ymd)", re.IGNORECASE)
    start_pattern = re.compile(
        r"(?:bgn|begin|start|from|fr|strt|stt|1)(?:date|dt|ymd)?$"
        r"|(?:date|dt|ymd)(?:bgn|begin|start|from|fr|strt|stt|1)$",
        re.IGNORECASE,
    )
    end_pattern = re.compile(
        r"(?:end|finish|to|2)(?:date|dt|ymd)?$"
        r"|(?:date|dt|ymd)(?:end|finish|to|2)$",
        re.IGNORECASE,
    )

    def visit(node: object, prefix: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                value_text = str(value)
                is_date_value = isinstance(value, (str, int)) and bool(date_pattern.match(value_text))
                if is_date_value and date_key_pattern.search(str(key)):
                    candidates.append(f"{path}={value_text}")
                    if start_pattern.search(str(key)):
                        node[key] = _date_value(year, True, value)
                        changed.append(path)
                    elif end_pattern.search(str(key)):
                        node[key] = _date_value(year, False, value)
                        changed.append(path)
                else:
                    visit(value, path)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, f"{prefix}[{index}]")

    visit(payload)
    if len(changed) < 2:
        candidate_text = ", ".join(candidates[:12]) or "날짜 후보 없음"
        raise RuntimeError(
            "나라장터 검색 요청에서 공고일 시작·종료 필드를 확인하지 못했습니다. "
            "2026년 전체가 아닌 일부만 저장될 수 있어 중단합니다. "
            f"감지한 날짜 후보: {candidate_text}"
        )
    return changed


def clean_datetime(value: object) -> str:
    """HTML이 섞인 게시일시에서 첫 번째 날짜·시간을 추출한다."""
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    match = re.search(r"(20\d{2}[-./]\d{1,2}[-./]\d{1,2}(?:\s+\d{1,2}:\d{2})?)", text)
    return match.group(1) if match else text


def is_target_notice(item: dict) -> bool:
    title = str(item.get("bidPbancNm") or "")
    posted_at = clean_datetime(item.get("pbancPstgDt"))
    return KEYWORD.casefold() in title.casefold() and posted_at.startswith(str(YEAR))


def to_output_row(item: dict) -> dict:
    return {
        "사업명": str(item.get("bidPbancNm") or "").strip(),
        "공고기관": str(item.get("oderInstUntyGrpNm") or "").strip(),
        "게시일시": clean_datetime(item.get("pbancPstgDt")),
    }


def dismiss_popups(page) -> None:
    page.keyboard.press("Escape")
    page.evaluate(
        """() => {
            document.querySelectorAll(
                '[role="dialog"],[class*="popup"],[class*="w2window"],[class*="layer"]'
            ).forEach((node) => {
                node.style.display = 'none';
                node.style.visibility = 'hidden';
            });
        }"""
    )


def open_bid_notice_list(page) -> None:
    """나라장터 메인에서 입찰공고목록 화면으로 이동한다."""
    page.goto(HOME_URL, wait_until="networkidle", timeout=120_000)
    dismiss_popups(page)

    clicked_bid = page.evaluate(
        """() => {
            const nodes = [...document.querySelectorAll('a[id*="gnbMenu"]')];
            const node = nodes.find((el) => el.textContent.includes('\uC785\uCC30'));
            if (!node) return false;
            node.click();
            return true;
        }"""
    )
    if not clicked_bid:
        raise RuntimeError("'입찰' 메뉴를 찾지 못했습니다. 나라장터 화면이 변경되었을 수 있습니다.")
    page.wait_for_timeout(1_500)

    clicked_list = page.evaluate(
        """() => {
            const nodes = [...document.querySelectorAll('a')];
            const node = nodes.find((el) => el.textContent.trim().includes('\uC785\uCC30\uACF5\uACE0\uBAA9\uB85D'));
            if (!node) return false;
            node.click();
            return true;
        }"""
    )
    if not clicked_list:
        raise RuntimeError("'입찰공고목록' 링크를 찾지 못했습니다. 나라장터 화면이 변경되었을 수 있습니다.")


def crawl(headless: bool = True, max_pages: int | None = None) -> tuple[list[dict], int]:
    from playwright.sync_api import sync_playwright

    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    selectors = profile["selectors"]
    endpoint = profile["api_endpoints"][0]["url"]

    captured_request: dict[str, object] = {}
    captured_response: list[dict] = []
    capture_enabled = [False]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(locale="ko-KR")

        def on_request(request) -> None:
            if capture_enabled[0] and API_URL_PART in request.url and not captured_request:
                captured_request.update({
                    "body": request.post_data,
                    "headers": dict(request.headers),
                })

        def on_response(response) -> None:
            if (
                capture_enabled[0]
                and API_URL_PART in response.url
                and response.status == 200
                and not captured_response
            ):
                try:
                    captured_response.append(response.json())
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)
        open_bid_notice_list(page)

        page.wait_for_selector(selectors["검색버튼"], timeout=60_000)
        page.select_option(selectors["페이지크기_select"], value=str(PAGE_SIZE))
        page.fill(selectors["공고명_input"], KEYWORD)
        capture_enabled[0] = True
        page.click(selectors["검색버튼"])

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and (not captured_request or not captured_response):
            page.wait_for_timeout(250)
        if not captured_request.get("body") or not captured_response:
            browser.close()
            raise RuntimeError("검색 API 요청을 캡처하지 못했습니다. 나라장터 화면 또는 API가 변경되었을 수 있습니다.")
        capture_enabled[0] = False

        headers = captured_request["headers"]
        websquare_headers = {
            "Content-Type": headers.get("content-type", "application/json;charset=UTF-8"),
            "accept": headers.get("accept", "application/json"),
            "submissionid": headers.get("submissionid", ""),
            "menu-info": headers.get("menu-info", ""),
            "target-id": headers.get("target-id", ""),
            "usr-id": headers.get("usr-id", "null"),
            "referer": HOME_URL,
        }
        base_body = json.loads(str(captured_request["body"]))
        changed_fields = set_year_range(base_body, YEAR)
        print("조회기간 설정:", ", ".join(changed_fields), f"→ {YEAR}-01-01~{YEAR}-12-31")

        # 화면 기본값(최근 1개월)이 담긴 첫 응답은 쓰지 않고, 같은 브라우저 세션에서
        # 날짜를 2026년 전체로 바꾼 첫 페이지부터 다시 조회한다.
        first_payload = page.evaluate(
            """async ({url, headers, body}) => {
                const response = await fetch(url, {
                    method: 'POST', headers, body: JSON.stringify(body)
                });
                if (!response.ok) return {error: response.status};
                return await response.json();
            }""",
            {"url": endpoint, "headers": websquare_headers, "body": base_body},
        )
        if first_payload.get("error"):
            browser.close()
            raise RuntimeError(f"2026년 첫 페이지 API 오류: HTTP {first_payload['error']}")

        all_items = list(first_payload.get("result") or [])
        total_count = int(first_payload.get("totCnt") or len(all_items))
        total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        if max_pages is not None:
            total_pages = min(total_pages, max_pages)

        for page_number in range(2, total_pages + 1):
            start_index = (page_number - 1) * PAGE_SIZE + 1
            end_index = min(page_number * PAGE_SIZE, total_count)
            body = json.loads(json.dumps(base_body))
            body["dlBidPbancLstM"]["startIndex"] = start_index
            body["dlBidPbancLstM"]["endIndex"] = end_index
            result = page.evaluate(
                """async ({url, headers, body}) => {
                    const response = await fetch(url, {
                        method: 'POST', headers, body: JSON.stringify(body)
                    });
                    if (!response.ok) return {error: response.status};
                    return await response.json();
                }""",
                {"url": endpoint, "headers": websquare_headers, "body": body},
            )
            if result.get("error"):
                browser.close()
                raise RuntimeError(f"{page_number}페이지 API 오류: HTTP {result['error']}")
            page_items = result.get("result") or []
            if not page_items:
                break
            all_items.extend(page_items)
            time.sleep(REQUEST_DELAY_SECONDS)

        browser.close()

    rows = [to_output_row(item) for item in all_items if is_target_notice(item)]
    unique_rows = list({(row["사업명"], row["공고기관"], row["게시일시"]): row for row in rows}.values())
    unique_rows.sort(key=lambda row: row["게시일시"], reverse=True)
    return unique_rows, total_count


def save_results(rows: list[dict], searched_count: int) -> Path:
    if not rows:
        raise RuntimeError("조건에 맞는 공고가 0건입니다. 추가 요청 없이 중단합니다.")

    result_dir = make_result_dir("나라장터")
    raw_path = result_dir / "2026_AI_공고.json"
    excel_path = result_dir / "2026_AI_공고.xlsx"
    script_copy = result_dir / "crawl_script.py"

    raw_path.write_text(
        json.dumps(
            {"검색어": KEYWORD, "대상연도": YEAR, "검색응답건수": searched_count, "결과": rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    export_to_excel(rows, str(excel_path), sheet_name="2026 AI 공고")
    shutil.copy2(__file__, script_copy)

    pii_warnings = detect_pii(rows)
    if pii_warnings:
        print("[개인정보 점검 경고]")
        for warning in pii_warnings:
            print(f"- {warning}")
    return excel_path


def main() -> int:
    parser = argparse.ArgumentParser(description="2026년 나라장터 AI 공고 수집")
    parser.add_argument("--show-browser", action="store_true", help="브라우저 창을 표시합니다.")
    parser.add_argument("--max-pages", type=int, help="시험 실행 시 가져올 최대 페이지 수")
    args = parser.parse_args()

    rows, searched_count = crawl(headless=not args.show_browser, max_pages=args.max_pages)
    excel_path = save_results(rows, searched_count)
    print(f"완료: {len(rows):,}건")
    print(f"저장: {excel_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
