"""크롤링 결과 폴더 경로를 일관되게 생성한다."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from utils import sanitize_filename


REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_DEFAULT_ROOT = Path(r"G:\내 드라이브\07. AI\클로드\11. 웹크롤러")
OUTPUT_ROOT_ENV = "WEB_CRAWLER_OUTPUT_ROOT"


def get_output_root() -> Path:
    """현재 PC에서 사용할 결과 저장 루트를 반환한다.

    환경변수가 있으면 운영체제와 관계없이 우선한다. Windows에서는 사용자가 지정한
    Google Drive 경로를 기본값으로 쓰고, 개발·CI용 macOS/Linux에서는 저장소의
    ``output`` 폴더를 사용한다.
    """
    configured = os.environ.get(OUTPUT_ROOT_ENV)
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        return WINDOWS_DEFAULT_ROOT
    return REPO_ROOT / "output"


def make_result_dir(site_name: str, run_date: date | None = None) -> Path:
    """``YYYYMMDD_사이트명`` 형식의 결과 폴더를 만들고 반환한다."""
    safe_site_name = sanitize_filename(site_name).strip("_")
    if not safe_site_name:
        raise ValueError("site_name에는 파일명으로 사용할 문자가 있어야 합니다.")

    folder_date = run_date or date.today()
    result_dir = get_output_root() / f"{folder_date:%Y%m%d}_{safe_site_name}"
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_dir
