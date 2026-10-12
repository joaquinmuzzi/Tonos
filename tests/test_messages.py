"""Message codes: each one has an English text and a translation in the web page."""

import re
from pathlib import Path

import pytest

from tonos.messages import ENGLISH, english, message

WEB = Path(__file__).parents[1] / "tonos" / "web"
I18N = WEB / "i18n.js"


def _translations() -> dict[str, dict[str, str]]:
    """{language: {key: text}} read from web/i18n.js."""
    source = I18N.read_text(encoding="utf-8")
    blocks = re.split(r"^  (\w+): \{$", source, flags=re.MULTILINE)
    entry = re.compile(r'^    (\w+):\s*"((?:[^"\\]|\\.)*)",$', re.MULTILINE)
    return {
        language: dict(entry.findall(re.sub(r":\n\s+", ": ", body)))
        for language, body in zip(blocks[1::2], blocks[2::2])
    }


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def test_message_keeps_code_and_params():
    msg = message("too_long", minutes=20)
    assert msg == {"code": "too_long", "params": {"minutes": 20}}
    assert english(msg).startswith("The audio is longer than 20 minutes")


def test_unknown_code_is_rejected():
    with pytest.raises(KeyError):
        message("no_such_code")


@pytest.mark.parametrize("language", ["en", "es"])
def test_every_message_is_translated_in_the_web_page(language):
    texts = _translations()[language]
    missing = sorted(set(ENGLISH) - set(texts))
    assert not missing, f"missing in i18n.js ({language}): {missing}"
    for code, text in ENGLISH.items():
        assert _placeholders(texts[code]) == _placeholders(text), code


def test_web_page_uses_the_same_english_texts():
    english_texts = _translations()["en"]
    assert {code: english_texts[code] for code in ENGLISH} == ENGLISH


def test_languages_have_the_same_keys():
    translations = _translations()
    assert set(translations) == {"en", "es"}
    assert set(translations["en"]) == set(translations["es"])
    for key, text in translations["en"].items():
        assert _placeholders(translations["es"][key]) == _placeholders(text), key


def test_page_and_script_only_use_known_keys():
    keys = set(_translations()["en"])
    page = (WEB / "index.html").read_text(encoding="utf-8")
    script = (WEB / "app.js").read_text(encoding="utf-8")
    used = set(re.findall(r'data-i18n(?:-aria-label)?="(\w+)"', page))
    used |= set(re.findall(r'\b(?:t|local)\("(\w+)"', script))
    assert used, "no keys found"
    assert not used - keys, sorted(used - keys)
