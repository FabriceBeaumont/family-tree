"""Clean the Ahnenblatt CSV export into a normalised copy (the start of an own data model).

Usage:
    python src/clean_csv.py                -> data/cleaned/family_tree_cleaned.csv
    python src/clean_csv.py path/to.csv

Writes (all inside the private, gitignored data/ folder):
    family_tree_cleaned.csv   UTF-8 (with BOM, for Excel), tab separated, same columns + new ones
    cleaning_changes.csv      every automatic change: person, column, before, after, rule
    cleaning_review.csv       values that need a human decision (left unchanged in the clean copy)

Generic rules live here. Data-specific input stays private in data/cleaned/ so no family data
enters git: manual_fixes.tsv (owner decisions: id, column, original, corrected) and
place_countries.tsv (place -> ISO country code, written to <place column>.CTRY) and
new_people.tsv (people known only from notes: id + any CSV columns, parents as I-numbers).

Date format in the clean copy: ISO 8601 with reduced precision - "1900", "1900-05", "1900-05-17".
The viewer renders them per language ("im Jahr 1900" / "in the year 1900").
"""
from __future__ import annotations

import argparse
import csv
import difflib
import fnmatch
import re
import uuid
from pathlib import Path

from build_web import DEFAULT_CSV, ROOT, read_rows

OUT = ROOT / "data" / "cleaned"
MONTHS = {m: i for i, names in enumerate([
    ("januar", "jänner", "january"), ("februar", "february"), ("märz", "maerz", "march"), ("april",),
    ("mai", "may"), ("juni", "june"), ("juli", "july"), ("august",), ("september",), ("oktober", "october"),
    ("november",), ("dezember", "december")], 1) for m in names}
DATE_COLS = re.compile(r"^(BIRT|DEAT|CHR|BURI|CONF)\.DATE$|^MARR\.DATE\.\d$")
PLACE_COLS = re.compile(r"\.PLAC(\.\d)?$")
NAME_PLACEHOLDERS = {"...", '"..."', "?", "(Geb.name unbek.)", "Geb.name unbek.", "(unleserlich)"}
TITLE_RE = re.compile(r",?\s*\b(Prof\.|Dr\.(?:\s?(?:med|jur|phil|rer\. nat)\.?)?)(?=\s|,|$)")
RELIGION = {"ev.-luth.": "ev.-luth.", "ev.luth.": "ev.-luth.", "kath.": "kath.", "röm. kath": "kath."}
GEN_NUMBER = re.compile(r"\s*\bGeneration [IVX]+\b(\s+\d+)?")   # "Generation IV 7"
PHONE = re.compile(r"^Tel\.\s*(.+)$")                                # "Tel. 0123-456789"
DIVORCE = re.compile(r"^(?:geschieden|Scheidung(?: am (.+))?)$")
VEREHEL = re.compile(r"^verehel\.\s+([^\s,]+)\s*,?\s*(.*)$")        # name of a former spouse / partner
CHILD_COUNT = re.compile(r",?\s*\b\d+ Kinder\b")
# NOTE categories: (name, regex, suggestion)
NOTE_KINDS = [
    ("Wohnort", re.compile(r"^Wohnort:\s*(.+)$"), "moved to ADDR.LAST"),
    ("Spitzname / Rufname", re.compile(r'^"[^"]+"$|genannt|gerufen|^[A-ZÄÖÜ][a-zäöüé]+$'), "→ Rufname / Spitzname column"),
    ("Ehe-/Geburtsname", re.compile(r"\b(verh\.|verehel\.|verw\.|geb\.)"), "→ married/birth name column"),
    ("Adresse / Telefon", re.compile(r"str\.|straße|straße|Tel\.|\b\d{5}\b|www\.", re.I), "privacy: address/phone of (possibly living) people"),
    ("Tod / Krieg", re.compile(r"gefallen|gestorben|vermisst", re.I), "→ death cause / circumstances"),
    ("Scheidung", re.compile(r"geschieden|Scheidung", re.I), "→ divorce on the family"),
    ("Aufgabe / zu klären", re.compile(r"erfragen|klären|überprüfen", re.I), "→ to-do list, not a note"),
    ("Alternative", re.compile(r"^oder |könnte auch", re.I), "→ alternative value of another field"),
    ("Kinderzahl", re.compile(r"\bKinder?\b|Sohn|Töchter|\d\. Kind|drittes Kind", re.I), "derivable from the tree, or keep"),
]


