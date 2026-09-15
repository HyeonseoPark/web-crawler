"""blog_reviews.csv의 제목·요약에서 빵 종류 언급 횟수를 집계 → 엑셀/콘솔.

crawl_script.py가 저장한 CSV만 읽는다. 네트워크 접근은 하지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from export_excel import export_to_excel  # noqa: E402

# 표기명 → 별칭들. 공백 제거·소문자화한 텍스트에 부분 문자열로 맞춘다.
# 짧은 별칭이 긴 별칭 안에 들어가는 경우(타르트 ⊂ 에그타르트)는 긴 쪽이 이긴다.
BREAD_LEXICON: dict[str, tuple[str, ...]] = {
    # 2026-09-15 아소토베이커리 실데이터에서 빠져 있던 대표 메뉴. 긴 이름 우선 규칙 덕에
    # "메론크림빵" 이 크림빵으로, "메론소금빵" 이 소금빵으로 잘못 세이지 않는다.
    "메론크림빵": ("메론크림빵", "크림메론빵", "말차크림메론빵", "딸기크림메론빵",
                  "바닐라크림메론빵", "얼그레이크림메론빵", "멜론크림빵"),
    "메론소금빵": ("메론소금빵", "멜론소금빵"),
    "메론빵": ("메론빵", "멜론빵", "melonpan"),
    "명란소금빵": ("명란소금빵",),
    "초코소금빵": ("초코소금빵",),
    "글레이즈소금빵": ("글레이즈소금빵", "글레이즈드소금빵"),
    "트러플소금빵": ("트러플소금빵",),
    "고구마소금빵": ("고구마소금빵",),
    "카레빵": ("카레빵", "반숙카레빵"),
    "야끼소바빵": ("야끼소바빵", "야키소바빵"),
    "후르츠산도": ("후르츠산도", "과일산도", "망고산도", "복숭아산도", "메론산도", "무화과산도"),
    "모찌빵": ("모찌빵", "쫀득빵", "모찌단팥빵", "사빠딸"),
    "고양이식빵": ("고양이모찌쇼쿠팡", "고양이모찌쇼쿠빵", "고양이생식빵", "고양이식빵", "모찌쇼쿠팡"),
    "푸딩모찌": ("푸딩모찌", "푸딩쫀득모찌"),
    "당고페스츄리": ("당고페스츄리", "당고페이스트리", "당고패스트리"),
    "명란바게트": ("명란바게트",),
    "밤파이": ("밤파이",),
    "소라빵": ("소라빵", "초코소라빵"),
    "캣아망": ("캣아망", "고양이퀸아망"),
    "버터떡": ("버터떡",),
    "소금빵": ("소금빵", "시오빵", "saltbread"),
    "크루아상": ("크루아상", "크로와상", "크르와상", "croissant"),
    "뺑오쇼콜라": ("뺑오쇼콜라", "빵오쇼콜라", "팽오쇼콜라", "초코크루아상"),
    "앙버터": ("앙버터", "앙버터바게트", "앙버뜨"),
    "바게트": ("바게트", "바게뜨", "baguette"),
    "식빵": ("식빵", "생식빵", "우유식빵", "통밀식빵"),
    "베이글": ("베이글", "bagel"),
    "치아바타": ("치아바타", "챠바타", "ciabatta"),
    "깜빠뉴": ("깜빠뉴", "캉파뉴", "campagne"),
    "브리오슈": ("브리오슈", "브리오쉬", "brioche"),
    "포카치아": ("포카치아", "포카챠", "focaccia"),
    "프레첼": ("프레첼", "프레즐", "pretzel"),
    "쿠이냐망": ("쿠이냐망", "퀸아망", "쿠인아망", "kouignamann"),
    "카눌레": ("카눌레", "까눌레", "canele"),
    "휘낭시에": ("휘낭시에", "피낭시에", "financier"),
    "마들렌": ("마들렌", "마드레느", "madeleine"),
    "스콘": ("스콘", "scone"),
    "에그타르트": ("에그타르트", "에그타르뜨", "eggtart"),
    "타르트": ("타르트", "타르뜨", "tart"),
    "소보로빵": ("소보로", "곰보빵"),
    "단팥빵": ("단팥빵", "팥빵", "앙금빵"),
    "크림빵": ("크림빵", "슈크림빵"),
    "마늘빵": ("마늘빵", "갈릭브레드", "갈릭바게트"),
    "치즈빵": ("치즈빵", "치즈브레드", "크림치즈빵"),
    "도넛": ("도넛", "도너츠", "donut", "doughnut"),
    "몽블랑": ("몽블랑", "montblanc"),
    "밤식빵": ("밤식빵",),
    "먹물빵": ("먹물빵", "스퀴드잉크"),
    "프렌치토스트": ("프렌치토스트", "frenchtoast"),
    "파이": ("애플파이", "에그파이", "미트파이"),
    "머핀": ("머핀", "머퓐", "muffin"),
    "롤케이크": ("롤케이크", "롤케익"),
    "피자빵": ("피자빵", "피자브레드"),
    "크로플": ("크로플",),
    "약과": ("약과", "약과쿠키"),
    "쿠키": ("쿠키", "cookie"),
}
TEXT_FIELDS = ("title", "summary")


def normalize(text: str) -> str:
    """공백 제거 + 소문자화. 원문 인덱스는 버린다(집계에만 쓰므로 무해)."""
    return "".join(text.split()).lower()


def find_breads(text: str) -> Counter:
    """한 문서에서 빵별 등장 횟수. 겹치는 별칭은 긴 것 우선으로 한 번만 센다."""
    haystack = normalize(text)
    spans: list[tuple[int, int, str]] = []
    for bread, aliases in BREAD_LEXICON.items():
        for alias in aliases:
            needle = normalize(alias)
            start = haystack.find(needle)
            while start != -1:
                spans.append((start, start + len(needle), bread))
                start = haystack.find(needle, start + 1)
    # 긴 매치 우선 → 이미 소비된 구간과 겹치면 버린다.
    spans.sort(key=lambda s: (s[0] - s[1], s[0]))
    counts: Counter = Counter()
    taken: list[tuple[int, int]] = []
    for start, end, bread in spans:
        if any(start < t_end and t_start < end for t_start, t_end in taken):
            continue
        taken.append((start, end))
        counts[bread] += 1
    return counts


def tally(rows: list[dict]) -> list[dict]:
    """빵별 (언급 글 수, 총 등장 횟수). 글 수 내림차순 정렬."""
    posts: Counter = Counter()
    total: Counter = Counter()
    for row in rows:
        text = " ".join(str(row.get(field) or "") for field in TEXT_FIELDS)
        found = find_breads(text)
        for bread, count in found.items():
            posts[bread] += 1
            total[bread] += count
    ranked = sorted(posts, key=lambda b: (-posts[b], -total[b], b))
    return [{"순위": i, "빵 종류": b, "언급 글 수": posts[b], "총 등장 횟수": total[b]}
            for i, b in enumerate(ranked, 1)]


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, nargs="?", help="crawl_script.py가 만든 blog_reviews.csv")
    parser.add_argument("--output", type=Path, help="엑셀 저장 경로 (기본: CSV 옆 bread_mentions.xlsx)")
    parser.add_argument("--self-test", action="store_true", help="합성 문장으로 집계 로직만 검증")
    args = parser.parse_args(argv)

    if args.self_test:
        sample = [{"title": "소금빵과 에그타르트", "summary": "소금빵 또 먹음. 크로와상도."},
                  {"title": "앙버터 최고", "summary": "타르트는 평범"}]
        for row in tally(sample):
            print(row)
        return 0

    if not args.csv_path:
        parser.error("csv_path 또는 --self-test 중 하나가 필요합니다.")
    if not args.csv_path.is_file():
        print(f"[ERROR] CSV가 없습니다: {args.csv_path}")
        return 1

    rows = read_rows(args.csv_path)
    if not rows:
        print("[STOP] CSV가 비어 있습니다.")
        return 4
    ranking = tally(rows)
    if not ranking:
        print(f"[STOP] {len(rows)}건에서 사전에 있는 빵 이름을 하나도 찾지 못했습니다. "
              "제목·요약이 짧거나 BREAD_LEXICON 보강이 필요합니다.")
        return 4

    print(f"분석 대상 {len(rows)}건 (제목+요약)")
    for row in ranking:
        print(f"{row['순위']:>2}. {row['빵 종류']:<12} 글 {row['언급 글 수']:>3}건 / 등장 {row['총 등장 횟수']:>3}회")
    covered = sum(r["언급 글 수"] for r in ranking)
    print(f"※ 언급-글 합계 {covered} (한 글이 여러 빵을 말하면 중복 계수)")

    destination = args.output or args.csv_path.parent / "bread_mentions.xlsx"
    saved = export_to_excel(ranking, str(destination), sheet_name="빵 언급 횟수")
    print(f"엑셀: {saved}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
