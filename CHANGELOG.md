# CHANGELOG

## 2026-09-15 — 블로그 본문 기준 '맛있다' 규칙 판정 추가

- 목적: 미리보기 대신 본문 전체로 빵별 '맛있다' 글 수를 세되, blog.naver.com robots 의 AI·RAG 금지에 따라 AI 없이 규칙으로 판정
- 추가: `jobs/naver_map/fetch_posts.py`(본문 로컬 저장, 본문 미출력), `jobs/naver_map/judge_tasty.py`(긍정/부정/전해들은 표현·가게 추천·비교 제외 규칙), `scripts/test_judge_tasty.py`
- 수정: `jobs/naver_map/analyze_breads.py` 사전에 소금빵 변형·모찌빵·고양이식빵·당고페스츄리 등 추가, `jobs/naver_map/README.md`

## 2026-09-15 — 네이버지도 블로그 리뷰 수집기 실사이트 보정

- 목적: `jobs/naver_map/crawl_script.py` 가 실제 네이버 화면에서 8건 이후 멈추거나 시작부터 중단되던 문제 해결 (아소토베이커리 50건 수집으로 확인)
- 수정: 리뷰 추가 버튼을 "펼쳐서 더보기"로 한정(사진 링크 오클릭 방지), 광고 서버 요청 차단(400 중단 원인), 클릭 후 새 카드 대기, `--delay`·`--ignore-robots`(명시적 선택 시에만) 옵션, 오류에 실패 주소 표시
- 빵 집계 사전에 메론크림빵·메론소금빵·메론빵·카레빵·후르츠산도 등 추가 (`jobs/naver_map/analyze_breads.py`)
- 파일: `jobs/naver_map/crawl_script.py`, `jobs/naver_map/analyze_breads.py`, `jobs/naver_map/README.md`, `scripts/test_naver_map.py`, `scripts/test_analyze_breads.py`
