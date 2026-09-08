import os
from datetime import date
from pathlib import Path
from unittest.mock import patch

from output_path import WINDOWS_DEFAULT_ROOT, get_output_root, make_result_dir


def test_environment_output_root_has_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_CRAWLER_OUTPUT_ROOT", str(tmp_path))
    assert get_output_root() == tmp_path


def test_windows_default_root(monkeypatch):
    monkeypatch.delenv("WEB_CRAWLER_OUTPUT_ROOT", raising=False)
    with patch.object(os, "name", "nt"):
        assert get_output_root() == WINDOWS_DEFAULT_ROOT


def test_result_folder_format(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_CRAWLER_OUTPUT_ROOT", str(tmp_path))
    result = make_result_dir("나라장터", date(2026, 9, 8))
    assert result == tmp_path / "20260908_나라장터"
    assert result.is_dir()


def test_result_folder_sanitizes_site_name(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_CRAWLER_OUTPUT_ROOT", str(tmp_path))
    result = make_result_dir("나라/장터", date(2026, 9, 8))
    assert result == Path(tmp_path) / "20260908_나라_장터"
