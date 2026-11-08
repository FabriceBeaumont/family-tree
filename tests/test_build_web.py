"""Building the viewer data (src/build_web.py): families, photos, documents, one connected tree."""
from pathlib import Path

import pytest

import build_web
from clean_csv import clean
from conftest import components


@pytest.fixture
def media(tmp_path, monkeypatch):
    """Empty photo and document folders instead of data/img and data/docs."""
    img, docs = tmp_path / "img", tmp_path / "docs"
    img.mkdir()
    docs.mkdir()
    monkeypatch.setattr(build_web, "IMG", img)
    monkeypatch.setattr(build_web, "DOCS", docs)
    return img, docs


def built(family, fixes=()):
    rows, _, _ = clean(list(family.values()), list(fixes), {}, [])
    return build_web.build(rows)


def by_id(data):
    return {p["id"]: p for p in data["people"]}


def test_families_children_and_marriage(family, media):
    data = built(family)
    parents = next(f for f in data["families"] if f["husband"] == "I1")
    assert parents["wife"] == "I2"
    assert parents["children"] == ["I3", "I7"]             # oldest first
    assert parents["marrDate"] == "1925-05-10"
    p = by_id(data)
    assert p["I3"]["by"] == 1926 and p["I2"]["married"] == "Muster"


def test_duplicates_and_strays_split_the_tree_until_fixed(family, media):
    assert len(components(built(family))) == 3             # main family, Karl's duplicate + Lina, the stray
    fixed = built(family, [("I4", "#MERGE", "*", "I3"), ("I6", "#DELETE", "*", "")])
    assert len(components(fixed)) == 1


def test_photos_by_id_and_year_newest_first_with_caption(family, media):
    img, _ = media
    for name in ("I1_1925.jpg", "I1_1950-07.jpg", "I1.jpg", "Nobody_1900.jpg"):
        (img / name).write_bytes(b"\xff\xd8 fake jpeg")
    (img / "I1_1925.txt").write_text("Hochzeit", encoding="utf-8")
    photos = by_id(built(family, [("I6", "#DELETE", "*", "")]))["I1"]["photos"]
    assert [ph.get("date") for ph in photos] == ["1950-07", "1925", None]
    assert photos[1]["note"] == "Hochzeit"
    assert photos[0]["src"].startswith("data:image/jpeg;base64,")


def test_documents_are_separate_from_photos(family, media):
    img, docs = media
    (img / "I1_1925.jpg").write_bytes(b"\xff\xd8 photo")
    (docs / "I1_Geburtsurkunde_1900.jpg").write_bytes(b"\xff\xd8 scan")
    (docs / "I1_Geburtsurkunde_1900.txt").write_text("Standesamt Saarlouis", encoding="utf-8")
    (docs / "I1_Brief.pdf").write_bytes(b"%PDF-1.4")
    (docs / "I99_Fremd.pdf").write_bytes(b"%PDF-1.4")        # nobody with that id: skipped
    p = by_id(built(family))["I1"]
    assert len(p["photos"]) == 1
    assert [d["title"] for d in p["docs"]] == ["Brief", "Geburtsurkunde 1900"]
    pdf, scan = p["docs"]
    assert "src" not in pdf and pdf["file"] == "I1_Brief.pdf"   # other types: listed only
    assert scan["src"].startswith("data:image/jpeg;base64,") and scan["note"] == "Standesamt Saarlouis"


REAL = build_web.ROOT / "data" / "cleaned" / "family_tree_cleaned.csv"


@pytest.mark.skipif(not REAL.exists(), reason="private data not present (public checkout)")
def test_the_real_tree_is_one_connected_graph(media):
    """Guards the owner's goal: one big graph, no loose groups (run `python src/build_web.py` first)."""
    rows = build_web.read_rows(REAL)
    groups = sorted(components(build_web.build(rows)), key=len)
    loose = [sorted(g) for g in groups[:-1]]
    assert not loose, f"people not connected to the main tree: {loose}"
