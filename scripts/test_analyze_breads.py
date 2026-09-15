"""Offline: 합성 텍스트로 집계 로직만 검증. 실제 네이버 리뷰가 아니다."""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jobs.naver_map.analyze_breads import (
    BREAD_LEXICON, find_breads, main, normalize, read_rows, tally,
)


def test_normalize_strips_space_and_case():
    assert normalize(" 소 금 빵 Croissant ") == "소금빵croissant"


@pytest.mark.parametrize("text,bread", [
    ("소금빵 먹었다", "소금빵"), ("크로와상 굿", "크루아상"), ("크루아상 굿", "크루아상"),
    ("까눌레 추천", "카눌레"), ("피낭시에", "휘낭시에"), ("Baguette 사옴", "바게트"),
])
def test_alias_maps_to_canonical_name(text, bread):
    assert find_breads(text) == {bread: 1}


def test_longer_alias_wins_over_substring():
    """에그타르트를 타르트로 겹쳐 세지 않는다."""
    assert find_breads("에그타르트") == {"에그타르트": 1}
    assert find_breads("에그타르트와 레몬 타르트") == {"에그타르트": 1, "타르트": 1}


def test_repeated_mentions_counted_each_time():
    assert find_breads("소금빵 소금빵 소금빵") == {"소금빵": 3}


def test_no_bare_bread_token_false_positive():
    """'빵집'·'빵' 만으로는 어떤 항목도 잡히지 않아야 한다."""
    assert find_breads("빵집 다녀왔어요. 빵 맛있다") == {}


def test_tally_ranks_by_post_count_then_total():
    rows = [
        {"title": "소금빵", "summary": "소금빵 또"},      # 소금빵 2회 / 1글
        {"title": "소금빵", "summary": "스콘"},            # 소금빵 1글, 스콘 1글
        {"title": "스콘", "summary": "스콘 스콘 스콘"},    # 스콘 1글
    ]
    result = tally(rows)
    # 둘 다 2글이므로 총 등장 횟수로 갈린다 (스콘 5 > 소금빵 3).
    assert [r["빵 종류"] for r in result] == ["스콘", "소금빵"]
    assert result[0] == {"순위": 1, "빵 종류": "스콘", "언급 글 수": 2, "총 등장 횟수": 5}
    assert result[1] == {"순위": 2, "빵 종류": "소금빵", "언급 글 수": 2, "총 등장 횟수": 3}


def test_tally_scans_title_and_summary_only():
    """author/blog_url 에 섞인 문자열은 집계에 들어가지 않는다."""
    assert tally([{"title": "", "summary": "", "author": "소금빵덕후",
                   "blog_url": "https://blog.naver.com/scone/1"}]) == []


def test_missing_fields_do_not_crash():
    assert tally([{}, {"title": None, "summary": None}]) == []


def test_lexicon_aliases_are_unique_per_bread():
    seen = {}
    for bread, aliases in BREAD_LEXICON.items():
        for alias in aliases:
            assert normalize(alias) not in seen, f"{alias} 중복: {bread} / {seen.get(normalize(alias))}"
            seen[normalize(alias)] = bread


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("blog_url", "title", "author", "published_at", "summary"))
        writer.writeheader()
        writer.writerows(rows)


def test_read_rows_handles_bom(tmp_path):
    path = tmp_path / "blog_reviews.csv"
    _write_csv(path, [{"blog_url": "https://blog.naver.com/a/1", "title": "소금빵",
                       "author": "", "published_at": "", "summary": ""}])
    assert read_rows(path)[0]["title"] == "소금빵"


def test_main_writes_excel(tmp_path):
    path = tmp_path / "blog_reviews.csv"
    _write_csv(path, [{"blog_url": "https://blog.naver.com/a/1", "title": "소금빵과 스콘",
                       "author": "", "published_at": "", "summary": "소금빵 또"}])
    assert main([str(path)]) == 0
    assert (tmp_path / "bread_mentions.xlsx").is_file()


def test_main_stops_without_overwriting_on_no_match(tmp_path):
    path = tmp_path / "blog_reviews.csv"
    _write_csv(path, [{"blog_url": "https://blog.naver.com/a/1", "title": "그냥 후기",
                       "author": "", "published_at": "", "summary": "좋았어요"}])
    assert main([str(path)]) == 4
    assert not (tmp_path / "bread_mentions.xlsx").exists()


def test_main_missing_csv_returns_error(tmp_path):
    assert main([str(tmp_path / "nope.csv")]) == 1
