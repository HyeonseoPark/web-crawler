"""네이버 검색 화면 수집 실행기. API 키 불필요."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from naver_search import SELECTORS, collect, search_blogs, classify_place
from output_path import make_result_dir
from utils import detect_pii


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="아소토베이커리 서울 중구 수표로10길")
    parser.add_argument("--place-name", default="아소토베이커리")
    parser.add_argument("--address", default="수표로10길 19")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--selectors", type=Path)
    parser.add_argument("--naver-permission", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 50 or not all(s.strip() for s in (args.query, args.place_name, args.address)):
        parser.error("검색어/장소명/주소는 필수이며 limit은 1~50입니다.")
    try:
        selectors = SELECTORS.copy()
        if args.selectors:
            custom = json.loads(args.selectors.read_text(encoding="utf-8"))
            if not isinstance(custom, dict) or set(custom) - set(selectors) or not all(isinstance(v, str) and v.strip() for v in custom.values()):
                raise ValueError("선택자 JSON 형식이 잘못되었습니다.")
            selectors.update(custom)
        if args.dry_run:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    page = browser.new_page()
                    page.route("**/*", lambda route: route.abort())
                    page.set_content((Path(__file__).parent / "fixture.html").read_text(encoding="utf-8"))
                    rows, reason = collect(page, args.limit, selectors)
                finally:
                    browser.close()
        else:
            rows, reason = search_blogs(args.query, limit=args.limit, selectors=selectors,
                                       permission=args.naver_permission, headed=args.headed)
        if not rows:
            print("[STOP] 0건. 빈 결과 또는 DOM 변경. CSV를 생성하지 않습니다.")
            return 4
        for row in rows:
            row["location_status"] = classify_place(row, args.place_name, args.address)
            row["source"] = "synthetic_fixture" if args.dry_run else "naver_search_page"
        destination = args.output_dir or make_result_dir("네이버검색")
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / ("search.demo.csv" if args.dry_run else "search.csv")
        with path.open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: "'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v for k, v in row.items()})
        for warning in detect_pii(rows):
            print(warning)
        print(f"CSV: {path}\n검색 후보 {len(rows)}건; 종료 사유: {reason}")
        print("주소가 요약에 있는 후보: " + str(sum(r['location_status'] == 'address_in_snippet' for r in rows)))
        return 0
    except PermissionError as exc:
        print(f"[BLOCKED] {exc}")
        return 3
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
