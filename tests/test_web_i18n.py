"""Static regression checks for the build-free web UI translations."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
APP_JS = (ROOT / "carina/web/app.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "carina/web/index.html").read_text(encoding="utf-8")


def _dictionary_keys(source: str) -> tuple[set[str], set[str]]:
    english, chinese = source.split('  "zh-CN": {', maxsplit=1)
    chinese = chinese.split("\n  },\n};", maxsplit=1)[0]
    key_pattern = re.compile(r'^    "([^"]+)":', re.MULTILINE)
    return set(key_pattern.findall(english)), set(key_pattern.findall(chinese))


def test_english_and_chinese_dictionaries_have_the_same_keys():
    english, chinese = _dictionary_keys(APP_JS)

    assert english == chinese
    assert len(english) >= 50


def test_every_static_translation_key_exists_in_both_dictionaries():
    english, chinese = _dictionary_keys(APP_JS)
    html_keys = set(re.findall(r'data-i18n(?:-placeholder)?="([^"]+)"', INDEX_HTML))

    assert html_keys <= english
    assert html_keys <= chinese


def test_language_choice_is_persisted():
    assert 'localStorage.getItem("carina.language")' in APP_JS
    assert 'localStorage.setItem("carina.language"' in APP_JS
    assert '<option value="en">English</option>' in INDEX_HTML
    assert '<option value="zh-CN">简体中文</option>' in INDEX_HTML
