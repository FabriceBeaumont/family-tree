"""Build the family tree viewer from an Ahnenblatt CSV export.

Usage:
    python src/build_web.py              -> web/     (plain data, private: zip to share)
    python src/build_web.py --publish    -> public/  (password-encrypted, safe to commit)
    python src/build_web.py --raw        use the Ahnenblatt export as is, without cleaning

By default the export is first cleaned by clean_csv.py (ISO dates, countries, nicknames, addresses,
owner decisions from data/cleaned/), and the viewer is built from that clean copy.

Reads  data/ahnenblatt/*.csv  (Ahnenblatt CSV export: UTF-16, tab separated,
GEDCOM-style column names). The data is a JS file (not JSON) so index.html also
works when opened directly from disk (file://), where browsers block fetch().
--publish asks for a password (or reads FAMILY_TREE_PASSWORD) and needs the
`cryptography` package (pip install -r requirements.txt).
"""
from __future__ import annotations

import argparse
import base64
import csv
import getpass
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
DEFAULT_CSV = ROOT / "data" / "ahnenblatt" / "2023_05_StammbaumFBeaumont.csv"
WEB = ROOT / "web"
PUBLIC = ROOT / "public"

# CSV column -> output key for the detail panel
DETAIL_FIELDS = {
    "BIRT.DATE": "birthDate",
    "BIRT.PLAC": "birthPlace",
    "DEAT.DATE": "deathDate",
    "DEAT.PLAC": "deathPlace",
    "CHR.DATE": "chrDate",
    "CHR.PLAC": "chrPlace",
    "BURI.DATE": "burialDate",
    "BURI.PLAC": "burialPlace",
    "OCCU": "occupation",
    "RELI": "religion",
    "NAME._RUFNAME": "callName",
    "NOTE": "note",
    # columns added by clean_csv.py
    "NICK": "nick",
    "TITL": "title",
    "PHON": "phone",
    "ADDR.LAST": "addrLast",
    "ADDR.LAST.CTRY": "addrLastCountry",
    "BIRT.PLAC.CTRY": "birthCountry",
    "DEAT.PLAC.CTRY": "deathCountry",
    "CHR.PLAC.CTRY": "chrCountry",
    "BURI.PLAC.CTRY": "burialCountry",
    "BIRT.ADDR": "birthAddr",
    "DEAT.ADDR": "deathAddr",
    "BIRT.DATE.QUAL": "birthDateQual",
    "BIRT.PLAC.QUAL": "birthPlaceQual",
}
LIST_FIELDS = {"ADDR.FORMER": "addrFormer", "SPOU.FORMER": "formerSpouses"}   # several values per cell

YEAR_RE = re.compile(r"(\d{4})")

# Photos: data/img/<ID>.<ext> (e.g. I12.jpg) or the file name Ahnenblatt links in OBJE.FILE.n.
# They are embedded as data: URIs, so --publish encrypts them together with the rest of the data.
IMG = ROOT / "data" / "img"
IMG_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
PHOTO_WARN_BYTES = 800_000


def photo_entry(date: str, path: Path) -> dict:
    """{src, date?, note?} - note = caption from a text file next to the photo (I61_1899.jpg + I61_1899.txt)."""
    entry = {"src": photo_uri(path), **({"date": date} if date else {})}
    note_file = path.with_suffix(".txt")
    if note_file.is_file():
        note = note_file.read_text(encoding="utf-8-sig").strip()
        if note:
            entry["note"] = note
    return entry


# Documents (evidence: certificates, notices, letters …): data/docs/<ID>_<Title>.<ext>, any file type.
# Images are embedded so the viewer can open them; other types are only listed by title.
# An optional <same name>.txt next to a document holds its description.
DOCS = ROOT / "data" / "docs"


def doc_index(people: dict[str, dict]) -> dict[str, list[dict]]:
    """person id -> [{title, file, src?, note?}] for every file in data/docs/, sorted by file name."""
    found: dict[str, list[dict]] = {}
    files = sorted(f for f in DOCS.glob("*") if f.is_file()) if DOCS.is_dir() else []
    stems = {f.stem for f in files if f.suffix.lower() != ".txt"}
    for f in files:
        if f.suffix.lower() == ".txt" and f.stem in stems:
            continue                                      # description of another document
        m = re.match(r"(I\d+)_(.+)$", f.stem)
        if not m or m[1] not in people:
            print(f"Warning: document {f.name} matches nobody - name it <ID>_<Title>{f.suffix}")
            continue
        entry = {"title": m[2].replace("_", " "), "file": f.name}
        if f.suffix.lower() in IMG_TYPES:
            entry["src"] = photo_uri(f)
        note = f.with_suffix(".txt")
        if f.suffix.lower() != ".txt" and note.is_file() and note.read_text(encoding="utf-8-sig").strip():
            entry["note"] = note.read_text(encoding="utf-8-sig").strip()
        found.setdefault(m[1], []).append(entry)
    return found


