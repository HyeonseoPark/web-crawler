# CHANGELOG

## 2026-09-15 — 네이버지도 블로그 리뷰 수집기 실사이트 보정

- 목적: `jobs/naver_map/crawl_script.py` 가 실제 네이버 화면에서 8건 이후 멈추거나 시작부터 중단되던 문제 해결 (아소토베이커리 50건 수집으로 확인)
- 수정: 리뷰 추가 버튼을 "펼쳐서 더보기"로 한정(사진 링크 오클릭 방지), 광고 서버 요청 차단(400 중단 원인), 클릭 후 새 카드 대기, `--delay`·`--ignore-robots`(명시적 선택 시에만) 옵션, 오류에 실패 주소 표시
- 빵 집계 사전에 메론크림빵·메론소금빵·메론빵·카레빵·후르츠산도 등 추가 (`jobs/naver_map/analyze_breads.py`)
- 파일: `jobs/naver_map/crawl_script.py`, `jobs/naver_map/analyze_breads.py`, `jobs/naver_map/README.md`, `scripts/test_naver_map.py`, `scripts/test_analyze_breads.py`
