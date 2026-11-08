"""The public DEMO (made-up family in sample/, built with --sample): complete, separate, and private-data-free."""
import hashlib
import json
import re

import pytest

import build_web
import clean_csv
from conftest import components


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """Build the demo into a temporary folder; data/ must not be touched (clean_csv.OUT points nowhere)."""
    monkeypatch.setattr(build_web, "IMG", build_web.IMG)      # build_sample switches these: restore afterwards
    monkeypatch.setattr(build_web, "DOCS", build_web.DOCS)
    monkeypatch.setattr(clean_csv, "OUT", tmp_path / "must-not-be-used")
    build_web.build_sample(tmp_path / "demo")
    assert not (tmp_path / "must-not-be-used").exists()
    js = (tmp_path / "demo" / "data.js").read_text(encoding="utf-8")
    data = json.loads(js[js.index("{"):js.rindex("}") + 1])
    return data, (tmp_path / "demo" / "index.html").read_text(encoding="utf-8")


def test_demo_is_marked_and_uses_its_own_browser_storage(demo):
    data, html = demo
    assert data["demo"] is True                             # the Pages workflow checks this marker
    assert f'data-store="{build_web.DEMO_STORE}"' in html and "data-demo" in html
    assert 'src="data.js"' in html                           # plain, no password


def test_demo_family_is_one_tree_with_photos_and_documents(demo):
    data, _ = demo
    assert len(data["people"]) >= 40
    assert len(components(data)) == 1
    people = {p["id"]: p for p in data["people"]}
    assert sum(len(p.get("photos", [])) for p in data["people"]) >= 10
    docs = [d for p in data["people"] for d in p.get("docs", [])]
    assert any("src" in d for d in docs) and any("src" not in d for d in docs)   # image + listed-only PDF
    assert any(f.get("divorced") for f in data["families"]) and any(f.get("unmarried") for f in data["families"])
    assert people["I21"]["title"] == "Dr. med. dent." and people["I33"]["nick"] == "root"


def test_viewer_keeps_every_storage_key_under_the_prefix():
    html = (build_web.SRC / "index.html").read_text(encoding="utf-8")
    code = re.sub(r"//.*", "", html)                         # comments may mention the names
    assert not re.search(r"[\"']stammbaum-", code), "use STORE + \"-…\" for browser storage keys"


REAL_CSV = build_web.ROOT / "data" / "cleaned" / "family_tree_cleaned.csv"


@pytest.mark.skipif(not REAL_CSV.exists(), reason="private data not present (public checkout)")
def test_demo_shares_no_name_with_the_real_tree(demo):
    data, _ = demo
    real = {(r["GIVN"].split(" ")[0], r["SURN"]) for r in build_web.read_rows(REAL_CSV) if r.get("SURN")}
    shared = {(p["given"].split(" ")[0], p["surname"]) for p in data["people"]} & real
    assert not shared, f"demo names that also exist in the real tree: {shared}"


REAL_MEDIA = [build_web.ROOT / "data" / "img", build_web.ROOT / "data" / "docs"]


@pytest.mark.skipif(not REAL_MEDIA[0].exists(), reason="private data not present (public checkout)")
def test_demo_contains_no_real_photo_or_document():
    digest = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
    real = {digest(f) for d in REAL_MEDIA if d.exists() for f in d.iterdir() if f.is_file()}
    demo = {f.name: digest(f) for d in ("img", "docs") for f in (build_web.SAMPLE / d).iterdir()}
    assert not {name for name, h in demo.items() if h in real}
