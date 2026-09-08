from jobs.g2b_ai_2026.crawl_script import clean_datetime, set_year_range


def test_clean_datetime_removes_html():
    assert clean_datetime("<span>2026-09-08 13:20</span><br>마감") == "2026-09-08 13:20"


def test_set_year_range_preserves_date_format():
    payload = {
        "condition": {
            "pbancPstgBgnDt": "20260808",
            "pbancPstgEndDt": "20260908",
        }
    }
    changed = set_year_range(payload, 2026)
    assert changed == ["condition.pbancPstgBgnDt", "condition.pbancPstgEndDt"]
    assert payload["condition"]["pbancPstgBgnDt"] == "20260101"
    assert payload["condition"]["pbancPstgEndDt"] == "20261231"


def test_set_year_range_accepts_dt_before_direction_suffix():
    payload = {
        "condition": {
            "pbancPstgDtFr": "2026-08-08",
            "pbancPstgDtTo": "2026-09-08",
        }
    }
    changed = set_year_range(payload, 2026)
    assert changed == ["condition.pbancPstgDtFr", "condition.pbancPstgDtTo"]
    assert payload["condition"]["pbancPstgDtFr"] == "2026-01-01"
    assert payload["condition"]["pbancPstgDtTo"] == "2026-12-31"


def test_set_year_range_preserves_integer_dates():
    payload = {"condition": {"inqryBgnDt": 20260808, "inqryEndDt": 20260908}}
    set_year_range(payload, 2026)
    assert payload["condition"]["inqryBgnDt"] == 20260101
    assert payload["condition"]["inqryEndDt"] == 20261231


def test_set_year_range_stops_when_fields_are_unknown():
    payload = {"condition": {"createdDate": "20260908"}}
    try:
        set_year_range(payload, 2026)
    except RuntimeError as error:
        assert "시작·종료 필드" in str(error)
    else:
        raise AssertionError("날짜 범위를 확인하지 못하면 중단해야 합니다.")