class Cleaner:
    def __init__(self, fixes: list[tuple[str, str, str]]):
        self.fixes = fixes
        self.changes: list[dict] = []
        self.review: list[dict] = []

    def change(self, pid, col, before, after, rule):
        if before != after:
            self.changes.append({"id": pid, "column": col, "before": before, "after": after, "rule": rule})

    def ask(self, pid, col, value, problem, suggestion=""):
        self.review.append({"id": pid, "column": col, "value": value, "problem": problem, "suggestion": suggestion})

    def apply_manual(self, pid: str, row: dict) -> None:
        """Owner decisions from manual_fixes.tsv, applied to the raw values before the automatic rules."""
        for fid, pattern, original, corrected in self.fixes:
            if fid not in ("*", pid):
                continue
            append, remove = pattern.endswith("+"), pattern.endswith("-")
            pattern = pattern.rstrip("+-")
            targets = [c for c in row if fnmatch.fnmatch(c, pattern)] if any(ch in pattern for ch in "*?[") else [pattern]
            for col in targets:
                old = row.get(col) or ""
                if remove:                                    # drop one line, e.g. from NOTE
                    kept = [x for x in old.split("\r") if x != original]
                    new = "\r".join(kept)
                    if new != old:
                        self.change(pid, col, old, new, "manual fix (line removed)")
                        row[col] = new
                    continue
                if original != "*" and old != original:
                    continue
                new = "\r".join(x for x in (old, corrected) if x) if append else corrected
                if new != old:
                    self.change(pid, col, old, new, "manual fix")
                    row[col] = new

    # ---------- dates ----------
    def date(self, pid, col, v, row) -> str:
        if not v:
            return v
        s = v.strip()
        qual = ""
        m = re.fullmatch(r"(.*?)\s*(\(\?\)|\?)", s)
        if m and m[1]:
            s, qual = m[1], "uncertain"
        iso = self.parse_date(s)
        if iso is None and s.lower() in ("?", "unbekannt"):
            self.change(pid, col, v, "", "unknown date -> empty")
            return ""
        if iso is None:
            m = re.fullmatch(r"(\d{1,2}\.\d{1,2}\.\d{4})\s+(.+)", s)   # date followed by an explanation
            if m and "oder" not in m[2]:
                iso = self.parse_date(m[1])
                row["NOTE"] = "\r".join(x for x in (row.get("NOTE", ""), m[2]) if x)
                self.change(pid, col, v, iso, "date + text: text moved to NOTE")
                self.ask(pid, col, v, "text after the date was moved to NOTE", "confirm")
            else:
                self.ask(pid, col, v, "date not understood / ambiguous", "decide the date, move the rest to NOTE")
                return v
        else:
            self.change(pid, col, v, iso, "date -> ISO" + (" + uncertain" if qual else ""))
        if qual:
            row[col + ".QUAL"] = qual
        return iso

    @staticmethod
    def parse_date(s: str) -> str | None:
        if m := re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s):
            return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
        if m := re.fullmatch(r"(?:im\s+jahre?\s+)?(\d{4})", s, re.I):
            return m[1]
        if m := re.fullmatch(r"(?:im\s+)?([A-Za-zäÄ]+)\s+(\d{4})", s, re.I):
            if m[1].lower() in MONTHS:
                return f"{m[2]}-{MONTHS[m[1].lower()]:02d}"
        return None

    # ---------- places ----------
    def place(self, pid, col, v, row) -> str:
        if not v:
            return v
        if m := re.fullmatch(r"(.*?)\s*(\(\?\)|\?)", v):
            row[col + ".QUAL"] = "uncertain"
            self.change(pid, col, v, m[1], "place + '?' -> uncertain")
            v = m[1]
        if m := re.fullmatch(r"(.*\D)\s+(\d+)", v):          # Bohemian house numbers: "Dorf 24"
            row[col.replace("PLAC", "ADDR")] = m[2]
            self.change(pid, col, v, m[1], "house number -> ADDR")
            v = m[1]
            for fid, pattern, original, corrected in self.fixes:   # fixes for the bare place name
                if fid == "*" and original == v and fnmatch.fnmatch(col, pattern):
                    self.change(pid, col, v, corrected, "manual fix")
                    v = corrected
        if re.search(r"\(\d\.\s?Ehe\)", v):
            self.ask(pid, col, v, "marriage info inside a place", "drop '(2.Ehe)', marriage is already numbered")
        return v

    # ---------- names ----------
    def name_part(self, pid, col, v, row) -> str:
        if v in NAME_PLACEHOLDERS:
            self.change(pid, col, v, "", "placeholder -> empty")
            if "unleserlich" in v:
                row["NOTE"] = "\r".join(x for x in (row.get("NOTE", ""), "Nachname unleserlich") if x)
            return ""
        titles = [t.strip() for t in TITLE_RE.findall(v)]
        if titles:
            new = re.sub(r"\s{2,}", " ", TITLE_RE.sub("", v)).strip(" ,")
            row["TITL"] = " ".join(filter(None, [row.get("TITL", ""), *titles]))
            self.change(pid, col, v, new, "title -> TITL")
            v = new
        if "(" in v:
            self.ask(pid, col, v, "alternative or nickname in brackets",
                     "brackets = other spelling/name? -> alt-name column; nickname -> Rufname")
        if col == "GIVN" and v.endswith(","):
            self.ask(pid, col, v, "given name ends with a comma (surname typed into the given-name field?)",
                     "check against the source")
        elif col == "GIVN" and "," in v:
            self.ask(pid, col, v, "comma inside given names", "remove comma or split into call name")
        if re.search(r"\b[A-Z][a-z]?\.$", v):
            self.ask(pid, col, v, "abbreviated name", "write out")
        return v


