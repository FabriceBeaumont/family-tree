"""Viewer source (src/index.html + style.css + i18n.js) and how the build puts it together."""
import re

import pytest

import build_web

SRC = build_web.SRC


def test_build_inlines_styles_and_texts_into_one_page():
    html = build_web.inline_assets((SRC / "index.html").read_text(encoding="utf-8"))
    assert 'href="style.css"' not in html and 'src="i18n.js"' not in html
    assert ":root {" in html and "const TEXT = {" in html
    assert html.index("const TEXT = {") < html.index('const LANG_KEY')      # texts load before the main code
    assert build_web.PLAIN_TAG in html                                     # data.js still swapped by the build


def test_inline_refuses_a_missing_tag(tmp_path):
    with pytest.raises(AssertionError):
        build_web.inline_assets("<html></html>")


def test_inline_refuses_a_closing_tag_inside_a_file(tmp_path):
    (tmp_path / "style.css").write_text("a{}</style><script>alert(1)</script>", encoding="utf-8")
    (tmp_path / "i18n.js").write_text("const TEXT = {};", encoding="utf-8")
    page = '<link rel="stylesheet" href="style.css"><script src="i18n.js"></script>'
    with pytest.raises(AssertionError):
        build_web.inline_assets(page, tmp_path)


def text_keys():
    """{'de': {...}, 'en': {...}}: the keys of the TEXT registry in i18n.js."""
    js = (SRC / "i18n.js").read_text(encoding="utf-8")
    body = js[js.index("const TEXT = {"):]
    blocks = re.split(r"^  (de|en): \{$", body, flags=re.M)
    return {blocks[i]: set(re.findall(r"(?:^|,)\s*([A-Za-z]\w*):\s*[\"`(]", blocks[i + 1], re.M))
            for i in range(1, len(blocks), 2)}


def test_every_text_exists_in_both_languages():
    keys = text_keys()
    assert set(keys) == {"de", "en"}
    assert len(keys["de"]) > 100
    assert keys["de"] - keys["en"] == set(), "only in German"
    assert keys["en"] - keys["de"] == set(), "only in English"


def test_texts_used_in_the_page_exist():
    html = (SRC / "index.html").read_text(encoding="utf-8")
    used = set(re.findall(r'\bt\("([A-Za-z]\w*)"\)', html)) | set(re.findall(r'data-i18n="([A-Za-z]\w*)"', html))
    used |= {k for spec in re.findall(r'data-i18n-attr="([^"]+)"', html) for k in re.findall(r":(\w+)", spec)}
    missing = used - text_keys()["de"]
    assert not missing, f"labels without a text: {sorted(missing)}"
