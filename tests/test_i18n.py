from __future__ import annotations

import pytest

from ffai.i18n import _CATALOGS, Translator, resolve_language


def test_explicit_language_wins() -> None:
    assert resolve_language("en", {"FFAI_LANG": "zh", "LANG": "zh_CN.UTF-8"}) == "en"
    assert resolve_language("zh", {"FFAI_LANG": "en", "LANG": "en_US.UTF-8"}) == "zh"


def test_ffai_lang_accepts_locale_suffixes() -> None:
    assert resolve_language(None, {"FFAI_LANG": "zh-CN"}) == "zh"
    assert resolve_language(None, {"FFAI_LANG": "en_US"}) == "en"


def test_locale_is_used_as_fallback() -> None:
    assert resolve_language(None, {"LANG": "zh_CN.UTF-8"}) == "zh"
    assert resolve_language(None, {"LANG": "en_US.UTF-8"}) == "en"
    assert resolve_language(None, {}) == "en"


def test_chinese_locale_takes_precedence_over_lang() -> None:
    assert resolve_language(None, {"LC_ALL": "zh_CN.UTF-8", "LANG": "en_US.UTF-8"}) == "zh"


def test_translation_catalogs_have_identical_keys() -> None:
    assert set(_CATALOGS["en"]) == set(_CATALOGS["zh"])


def test_translator_formats_values() -> None:
    assert Translator("en")("action.added", path="/tmp/a.mp4") == "Added input: /tmp/a.mp4"
    assert Translator("zh")("action.added", path="/tmp/a.mp4") == "已添加输入：/tmp/a.mp4"


def test_unknown_translation_key_is_visible() -> None:
    assert Translator("zh")("missing.key") == "missing.key"


@pytest.mark.parametrize("language", ["en", "zh"])
def test_all_translation_keys_have_non_empty_values(language: str) -> None:
    assert all(value for value in _CATALOGS[language].values())