def clean(rows: list[dict[str, str]], fixes, countries: dict[str, str],
          new_people: list[dict[str, str]] = (), review_notes: bool = False) -> tuple[list[dict], list[str], Cleaner]:
    c = Cleaner(fixes)
    divorces: list[tuple[str, str]] = []                     # (person id, ISO date or "")
    rows = list(rows)
    for np in new_people:                                    # owner-added people, Ahnenblatt-style row
        row = {col: "" for col in rows[0]}
        row.update({k: v for k, v in np.items() if v})
        row["#REFN"] = "@" + np["id"] + "@"
        for k in ("FATH.#REFN", "MOTH.#REFN"):
            if row.get(k) and not row[k].startswith("@"):
                row[k] = "@" + row[k] + "@"
        row["_UID"] = row.get("_UID") or new_uid()
        row.pop("id", None)
        rows.append(row)
        c.change(np["id"], "#REFN", "", row["#REFN"], "new person (new_people.tsv)")
    no_country: dict[str, int] = {}
    cols = list(rows[0].keys())
    out = []
    for r in rows:
        row = dict(r)
        pid = row["#REFN"].strip("@")
        for col, v in r.items():                               # whitespace everywhere
            if v is None:
                continue
            if col == "NOTE":
                new = "\r".join(line.strip() for line in v.split("\r")).strip()
            else:
                new = re.sub(r"\s{2,}", " ", v).strip()
            new = re.sub(r",(?=\S)", ", ", new) if col == "OCCU" else new
            new = new.rstrip(",").strip() if col == "OCCU" else new
            if new != v:
                c.change(pid, col, v, new, "whitespace / punctuation")
            row[col] = new
        c.apply_manual(pid, row)
        for col in ("GIVN", "SURN"):
            row[col] = c.name_part(pid, col, row[col], row)
        for col in cols:
            if DATE_COLS.match(col):
                row[col] = c.date(pid, col, row[col], row)
            elif PLACE_COLS.search(col):
                had = bool(row[col])
                row[col] = c.place(pid, col, row[col], row)
                if had and row[col] in countries:
                    row[col + ".CTRY"] = countries[row[col]]
                elif had:
                    no_country[row[col]] = no_country.get(row[col], 0) + 1
        if row.get("RELI"):
            new = RELIGION.get(row["RELI"])
            if new is None:
                c.ask(pid, "RELI", row["RELI"], "unknown religion value")
            else:
                c.change(pid, "RELI", row["RELI"], new, "religion spelling")
                row["RELI"] = new
        if row.get("NOTE"):                                          # phone numbers and divorces
            kept = []
            for line in row["NOTE"].split("\r"):
                if m := PHONE.match(line):
                    row["PHON"] = "; ".join(x for x in (row.get("PHON", ""), m[1].strip()) if x)
                    c.change(pid, "NOTE", line, "", "'Tel. X' -> PHON")
                elif m := DIVORCE.match(line):
                    divorces.append((pid, c.parse_date(m[1]) if m[1] else ""))
                    c.change(pid, "NOTE", line, "", "divorce -> FAM.DIV")
                else:
                    kept.append(line)
            row["NOTE"] = "\r".join(kept)
        if row.get("NOTE") and VEREHEL.search(row["NOTE"]):          # "verehel. Muster in Musterstadt"
            kept = []
            for line in row["NOTE"].split("\r"):
                m = VEREHEL.match(line)
                if not m:
                    kept.append(line)
                    continue
                row["SPOU.FORMER"] = "; ".join(x for x in (row.get("SPOU.FORMER", ""), m[1]) if x)
                rest = CHILD_COUNT.sub("", m[2]).strip(" ,")
                if rest:
                    kept.append(rest)
            new = "\r".join(kept)
            c.change(pid, "NOTE", row["NOTE"], new, "'verehel. X' -> SPOU.FORMER")
            row["NOTE"] = new
        if row.get("NOTE") and GEN_NUMBER.search(row["NOTE"]):      # old genealogy numbering: dropped
            lines = (GEN_NUMBER.sub("", line).strip() for line in row["NOTE"].split("\r"))
            new = "\r".join(x for x in lines if x)
            c.change(pid, "NOTE", row["NOTE"], new, "generation numbering removed")
            row["NOTE"] = new
        if note := row.get("NOTE"):
            for line in note.split("\r"):
                for kind, rx, suggestion in NOTE_KINDS:
                    m = rx.search(line)
                    if not m:
                        continue
                    if kind == "Wohnort":
                        row["ADDR.LAST"] = m[1]
                        if m[1] in countries:
                            row["ADDR.LAST.CTRY"] = countries[m[1]]
                        row["NOTE"] = "\r".join(x for x in row["NOTE"].split("\r") if x != line)
                        c.change(pid, "NOTE", line, "", "'Wohnort: X' -> ADDR.LAST")
                    elif review_notes:                  # owner accepted the remaining notes (2026-11-05)
                        c.ask(pid, "NOTE", line, f"note looks like: {kind}", suggestion)
                    break
        out.append(row)

    # derived name columns, rebuilt the way Ahnenblatt writes them: NAME = given + surname,
    # relatives' names = call name (or first given name) + surname
    by_id = {r["#REFN"]: r for r in out}
    def short(ref):
        p = by_id.get(ref)
        first = p.get("NAME._RUFNAME") or (p["GIVN"].split() or [""])[0]
        return " ".join(x for x in (first, p["SURN"]) if x) if p else ""
    for row in out:
        pid = row["#REFN"].strip("@")
        new = " ".join(x for x in (row["GIVN"], row["SURN"]) if x)
        c.change(pid, "NAME", row["NAME"], new, "derived name rebuilt")
        row["NAME"] = new
        for name_col, ref_col in [("FATH.NAME", "FATH.#REFN"), ("MOTH.NAME", "MOTH.#REFN"),
                                  *[(f"MARR.SPOU.NAME.{n}", f"MARR.SPOU.#REFN.{n}") for n in (1, 2, 3)]]:
            if row.get(ref_col):
                new = short(row[ref_col])
                c.change(pid, name_col, row[name_col], new, "derived name rebuilt")
                row[name_col] = new

    # divorce: mark the family slot on both partners (FAM.DIV.n = Y, FAM.DIV.DATE.n = ISO date)
    for pid, date in divorces:
        row = by_id["@" + pid + "@"]
        slots = [n for n in (1, 2, 3) if row.get(f"FAM.HUSB.{n}") or row.get(f"FAM.WIFE.{n}")]
        if len(slots) != 1:
            c.ask(pid, "NOTE", "geschieden", "divorce, but not exactly one marriage", "set FAM.DIV.n by hand")
            continue
        n = slots[0]
        couple = {row.get(f"FAM.HUSB.{n}"), row.get(f"FAM.WIFE.{n}")}
        for person in (row, by_id.get(row.get(f"MARR.SPOU.#REFN.{n}"))):
            if not person:
                continue
            for k in (1, 2, 3):
                if {person.get(f"FAM.HUSB.{k}"), person.get(f"FAM.WIFE.{k}")} == couple:
                    person[f"FAM.DIV.{k}"] = "Y"
                    if date:
                        person[f"FAM.DIV.DATE.{k}"] = date
                    c.change(person["#REFN"].strip("@"), f"FAM.DIV.{k}", "", "Y" + (" " + date if date else ""), "divorce")

    # places that are probably the same, spelled differently (Musterau / Musterrau)
    places = sorted({row[col] for row in out for col in cols if PLACE_COLS.search(col) and row.get(col)})
    stem = lambda s: re.split(r"[/,(]| bei | im | in ", s)[0].strip().lower()
    seen = set()
    for i, a in enumerate(places):
        for b in places[i + 1:]:
            sa, sb = stem(a), stem(b)
            if sa != sb and sa[:1] == sb[:1] and (sa, sb) not in seen and difflib.SequenceMatcher(None, sa, sb).ratio() >= 0.85:
                seen.add((sa, sb))
                c.ask("-", "*.PLAC", f"{a}  |  {b}", "similar place names", "same place? pick one spelling")
    for place, n in sorted(no_country.items(), key=lambda x: x[0].lower()):
        c.ask("-", "*.PLAC", place, f"no country known ({n}x)", "add to place_countries.tsv")
    extra = sorted({k for row in out for k in row} - set(cols))
    return out, cols + extra, c


