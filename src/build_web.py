"""Build the family tree viewer from an Ahnenblatt CSV export.

Usage:
    python src/build_web.py              -> web/     (plain data, private: zip to share)
    python src/build_web.py --publish    -> public/  (password-encrypted, safe to commit)

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
}

YEAR_RE = re.compile(r"(\d{4})")


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
        for col, key in DETAIL_FIELDS.items():
            v = clean(r.get(col))
            if v:
                p[key] = v
        by, dy = year(p.get("birthDate", "")), year(p.get("deathDate", ""))
        if by:
            p["by"] = by
        if dy:
            p["dy"] = dy
        people[pid] = p

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
    args = ap.parse_args()

    data = build(read_rows(args.csv))
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
    print(f"{len(data['people'])} people, {len(data['families'])} families -> {out}"
          + (" (encrypted)" if args.publish else ""))


if __name__ == "__main__":
    main()
