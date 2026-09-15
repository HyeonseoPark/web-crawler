"""Offline: 합성 문장으로 규칙 판정만 검증. 실제 블로그 본문이 아니다."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jobs.naver_map.judge_tasty import classify, judge_post, main, run, sentences  # noqa: E402
from jobs.naver_map.fetch_posts import extract_paragraphs, fetch_all, mobile_url  # noqa: E402


def test_classify_priority():
    assert classify("메론크림빵 진짜 맛있어요") == "pos"
    assert classify("맛있다고 해서 기대했는데") == "hearsay"
    assert classify("맛있긴 한데 가격이 아쉬움") == "neg"
    assert classify("가게가 예쁘다") == ""


def test_one_vote_per_bread_per_post():
    votes = judge_post(["메론크림빵 맛있다.", "메론크림빵 또 먹고 싶다 최고"])
    assert list(votes) == ["메론크림빵"]


def test_negative_and_hearsay_excluded():
    votes = judge_post(["야끼소바빵은 너무 짰어요.", "카레빵이 맛있다고 해서 샀어요."])
    assert votes == {}


def test_carry_to_previous_sentence():
    votes = judge_post(["반숙카레빵", "진짜 맛있었어요"])
    assert list(votes) == ["카레빵"]
    assert votes["카레빵"].endswith("(앞 문장 연결)")
    # 앞 문장이 이미 평가됐으면 넘기지 않는다
    assert list(judge_post(["밤파이는 별로였고", "커피는 맛있었어요"])) == []


def test_place_recommendation_and_comparison_are_not_votes():
    assert judge_post(["을지로 카페 추천 메론빵 유명한 곳"]) == {}
    assert judge_post(["메론빵", "을지로 베이커리 추천"]) == {}
    assert judge_post(["메론빵은 소보로빵 같은 느낌인데 맛있어요"]) == {"메론빵": "메론빵은 소보로빵 같은 느낌인데 맛있어요"}
    # '좋았다'는 앞 문장으로 넘기지 않는다 (분위기 평에도 쓰인다)
    assert judge_post(["메론빵", "분위기 좋았다"]) == {}


def test_sentence_split_on_laughter_and_punctuation():
    assert sentences(["소금빵 맛있음ㅋㅋㅋ메론빵 별로. 끝"]) == ["소금빵 맛있음", "메론빵 별로.", "끝"]


def test_run_and_excel(tmp_path):
    posts = [{"index": 1, "blog_url": "https://blog.naver.com/a/1", "paragraphs": ["소금빵 추천!"], "error": ""},
             {"index": 2, "blog_url": "https://blog.naver.com/a/2", "paragraphs": [], "error": "HTTP 404"}]
    counts, rows = run(posts)
    assert counts == {"소금빵": 1} and rows[1]["status"].startswith("본문 없음")
    src = tmp_path / "posts.json"
    src.write_text(json.dumps(posts, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out.xlsx"
    assert main([str(src), "--output", str(out)]) == 0 and out.exists()


def test_mobile_url():
    assert mobile_url("https://blog.naver.com/PostView.naver?blogId=a_b&logNo=12") == "https://m.blog.naver.com/a_b/12"


class _Node:
    def __init__(self, text):
        self.text = text

    def get_all_text(self, separator=" ", strip=True):
        return self.text


class _Page:
    status = 200
    body = b"<html>" + b"x" * 100 + b"</html>"

    def css(self, selector):
        return [_Node(" 첫  문단 "), _Node("")] if selector.startswith(".se-main") else []


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, **kw):
        assert kw["headers"]["User-Agent"].startswith("WebCrawlerNaverMap")
        return _Page()


def test_fetch_respects_robots_and_extracts(monkeypatch):
    monkeypatch.setattr("utils.RateLimiter.wait", lambda self: None)
    allow = lambda url, agent: {"allowed": True, "crawl_delay": None, "error": None}
    deny = lambda url, agent: {"allowed": agent != "*", "crawl_delay": None, "error": None}
    urls = ["https://blog.naver.com/a/1"]
    assert fetch_all(urls, 1, session_factory=_Session, robots=allow)[0]["paragraphs"] == ["첫 문단"]
    assert fetch_all(urls, 1, session_factory=_Session, robots=deny)[0]["error"].startswith("robots")
    assert extract_paragraphs(_Page()) == ["첫 문단"]