def new_uid() -> str:
    """Ahnenblatt/PAF-style _UID: 16 random bytes + 2 checksum bytes, as 36 hex digits."""
    raw = uuid.uuid4().bytes
    a = b = 0
    for x in raw:
        a = (a + x) % 256
        b = (b + a) % 256
    return (raw + bytes([a, b])).hex().upper()


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        lines = [line for line in fh if not line.startswith("#")]
    return [{k: (v or "") for k, v in r.items()} for r in csv.DictReader(lines, delimiter="\t", quoting=csv.QUOTE_NONE)]


def read_fixes(path: Path) -> list[tuple[str, str, str, str]]:
    return [(r["id"], r["column"], r["original"], r["corrected"]) for r in read_tsv(path)]


def read_countries(path: Path) -> dict[str, str]:
    return {r["place"]: r["country"] for r in read_tsv(path)}


def write(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run(csv_path: Path = DEFAULT_CSV, review_notes: bool = False) -> list[dict[str, str]]:
    """Clean the export, write the clean copy + logs, return the cleaned rows (used by build_web.py)."""
    OUT.mkdir(parents=True, exist_ok=True)
    rows, cols, c = clean(read_rows(csv_path), read_fixes(OUT / "manual_fixes.tsv"),
                          read_countries(OUT / "place_countries.tsv"), read_tsv(OUT / "new_people.tsv"),
                          review_notes=review_notes)
    write(OUT / "family_tree_cleaned.csv", rows, cols)
    write(OUT / "cleaning_changes.csv", c.changes, ["id", "column", "before", "after", "rule"])
    write(OUT / "cleaning_review.csv", c.review, ["id", "column", "value", "problem", "suggestion"])
    print(f"cleaned: {len(rows)} people, {len(c.changes)} automatic changes, {len(c.review)} values to review")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--review-notes", action="store_true",
                    help="also list notes that look like they belong in another field (off: all notes accepted)")
    args = ap.parse_args()
    run(args.csv, args.review_notes)


if __name__ == "__main__":
    main()
