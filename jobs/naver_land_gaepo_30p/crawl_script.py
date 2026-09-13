r"""네이버페이 부동산에서 개포동 30평대 매매 매물을 수집한다.

실행(저장소 루트 PowerShell):
    .\.venv\Scripts\python.exe jobs\naver_land_gaepo_30p\crawl_script.py

30평대는 사용자가 지정한 화면 필터와 동일하게 공급면적 99~132㎡로 정의한다.
중개사 전화번호 등 개인정보성 항목은 수집하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlencode


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from export_excel import export_to_excel  # noqa: E402
from output_path import make_result_dir  # noqa: E402
from utils import (  # noqa: E402
    BudgetExceeded,
    RateLimiter,
    detect_pii,
    detect_softblock,
    plain_session,
)


BASE_URL = "https://new.land.naver.com"
START_URL = (
    f"{BASE_URL}/complexes?ms=37.482968,127.0634,16"
    "&a=APT:ABYG:JGC&b=A1&e=RETAIL&h=99&i=132"
)
GAEPO_CORTAR_NO = "1168010300"
REAL_ESTATE_TYPES = "APT:ABYG:JGC"
TRADE_TYPE = "A1"
AREA_MIN = 99.0
AREA_MAX = 132.0
REQUEST_DELAY_SECONDS = 1.0
DEFAULT_MAX_REQUESTS = 200
DEFAULT_MAX_PAGES_PER_COMPLEX = 20
JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def build_url(path: str, params: dict[str, object] | None = None) -> str:
    """API 경로와 쿼리 파라미터를 안전하게 합친다."""
    url = f"{BASE_URL}/api{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def parse_area(value: object) -> float | None:
    """'112.34', '112.34㎡' 같은 값을 ㎡ 실수로 변환한다."""
    if value is None:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def price_to_manwon(value: object) -> int | None:
    """'31억 5,000' 형식의 가격을 만원 단위 정수로 변환한다."""
    text = str(value or "").replace(",", "").replace(" ", "")
    if not text:
        return None
    match = re.fullmatch(r"(?:(\d+(?:\.\d+)?)억)?(?:(\d+))?", text)
    if not match:
        return None
    eok = float(match.group(1) or 0)
    remainder = int(match.group(2) or 0)
    return round(eok * 10_000 + remainder)


def is_target_article(article: dict) -> bool:
    """매매이면서 공급면적 99~132㎡인 매물만 통과시킨다."""
    trade_code = str(article.get("tradeTypeCode") or article.get("tradeTypeName") or "")
    is_sale = trade_code in {"A1", "매매"}
    area = parse_area(article.get("area1"))
    return is_sale and area is not None and AREA_MIN <= area <= AREA_MAX


def to_output_row(article: dict, complex_info: dict) -> dict:
    """네이버 API 필드를 개인정보를 제외한 엑셀 행으로 변환한다."""
    complex_no = str(complex_info.get("complexNo") or article.get("complexNo") or "")
    article_no = str(article.get("articleNo") or "")
    price = str(article.get("dealOrWarrantPrc") or "").strip()
    return {
        "단지명": str(complex_info.get("complexName") or article.get("articleName") or "").strip(),
        "매매가": price,
        "매매가(만원)": price_to_manwon(price),
        "공급면적(㎡)": parse_area(article.get("area1")),
        "전용면적(㎡)": parse_area(article.get("area2")),
        "동": str(article.get("buildingName") or "").strip(),
        "층": str(article.get("floorInfo") or "").strip(),
        "방향": str(article.get("direction") or "").strip(),
        "매물특징": str(article.get("articleFeatureDesc") or "").strip(),
        "확인일": str(article.get("articleConfirmYmd") or "").strip(),
        "매물번호": article_no,
        "매물링크": (
            f"{BASE_URL}/complexes/{complex_no}?articleNo={article_no}"
            if complex_no and article_no
            else ""
        ),
    }


def _response_text(response) -> str:
    return str(getattr(response, "html_content", "") or "")


def _get_json(session, limiter: RateLimiter, url: str, headers: dict[str, str]) -> dict:
    """RateLimiter를 적용해 JSON 한 건을 받고 오류를 명확히 구분한다."""
    limiter.wait()
    response = session.get(url, headers=headers, timeout=30)
    status = int(getattr(response, "status", 0) or 0)
    if status in {403, 429}:
        raise PermissionError(f"자동 접근 거절 가능성: HTTP {status} ({url})")
    if status != 200:
        raise RuntimeError(f"API HTTP {status} ({url})")
    body = _response_text(response)
    try:
        data = response.json()
    except Exception as exc:
        preview = body[:200].replace("\n", " ")
        raise RuntimeError(f"JSON이 아닌 응답: {preview}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"예상하지 못한 JSON 형식: {type(data).__name__}")
    softblock = detect_softblock(body, status=status, selector_hit=bool(data))
    if softblock["blocked"]:
        raise PermissionError(
            f"소프트블록 감지: {softblock['verdict']} ({', '.join(softblock['signals'])})"
        )
    if data.get("error"):
        raise RuntimeError(f"네이버 API 오류: {data['error']}")
    return data


def _authorize_session(session, max_requests: int):
    """메인 페이지에서 공개 프론트엔드용 JWT를 얻어 헤더를 반환한다."""
    limiter = RateLimiter(delay=REQUEST_DELAY_SECONDS, max_requests=max_requests)
    limiter.wait()
    response = session.get(
        START_URL,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "User-Agent": "web-crawler-agent/1.0 (+https://github.com/HyeonseoPark/web-crawler)",
        },
        timeout=30,
    )
    status = int(getattr(response, "status", 0) or 0)
    if status in {403, 429}:
        raise PermissionError(f"자동 접근 거절 가능성: HTTP {status} (시작 페이지)")
    if status != 200:
        raise RuntimeError(f"시작 페이지 HTTP {status}")
    body = _response_text(response)
    tokens = JWT_PATTERN.findall(body)
    softblock = detect_softblock(body, status=status, selector_hit=bool(tokens))
    if softblock["blocked"]:
        raise PermissionError(
            f"소프트블록 감지: {softblock['verdict']} ({', '.join(softblock['signals'])})"
        )
    if not tokens:
        raise RuntimeError("시작 페이지에서 API 인증 토큰을 찾지 못했습니다.")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Authorization": f"Bearer {tokens[0]}",
        "Referer": START_URL,
        "User-Agent": "web-crawler-agent/1.0 (+https://github.com/HyeonseoPark/web-crawler)",
    }
    return limiter, headers


def crawl(
    *,
    complex_nos: set[str] | None = None,
    max_complexes: int | None = None,
    max_pages_per_complex: int = DEFAULT_MAX_PAGES_PER_COMPLEX,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    checkpoint_path: Path | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """개포동 단지 목록을 순회해 30평대 매매 매물을 수집한다."""
    rows: list[dict] = []
    seen_article_nos: set[str] = set()
    stats = {"available_complexes": 0, "complexes": 0, "pages": 0, "errors": 0}
    consecutive_errors = 0
    next_checkpoint = 100
    with plain_session() as session:
        limiter, headers = _authorize_session(session, max_requests)
        complexes_data = _get_json(
            session,
            limiter,
            build_url(
                "/regions/complexes",
                {
                    "cortarNo": GAEPO_CORTAR_NO,
                    "realEstateType": REAL_ESTATE_TYPES,
                    "order": "",
                },
            ),
            headers,
        )
        complexes = list(complexes_data.get("complexList") or [])
        complexes = [item for item in complexes if int(item.get("dealCount") or 0) > 0]
        stats["available_complexes"] = len(complexes)
        if complex_nos:
            complexes = [item for item in complexes if str(item.get("complexNo") or "") in complex_nos]
        if max_complexes is not None:
            complexes = complexes[:max_complexes]

        for complex_info in complexes:
            complex_no = str(complex_info.get("complexNo") or "")
            if not complex_no:
                continue
            stats["complexes"] += 1

            for page in range(1, max_pages_per_complex + 1):
                try:
                    data = _get_json(
                        session,
                        limiter,
                        build_url(
                            f"/articles/complex/{complex_no}",
                            {
                                "realEstateType": REAL_ESTATE_TYPES,
                                "tradeType": TRADE_TYPE,
                                "tag": "::::::::",
                                "rentPriceMin": 0,
                                "rentPriceMax": 900_000_000,
                                "priceMin": 0,
                                "priceMax": 900_000_000,
                                "areaMin": int(AREA_MIN),
                                "areaMax": int(AREA_MAX),
                                "oldBuildYears": "",
                                "recentlyBuildYears": "",
                                "minHouseHoldCount": "",
                                "maxHouseHoldCount": "",
                                "priceType": "RETAIL",
                                "sameAddressGroup": "true",
                                "showArticle": "false",
                                "minMaintenanceCost": "",
                                "maxMaintenanceCost": "",
                                "directions": "",
                                "complexNo": complex_no,
                                "buildingNos": "",
                                "areaNos": "",
                                "type": "list",
                                "order": "rank",
                                "page": page,
                            },
                        ),
                        headers,
                    )
                    batch = list(data.get("articleList") or [])
                    stats["pages"] += 1
                    if not batch:
                        break

                    for article in batch:
                        article_no = str(article.get("articleNo") or "")
                        if not article_no or article_no in seen_article_nos:
                            continue
                        if not is_target_article(article):
                            continue
                        seen_article_nos.add(article_no)
                        rows.append(to_output_row(article, complex_info))

                    if checkpoint_path is not None and len(rows) >= next_checkpoint:
                        checkpoint_path.write_text(
                            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        while next_checkpoint <= len(rows):
                            next_checkpoint += 100

                    consecutive_errors = 0
                    if not data.get("isMoreData"):
                        break
                except BudgetExceeded:
                    raise
                except Exception as exc:
                    stats["errors"] += 1
                    consecutive_errors += 1
                    print(f"[WARN] 단지 {complex_no} page {page}: {exc}")
                    if isinstance(exc, PermissionError):
                        raise
                    if consecutive_errors >= 5:
                        raise RuntimeError("5회 연속 오류로 수집을 중단합니다.") from exc
                    continue
    rows.sort(key=lambda row: (row["단지명"], row["매매가(만원)"] or 0, row["매물번호"]))
    return rows, stats


def write_results(
    rows: list[dict], stats: dict[str, int], result_dir: Path
) -> tuple[Path, Path] | None:
    """0건일 때 기존 결과를 보존하고, 성공 결과만 JSON·Excel로 저장한다."""
    if not rows:
        return None
    raw_path = result_dir / "raw_data.json"
    excel_path = result_dir / "crawl_result.xlsx"
    progress_path = result_dir / "progress.json"
    script_copy = result_dir / "crawl_script.py"

    if raw_path.exists():
        shutil.copy2(raw_path, raw_path.with_suffix(".json.bak"))
    raw_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    progress_path.write_text(
        json.dumps({**stats, "collected": len(rows)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    export_to_excel(rows, str(excel_path), sheet_name="개포동 30평대 매매")
    shutil.copy2(Path(__file__), script_copy)
    checkpoint_path = result_dir / "raw_data.partial.json"
    checkpoint_path.unlink(missing_ok=True)
    return raw_path, excel_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="개포동 30평대(99~132㎡) 매매 매물 수집")
    parser.add_argument("--max-complexes", type=int, default=None, help="시험용 단지 수 상한")
    parser.add_argument(
        "--complex-no",
        action="append",
        default=None,
        help="특정 단지만 수집할 때 사용할 단지번호(여러 번 지정 가능)",
    )
    parser.add_argument(
        "--max-pages-per-complex",
        type=int,
        default=DEFAULT_MAX_PAGES_PER_COMPLEX,
        help="단지별 페이지 상한(기본 20)",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=DEFAULT_MAX_REQUESTS,
        help="전체 HTTP 요청 상한(기본 200)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = time.monotonic()
    result_dir = make_result_dir("네이버부동산_개포동_30평대_매매")
    checkpoint_path = result_dir / "raw_data.partial.json"
    try:
        rows, stats = crawl(
            complex_nos=set(args.complex_no) if args.complex_no else None,
            max_complexes=args.max_complexes,
            max_pages_per_complex=args.max_pages_per_complex,
            max_requests=args.max_requests,
            checkpoint_path=checkpoint_path,
        )
    except PermissionError as exc:
        print(f"[BLOCKED] {exc}")
        print("사다리 B(차단 대응)로 넘어가기 전에 사용자 확인이 필요합니다.")
        return 3
    except BudgetExceeded as exc:
        print(f"[STOP] 요청 상한 도달: {exc}")
        return 2
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not rows:
        print("[STOP] 조건에 맞는 매물이 0건이라 기존 산출물을 덮지 않았습니다.")
        return 4

    pii_warnings = detect_pii(rows)
    if pii_warnings:
        print("[PII 경고]")
        for warning in pii_warnings:
            print(f"- {warning}")

    paths = write_results(rows, stats, result_dir)
    assert paths is not None
    raw_path, excel_path = paths
    elapsed = time.monotonic() - started_at
    print(f"수집 건수: {len(rows)}")
    print(
        "대상·조회 단지/페이지/오류: "
        f"{stats['available_complexes']}/{stats['complexes']}/{stats['pages']}/{stats['errors']}"
    )
    print(f"소요 시간: {elapsed:.1f}초")
    print(f"JSON: {raw_path}")
    print(f"Excel: {excel_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
