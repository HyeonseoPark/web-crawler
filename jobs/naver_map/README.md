# 네이버지도 장소 블로그 리뷰 → CSV

장소 ID 또는 네이버지도 URL을 받아 블로그 리뷰 목록에서 최대 **50개**의
`blog_url,title,author,published_at,summary`를 저장합니다. 기본 장소 ID는
아소토베이커리 예시 `1141254769`입니다. 게시물 본문은 방문하지 않습니다.

## 현재 검증 범위와 접근 조건

**실사이트의 DOM·페이지네이션은 아직 검증하지 못했습니다.** 선택자는 의미 기반 후보이며,
현재 네이버 화면에서 그대로 작동한다고 보장하지 않습니다. 합성 HTML로 Playwright 추출,
더보기, URL 정규화/중복 제거, CSV 출력을 테스트합니다. 테스트 데이터는 실제 리뷰가 아닙니다.

2026-09-14 확인한 [네이버 약관](https://policy.naver.com/rules/service.html)의
‘네이버 서비스 이용과 관련하여 몇 가지 주의사항이 있습니다’는 사전 허락 없는 자동 게시물 수집을
제한합니다. 따라서 실제 수집은 네이버의 사전 허락을 받은 경우에만 `--naver-permission`을 지정합니다.
이 옵션은 사용자 동의로 네이버의 허락을 대체하거나 robots 제한을 무시하는 옵션이 아닙니다.
이번 개발에서는 허락이 확인되지 않아 실제 리뷰 수집 및 내부 네트워크 API 정찰을 실행하지 않았습니다.

브라우저가 공개 장소 리뷰 화면(`/restaurant/<id>/review/ugc`)을 로드하고 더보기/스크롤로 진행합니다.
문서·XHR·fetch 요청 전 각 origin의 robots.txt를 Playwright로 검사합니다. 금지/조회 실패/리다이렉트,
HTTP 오류, 로그인, CAPTCHA·접근 제한에서 중단합니다. 요청 간 최소 1초 및 robots crawl-delay,
120회 데이터/robots 요청 상한, 20회 화면 탐색 상한을 적용합니다(이미지·스크립트 등 정적 자원은 별도).
내부 API는 검증되지 않아 직접 재호출하지 않으며, 로그인 세션·프록시·stealth·차단 회피를 사용하지 않습니다.

## 실행

저장소 공통 설치 안내로 Python 의존성과 Chromium을 준비한 후 저장소 루트에서 실행합니다.

```powershell
# 외부 접속 없이 합성 데이터로 CSV 출력 검증
.\.venv\Scripts\python.exe jobs\naver_map\crawl_script.py --dry-run --output-dir output\naver_map_demo

# 네이버의 사전 허락을 받은 환경에서만 사용: 기본 50개
.\.venv\Scripts\python.exe jobs\naver_map\crawl_script.py --place 1141254769 --naver-permission

# 장소 URL, 시험용 5개, 출력 위치 직접 지정
.\.venv\Scripts\python.exe jobs\naver_map\crawl_script.py --place "https://map.naver.com/p/entry/place/1141254769" --limit 5 --naver-permission --output-dir output\naver_map_5

.\.venv\Scripts\python.exe -m pytest scripts\test_naver_map.py -q
```

macOS/Linux에서는 Python 경로를 `.venv/bin/python`으로 바꿉니다.
`--headed`로 브라우저를 표시할 수 있습니다. `--place` 생략 시 예시 ID, `--limit` 생략 시 50이며
범위는 1~50입니다. 다른 장소 유형 등의 이유로 주소가 리다이렉트되면 자동으로 따라가지 않고 중단합니다.

`--output-dir` 생략 시 기존 `make_result_dir` 규칙과 `WEB_CRAWLER_OUTPUT_ROOT`를 따릅니다.
CSV는 Excel용 UTF-8 BOM, 표준 CSV 인용부호, 수식 시작 문자 보호를 적용합니다.
실수집은 `blog_reviews.csv`, 드라이런은 `blog_reviews.demo.csv`로 구분합니다.
기존 파일은 덮어쓰지 않습니다. 다시 실행하려면 새로운 출력 디렉토리를 지정하세요.

날짜는 목록에 표시된 값/`time[datetime]`을 그대로 보존합니다. 누락된 작성자·날짜·요약은
추측하지 않고 빈 칸으로 남기며, 종료 출력에 필드별 누락 건수를 표시합니다.
PC/모바일/`PostView.naver` URL의 동일 게시물은 하나로 합칩니다. 프로필 링크는 제외합니다.
목표보다 적은 건수는 `no_new_reviews` 또는 `round_limit`로 보고하며 ‘전체 수집 완료’로 해석하지 않습니다.
0건은 빈 목록 또는 DOM 변경일 수 있어 종료 코드 4로 중단합니다. 접근 차단은 3, 기타 오류는 1입니다.
차단·오류 시 부분 결과를 성공 파일로 저장하지 않습니다. 실수집 성공 프로필은 이번 개발에서 생성하지 않았습니다.

## DOM 변경 시

허락받은 환경에서 실제 목록 구조를 확인한 뒤 `--selectors selectors.json`으로 CSS 선택자를 교체할 수 있습니다.
`card`는 리뷰 한 건의 컨테이너이며, 나머지는 그 안에서 찾습니다. 예시(합성 HTML 구조):

```json
{"card":"li","title":"h3","author":".author","date":"time","summary":"p"}
```

이 옵션은 필드 위치만 변경합니다. 인증/robots/요청 상한은 변경하지 않습니다.
드라이런 성공은 실제 네이버 페이지에서의 작동 검증을 대신하지 않습니다.

## 빵 언급 횟수 집계 (`analyze_breads.py`)

수집된 `blog_reviews.csv`를 읽어 **제목+요약**에 등장하는 빵 종류를 세고,
`bread_mentions.xlsx`(시트 `빵 언급 횟수`)와 콘솔 순위표를 만듭니다. 네트워크 접근은 없습니다.

```bash
.venv/bin/python jobs/naver_map/analyze_breads.py output/<결과폴더>/blog_reviews.csv
.venv/bin/python jobs/naver_map/analyze_breads.py --self-test      # 합성 문장으로 로직만 확인
.venv/bin/python -m pytest scripts/test_analyze_breads.py -q
```

`언급 글 수`(그 빵을 말한 글의 수)로 정렬하고, 동률이면 `총 등장 횟수`로 가릅니다.
같은 빵의 표기 변형은 하나로 묶습니다(크로와상→크루아상, 까눌레→카눌레, 피낭시에→휘낭시에 등).
긴 이름이 짧은 이름을 포함하면 긴 쪽만 셉니다(`에그타르트`를 `타르트`로 중복 계수하지 않음).
`빵`·`빵집` 같은 일반 명사는 사전에 넣지 않아 오탐이 나지 않습니다.

**해석 시 주의:** crawl_script.py는 게시물 본문을 방문하지 않으므로 집계 대상은 목록에 보이는
제목과 짧은 요약뿐입니다. 따라서 이 수치는 "본문에서 실제로 칭찬받은 빵"이 아니라
**"제목·요약에 노출된 빵"**이며, 언급 횟수는 맛 평가가 아니라 노출 빈도입니다.
사전에 없는 빵은 세지 않으므로, 결과가 빈약하면 `BREAD_LEXICON`에 이름을 추가하세요.
