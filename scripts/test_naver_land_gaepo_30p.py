from jobs.naver_land_gaepo_30p.crawl_script import (
    AREA_MAX,
    AREA_MIN,
    build_url,
    is_target_article,
    parse_area,
    price_to_manwon,
    to_output_row,
)


def test_area_bounds_match_30_pyeong_filter():
    assert (AREA_MIN, AREA_MAX) == (99.0, 132.0)
    assert is_target_article({"tradeTypeCode": "A1", "area1": "99"})
    assert is_target_article({"tradeTypeName": "매매", "area1": "132㎡"})
    assert not is_target_article({"tradeTypeCode": "A1", "area1": "98.99"})
    assert not is_target_article({"tradeTypeCode": "B1", "area1": "110"})


def test_parse_area():
    assert parse_area("112.34㎡") == 112.34
    assert parse_area(None) is None
    assert parse_area("-") is None


def test_price_to_manwon():
    assert price_to_manwon("31억") == 310_000
    assert price_to_manwon("31억 5,000") == 315_000
    assert price_to_manwon("33.5억") == 335_000
    assert price_to_manwon("") is None


def test_output_row_excludes_contact_fields():
    article = {
        "articleNo": "123",
        "tradeTypeCode": "A1",
        "dealOrWarrantPrc": "31억",
        "area1": "105",
        "area2": "84.9",
        "realtorName": "예시공인중개사",
        "cpPcArticleUrl": "https://example.invalid/contact",
    }
    row = to_output_row(article, {"complexNo": "8928", "complexName": "LG개포자이"})
    assert row["단지명"] == "LG개포자이"
    assert row["매매가(만원)"] == 310_000
    assert row["매물링크"].endswith("/complexes/8928?articleNo=123")
    assert not any("전화" in key or "중개사" in key for key in row)


def test_build_url_encodes_colon_filter():
    url = build_url("/regions/complexes", {"realEstateType": "APT:ABYG:JGC"})
    assert url.endswith("realEstateType=APT%3AABYG%3AJGC")
