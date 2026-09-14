# 네이버 검색 화면 크롤러 (API 키 불필요)

`scripts/naver_search.py`는 재사용 모듈, `jobs/naver_search/crawl_script.py`는 실행기입니다.
Playwright로 네이버 블로그 검색 화면을 읽습니다. 공식 API를 호출하지 않습니다.
기존 지도 작업의 브라우저·robots·요청 속도·접근 차단 처리를 재사용합니다.

기본 검색어는 **아소토베이커리 서울 중구 수표로10길**, 주소 판정 기준은 **수표로10길 19**,
상한은 **50개**입니다. 네이버 블로그 게시물만 선택하며 URL 중복을 제거합니다.
제목·작성자·작성일·요약은 검색 카드에 표시된 값만 저장합니다. 누락 값은 빈칸이며
블로그 본문에 접속하지 않습니다. 날짜가 상대 표현이면 그대로 저장합니다.

```powershell
# 외부 접속 없는 합성 HTML 테스트
.\.venv\Scripts\python.exe jobs/naver_search/crawl_script.py --dry-run --output-dir output/search_demo

# 허락받은 환경에서 실제 검색. robots/접근 제한에서는 중단
.\.venv\Scripts\python.exe jobs/naver_search/crawl_script.py --naver-permission --output-dir output/asoto_search

# 다른 장소에 재사용
.\.venv\Scripts\python.exe jobs/naver_search/crawl_script.py --query "검색어" --place-name "매장명" --address "도로명주소" --limit 20 --naver-permission

.\.venv\Scripts\python.exe -m pytest scripts/test_naver_search.py scripts/test_naver_map.py -q
```

재사용 호출(저장소 루트를 Python 경로에 포함):

```python
from scripts.naver_search import search_blogs
rows, stop_reason = search_blogs("아소토베이커리 서울 중구", limit=50, permission=True)
```

CSV는 UTF-8 BOM이며 기존 파일을 덮어쓰지 않습니다. 다른 폴더로 재실행하세요.
추가 열 `location_status`는 `address_in_snippet`(매장명과 주소가 검색 요약에 있음),
`needs_location_check`(매장명만 있음), `name_not_found`(매장명도 미확인)로 구분합니다.
이것은 장소 일치의 **검색 요약 근거**이며 실제 방문 리뷰/지도 place ID 일치 확정이 아닙니다.
미확인 후보를 중구 매장 리뷰로 집계하지 마세요.

`--selectors`에 card/title/author/date/summary CSS 선택자 JSON을 주면 DOM 변경에 대응할 수 있습니다.
`--headed`는 브라우저를 표시합니다. 최대 20회 스크롤하며 새 결과가 없으면 종료합니다.
0건은 종료 코드 4, 차단은 3, 기타 오류는 1입니다. API 키와 비용 설정은 없습니다.

## 검증 현황

2026-09-14 실제 검색을 시도했으나 `search.naver.com` robots.txt의 금지로 중단했습니다.
실제 리뷰 CSV는 생성되지 않았고, 현재 선택자는 실사이트에서 검증되지 않았습니다.
합성 HTML을 사용한 오프라인 테스트만 실제 추출 경로를 검증합니다.
지도 차단을 피하기 위한 우회 옵션은 없으며 검색 경로에도 동일한 접근 검사를 적용합니다.