PHOTO_DATE_RE = re.compile(r"(?:^|_)(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def _key(text: str) -> str:
    """'Müller-Lüdenscheidt' -> 'muller_ludenscheidt' (for matching file names to people)"""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def photo_index(people: dict[str, dict]) -> dict[str, list[tuple[str, Path]]]:
    """person id -> [(date, file)] for every image in data/img/, newest first.

    File names: <ID>[_<date>].<ext>  (recommended, e.g. I81_2019-06-12.jpg, I81_2019.jpg, I81.jpg)
            or  <Surname>_<Given>[_<date>].<ext>  (only if exactly one person has that name)
    Date = yyyy, yyyy-mm or yyyy-mm-dd; undated photos sort last.
    """
    by_name: dict[str, list[str]] = {}
    for pid, p in people.items():
        given = p.get("given", "")
        for g in {given, given.split(" ")[0]} - {""}:
            if p.get("surname"):
                by_name.setdefault(_key(f"{p['surname']}_{g}"), []).append(pid)
    found: dict[str, list[tuple[str, Path]]] = {}
    for f in sorted(IMG.glob("*")) if IMG.is_dir() else []:
        if not f.is_file() or f.suffix.lower() not in IMG_TYPES:
            continue
        stem = re.sub(r"_\d{1,2}$", "", f.stem)    # counter for several photos of one day: I81_2019-07_2
        m = PHOTO_DATE_RE.search(stem)
        date = "-".join(x for x in m.groups() if x) if m else ""
        head = stem[: m.start()] if m else stem
        pid = head if head in people else None
        if not pid:
            ids = sorted(set(by_name.get(_key(head), [])))
            if len(ids) == 1:
                pid = ids[0]
            elif ids:
                print(f"Warning: {f.name} matches {len(ids)} people ({', '.join(ids)}) - rename it to <ID>_<date>{f.suffix}")
                continue
        if not pid:
            print(f"Warning: {f.name} matches nobody - name it <ID>_<date>{f.suffix} (ID is shown in the viewer)")
            continue
        found.setdefault(pid, []).append((date, f))
    for items in found.values():
        items.sort(key=lambda x: x[0] or "0000", reverse=True)
    return found


def find_photo(pid: str, row: dict[str, str]) -> Path | None:
    """Photo linked by Ahnenblatt (OBJE.FILE.n, absolute paths from the original PC) if it is in data/img/."""
    for n in (1, 2, 3):
        linked = clean(row.get(f"OBJE.FILE.{n}"))
        if linked:
            c = IMG / linked.replace("\\", "/").rsplit("/", 1)[-1]
            if c.is_file() and c.suffix.lower() in IMG_TYPES:
                return c
    return None


def photo_uri(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > PHOTO_WARN_BYTES:
        print(f"Warning: {path.name} is {len(raw) // 1000} kB - a ~1200 px wide copy is plenty for the viewer.")
    return f"data:{IMG_TYPES[path.suffix.lower()]};base64,{base64.b64encode(raw).decode()}"


def clean(value: str | None) -> str:
    return (value or "").strip()


def year(date: str) -> int | None:
    m = YEAR_RE.search(date)
    return int(m.group(1)) if m else None


def ref(value: str) -> str:
    """'@I12@' -> 'I12'"""
    return value.strip().strip("@")


def read_rows(path: Path) -> list[dict[str, str]]:
    # Ahnenblatt writes UTF-16 with BOM; fall back to utf-8 for re-saved files.
    for enc in ("utf-16", "utf-8-sig", "cp1252"):
        try:
            with path.open(encoding=enc, newline="") as fh:
                return list(csv.DictReader(fh, delimiter="\t"))
        except (UnicodeError, csv.Error):
            continue
    raise SystemExit(f"Could not decode {path}")


def build(rows: list[dict[str, str]]) -> dict:
    people: dict[str, dict] = {}
    for r in rows:
        pid = ref(r["#REFN"])
        surname = clean(r.get("SURN")).strip('"')
        p = {
            "id": pid,
            "given": clean(r.get("GIVN")),
            "surname": "" if surname in ("...", "?") else surname,
            "sex": clean(r.get("SEX")) or "U",
        }
        married = clean(r.get("SURN.MARR")).strip('"')    # taken surname; "surname" stays the birth surname
        if married and married != p["surname"]:
            p["married"] = married
        for col, key in DETAIL_FIELDS.items():
            v = clean(r.get(col))
            if v:
                p[key] = v
        for col, key in LIST_FIELDS.items():
            items = [x.strip() for x in re.split(r"[\r\n;]+", r.get(col) or "") if x.strip()]
            if items:
                p[key] = items
        by, dy = year(p.get("birthDate", "")), year(p.get("deathDate", ""))
        if by:
            p["by"] = by
        if dy:
            p["dy"] = dy
        linked = find_photo(pid, r)
        if linked:
            p["_linked"] = linked
        people[pid] = p

    # photos: data/img/ files (newest first) + the photo Ahnenblatt links; card shows the newest
    index = photo_index(people)
    for pid, p in people.items():
        items = index.get(pid, [])
        linked = p.pop("_linked", None)
        if linked and all(f != linked for _, f in items):
            items.append(("", linked))
        if items:
            p["photos"] = [photo_entry(d, f) for d, f in items]
    for pid, docs in doc_index(people).items():
        people[pid]["docs"] = docs

    # Families keyed by (father, mother). Built from child->parent links first,
    # then from spouse links so childless couples also appear.
    families: dict[tuple[str, str], dict] = {}

    def family(h: str, w: str) -> dict:
        key = (h, w)
        if key not in families:
            families[key] = {"id": f"F{len(families) + 1}", "husband": h or None,
                             "wife": w or None, "children": []}
        return families[key]

    for r in rows:
        f, m = ref(r.get("FATH.#REFN", "")), ref(r.get("MOTH.#REFN", ""))
        f = f if f in people else ""
        m = m if m in people else ""
        if f or m:
            family(f, m)["children"].append(ref(r["#REFN"]))

    for r in rows:
        for n in (1, 2, 3):
            h, w = ref(r.get(f"FAM.HUSB.{n}", "")), ref(r.get(f"FAM.WIFE.{n}", ""))
            if h in people and w in people:
                fam = family(h, w)
                if clean(r.get(f"MARR.DATE.{n}")):
                    fam["marrDate"] = clean(r[f"MARR.DATE.{n}"])
                if clean(r.get(f"MARR.PLAC.{n}")):
                    fam["marrPlace"] = clean(r[f"MARR.PLAC.{n}"])
                if clean(r.get(f"MARR.PLAC.{n}.CTRY")):
                    fam["marrCountry"] = clean(r[f"MARR.PLAC.{n}.CTRY"])
                if clean(r.get(f"FAM.DIV.{n}")) == "Y":
                    fam["divorced"] = True
                    if clean(r.get(f"FAM.DIV.DATE.{n}")):
                        fam["divDate"] = clean(r[f"FAM.DIV.DATE.{n}"])
                if clean(r.get(f"FAM._STAT.{n}")) == "NOT MARRIED":
                    fam["unmarried"] = True

    fam_list = list(families.values())
    for fam in fam_list:
        # sort children by birth year where known
        fam["children"].sort(key=lambda c: people[c].get("by", 9999))
    return {"people": list(people.values()), "families": fam_list}


PBKDF2_ITERATIONS = 600_000
PLAIN_TAG = '<script src="data.js"></script>'
ENC_TAG = '<script src="data.enc.js"></script>'


def read_password() -> str:
    pw = os.environ.get("FAMILY_TREE_PASSWORD")
    if pw:
        return pw
    pw = getpass.getpass("Password for the published tree: ")
    if pw != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    if len(pw) < 12:
        print("Warning: short password. The encrypted file is public, so it can be attacked "
              "offline - a passphrase of 4+ random words is much safer.")
    return pw


def encrypt(data: dict, password: str) -> dict:
    """AES-256-GCM with a PBKDF2-SHA256 key. Decrypted in the browser via Web Crypto."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # only needed for --publish

    salt, iv = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS, dklen=32)
    ct = AESGCM(key).encrypt(iv, json.dumps(data, ensure_ascii=False).encode(), None)
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 1, "iter": PBKDF2_ITERATIONS, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", type=Path, default=DEFAULT_CSV, help="Ahnenblatt CSV export")
    ap.add_argument("--publish", action="store_true",
                    help="write a password-encrypted copy to public/ (for GitHub Pages)")
    ap.add_argument("--out", type=Path, help="output folder (default: web/, or public/ with --publish)")
    ap.add_argument("--raw", action="store_true", help="skip clean_csv.py and use the export as is")
    args = ap.parse_args()

    if args.raw:
        rows = read_rows(args.csv)
    else:
        from clean_csv import run as clean_export   # imported here: clean_csv imports this module
        rows = clean_export(args.csv)
    data = build(rows)
    html = (SRC / "index.html").read_text(encoding="utf-8")
    assert PLAIN_TAG in html, "src/index.html must load data.js via " + PLAIN_TAG
    header = "// Generated by build_web.py from " + args.csv.name + " - do not edit by hand.\n"

    if args.publish:
        out = args.out or PUBLIC
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(html.replace(PLAIN_TAG, ENC_TAG), encoding="utf-8")
        (out / "data.enc.js").write_text(
            "// Generated by build_web.py --publish (encrypted).\n"
            "window.FAMILY_DATA_ENC = " + json.dumps(encrypt(data, read_password())) + ";\n",
            encoding="utf-8")
    else:
        out = args.out or WEB
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(html, encoding="utf-8")
        (out / "data.js").write_text(
            header + "window.FAMILY_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
            encoding="utf-8")
    photos = sum(len(p.get("photos", [])) for p in data["people"])
    docs = sum(len(p.get("docs", [])) for p in data["people"])
    print(f"{len(data['people'])} people, {len(data['families'])} families, {photos} photos, {docs} documents -> {out}"
          + (" (encrypted)" if args.publish else ""))


if __name__ == "__main__":
    main()
