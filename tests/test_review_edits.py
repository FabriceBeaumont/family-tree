"""Reviewing change files from the viewer's edit mode (src/review_edits.py), all in a temporary folder."""
import base64
import sys
import zipfile

import pytest

import review_edits as rv

HEADER = "action\tid\tcolumn\toriginal\tcorrected"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A fake data/ folder: inbox, fix files, the cleaned copy (current values) and the export (used ids)."""
    cleaned = tmp_path / "cleaned"
    (cleaned / "inbox").mkdir(parents=True)
    (cleaned / "manual_fixes.tsv").write_text("id\tcolumn\toriginal\tcorrected\n", encoding="utf-8")
    (cleaned / "family_tree_cleaned.csv").write_text(
        "#REFN\tGIVN\tSURN\tBIRT.DATE\tFATH.#REFN\n@I1@\tHans\tMuster\t1900\t\n@I2@\tErna\tBeispiel\t1902\t\n",
        encoding="utf-8-sig")
    export = tmp_path / "export.csv"
    export.write_text("#REFN\tGIVN\n@I1@\tHans\n@I2@\tErna\n", encoding="utf-8")
    paths = {"ROOT": tmp_path, "INBOX": cleaned / "inbox", "FIXES": cleaned / "manual_fixes.tsv",
             "NEW_PEOPLE": cleaned / "new_people.tsv", "CLEAN_COPY": cleaned / "family_tree_cleaned.csv",
             "IMG": tmp_path / "img", "DOCS": tmp_path / "docs", "DEFAULT_CSV": export}
    for name, value in paths.items():
        monkeypatch.setattr(rv, name, value)
    monkeypatch.setattr(sys, "argv", ["review_edits.py"])
    return paths


def answer(monkeypatch, *answers):
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))


def write_zip(path, tsv_lines, files):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(path.stem + ".tsv", "\n".join([HEADER, *tsv_lines]) + "\n")
        for name, data in files.items():
            z.writestr(name, data)


def test_zip_with_every_kind_of_change(workspace, monkeypatch):
    inbox = workspace["INBOX"]
    write_zip(inbox / "2026-01-01_10-00_edits.zip", [
        "set\tI1\tOCCU\t\tBäcker",
        "delete\tI2\t\tErna Beispiel\t",
        "new\tNEW1\tGIVN\t\tPaul",
        "new\tNEW1\tSURN\t\tMuster",
        "new\tNEW1\tFATH.#REFN\t\tI1",
        "photo\tI1\t1925\tI1_1925.jpg\tHochzeit\\nin Saarlouis",
        "photo\tNEW1\t\tNEW1.jpg\t",
        "doc\tI1\t\tI1_Brief_1925.pdf\tBrief 1925",
    ], {"I1_1925.jpg": b"\xff\xd8 wedding", "NEW1.jpg": b"\xff\xd8 baby", "I1_Brief_1925.pdf": b"%PDF-1.4"})
    answer(monkeypatch, *["y"] * 6)        # new person, set, delete, 2 photos, document
    rv.main()

    fixes = workspace["FIXES"].read_text(encoding="utf-8")
    assert "I1\tOCCU\t*\tBäcker" in fixes
    assert "I2\t#DELETE\t*\t" in fixes
    people = workspace["NEW_PEOPLE"].read_text(encoding="utf-8")
    assert "I3\tPaul\tMuster\tI1" in people              # NEW1 got the next free id
    img, docs = workspace["IMG"], workspace["DOCS"]
    assert (img / "I1_1925.jpg").read_bytes() == b"\xff\xd8 wedding"
    assert (img / "I1_1925.txt").read_text(encoding="utf-8") == "Hochzeit\nin Saarlouis"
    assert (img / "I3.jpg").read_bytes() == b"\xff\xd8 baby"   # photo of the new person, with its real id
    assert (docs / "I1_Brief_1925.pdf").read_bytes() == b"%PDF-1.4"
    assert (inbox / "done" / "2026-01-01_10-00_edits.zip").exists()
    assert not (inbox / "2026-01-01_10-00_edits").exists()     # unpacked copy removed
    assert not list(inbox.glob("*.zip"))


def test_rejected_changes_leave_everything_as_it_was(workspace, monkeypatch):
    write_zip(workspace["INBOX"] / "2026-01-01_11-00_edits.zip",
              ["set\tI1\tOCCU\t\tBäcker", "photo\tI1\t1925\tI1_1925.jpg\t"], {"I1_1925.jpg": b"x"})
    answer(monkeypatch, "n", "n")
    rv.main()
    assert "Bäcker" not in workspace["FIXES"].read_text(encoding="utf-8")
    assert not workspace["IMG"].exists() or not list(workspace["IMG"].iterdir())


def test_existing_photo_is_never_overwritten(workspace, monkeypatch):
    img = workspace["IMG"]
    img.mkdir()
    (img / "I1_1925.jpg").write_bytes(b"old")
    write_zip(workspace["INBOX"] / "2026-01-01_12-00_edits.zip",
              ["photo\tI1\t1925\tI1_1925.jpg\t"], {"I1_1925.jpg": b"new"})
    answer(monkeypatch, "y")
    rv.main()
    assert (img / "I1_1925.jpg").read_bytes() == b"old"
    assert (img / "I1_1925_2.jpg").read_bytes() == b"new"


def test_loose_tsv_with_photo_next_to_it_and_old_inline_photos(workspace, monkeypatch):
    inbox = workspace["INBOX"]
    (inbox / "I1_1930.jpg").write_bytes(b"loose")
    inline = "data:image/jpeg;base64," + base64.b64encode(b"inline").decode()
    (inbox / "2026-01-01_13-00_edits.tsv").write_text("\n".join([
        HEADER,
        "photo\tI1\t1930\tI1_1930.jpg\t",
        "photo\tI1\t1940\tscan.jpg\t" + inline,          # change file from before the zip download
        "photo\tI1\t1950\tmissing.jpg\t",                 # not there: skipped, no question
    ]) + "\n", encoding="utf-8")
    answer(monkeypatch, "y", "y")
    rv.main()
    img = workspace["IMG"]
    assert (img / "I1_1930.jpg").read_bytes() == b"loose"
    assert (img / "I1_1940.jpg").read_bytes() == b"inline"
    assert not (img / "I1_1950.jpg").exists()
    assert (inbox / "done" / "2026-01-01_13-00_edits.tsv").exists()


def test_quit_keeps_the_change_file_in_the_inbox(workspace, monkeypatch):
    tsv = workspace["INBOX"] / "2026-01-01_14-00_edits.tsv"
    tsv.write_text(HEADER + "\nset\tI1\tOCCU\t\tBäcker\n", encoding="utf-8")
    answer(monkeypatch, "q")
    rv.main()
    assert tsv.exists()
    assert "Bäcker" not in workspace["FIXES"].read_text(encoding="utf-8")


def test_unpack_ignores_folders_and_paths_inside_the_zip(tmp_path):
    archive = tmp_path / "x_edits.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../../evil.tsv", "a")
        z.writestr("sub/I1.jpg", "b")
        z.writestr("not a photo.exe.", "c")
    folder = rv.unpack(archive)
    assert sorted(p.name for p in folder.iterdir()) == ["I1.jpg", "evil.tsv"]
    assert not (tmp_path.parent / "evil.tsv").exists()
