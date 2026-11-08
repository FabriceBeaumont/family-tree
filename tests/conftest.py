"""Shared helpers for the tests: a small, made-up family in Ahnenblatt's CSV shape.

No real family data here - the repository is public. Everything is built in memory or in pytest's
tmp_path, and module paths that point into data/ are redirected there by monkeypatch.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

# the column set of an Ahnenblatt 2.70 CSV export (same order)
COLUMNS = [
    "#REFN", "NAME", "FATH.NAME", "FATH.#REFN", "MOTH.NAME", "MOTH.#REFN", "_UID", "SEX", "GIVN", "SURN",
    "BIRT.DATE", "DEAT.DATE", "BIRT.PLAC", "DEAT.PLAC", "NOTE", "OCCU", "NAME._RUFNAME", "RELI",
    "CHR.DATE", "CHR.PLAC", "CHR.ADDR", "CHR._GODP", "BURI.DATE", "BURI.PLAC", "CONF.DATE", "CONF.ADDR", "CONF.PLAC",
    *[c for n in (1, 2, 3) for c in (f"MARR.SPOU.NAME.{n}", f"MARR.SPOU.#REFN.{n}", f"FAM.WIFE.{n}", f"FAM.MARR.{n}",
                                     f"FAM.HUSB.{n}", f"FAM.CHIL.{n}", f"MARR.DATE.{n}", f"MARR.PLAC.{n}",
                                     f"FAM._STAT.{n}", f"FAM._MARR.{n}")],
    "OBJE.FILE.1", "OBJE.TITL.1", "OBJE.FILE.2", "OBJE.TITL.2", "OBJE.FILE.3", "OBJE.TITL.3",
]


def person(pid: str, given: str, surname: str, sex: str, **cols: str) -> dict[str, str]:
    """One raw export row; keyword names use _ for . and HASH for # (FATH_HASHREFN -> FATH.#REFN)."""
    row = dict.fromkeys(COLUMNS, "")
    row.update({"#REFN": f"@{pid}@", "NAME": f"{given} {surname}", "GIVN": given, "SURN": surname, "SEX": sex})
    for key, value in cols.items():
        col = key.replace("HASH", "#").replace("_", ".")
        assert col in row, f"unknown column {col}"
        row[col] = value
    return row


def couple(h: dict, w: dict, n: int = 1, date: str = "") -> None:
    """Mark h and w as partners in family slot n on both rows (the way Ahnenblatt writes it)."""
    for me, other in ((h, w), (w, h)):
        me[f"FAM.HUSB.{n}"], me[f"FAM.WIFE.{n}"] = h["#REFN"], w["#REFN"]
        me[f"MARR.SPOU.#REFN.{n}"], me[f"MARR.SPOU.NAME.{n}"] = other["#REFN"], other["NAME"]
        me[f"MARR.DATE.{n}"] = date


def child(kid: dict, father: dict | None, mother: dict | None) -> dict:
    kid["FATH.#REFN"] = father["#REFN"] if father else ""
    kid["MOTH.#REFN"] = mother["#REFN"] if mother else ""
    return kid


@pytest.fixture
def family() -> dict[str, dict]:
    """Hans + Erna Muster with children Karl (1926) and Grete (1930); Karl is also entered a second time
    (I4, with his wife Lina I5 and his job) as a typical Ahnenblatt duplicate; I6 is a stray nobody links to."""
    hans = person("I1", "Hans", "Muster", "M", BIRT_DATE="01.02.1900", BIRT_PLAC="Saarlouis")
    erna = person("I2", "Erna", "Beispiel", "F", BIRT_DATE="1902", RELI="evangelisch")
    couple(hans, erna, date="10.05.1925")
    karl = child(person("I3", "Karl", "Muster", "M", BIRT_DATE="03.03.1926"), hans, erna)
    grete = child(person("I7", "Grete", "Muster", "F", BIRT_DATE="1930"), hans, erna)
    karl_dup = person("I4", "Karl", "Muster", "M", BIRT_DATE="03.03.1926", BIRT_PLAC="Saarlouis",
                      OCCU="Schlosser", NOTE="Karli")
    lina = person("I5", "Lina", "Probe", "F")
    couple(karl_dup, lina, date="1950")
    stray = person("I6", "...", "Fremd", "M")
    return {r["#REFN"].strip("@"): r for r in (hans, erna, karl, grete, karl_dup, lina, stray)}


def components(data: dict) -> list[set[str]]:
    """Connected groups of people in a built tree (partners, parents and children are linked)."""
    adj = {p["id"]: set() for p in data["people"]}
    for f in data["families"]:
        members = [x for x in (f["husband"], f["wife"], *f["children"]) if x]
        for a in members:
            adj[a].update(m for m in members if m != a)
    seen, groups = set(), []
    for start in adj:
        if start in seen:
            continue
        group, todo = set(), [start]
        while todo:
            x = todo.pop()
            if x not in group:
                group.add(x)
                todo.extend(adj[x] - group)
        seen |= group
        groups.append(group)
    return groups
