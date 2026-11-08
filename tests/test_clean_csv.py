"""Cleaning rules (src/clean_csv.py): dates, owner fixes, deleting and merging people."""
import pytest

from clean_csv import Cleaner, clean

COUNTRIES = {"Saarlouis": "DE"}


def run(family, fixes=(), new_people=()):
    rows, cols, c = clean(list(family.values()), list(fixes), COUNTRIES, list(new_people))
    return {r["#REFN"].strip("@"): r for r in rows}, c


@pytest.mark.parametrize("raw, iso", [
    ("17.06.1891", "1891-06-17"),
    ("6.5.1813", "1813-05-06"),
    ("1814", "1814"),
    ("im Jahr 1814", "1814"),
    ("August 1873", "1873-08"),
    ("im März 1920", "1920-03"),
    ("1936-10-17", "1936-10-17"),      # already ISO (from the edit mode)
    ("1873-08", "1873-08"),
    ("irgendwann", None),
])
def test_parse_date(raw, iso):
    assert Cleaner.parse_date(raw) == iso


def test_question_mark_makes_a_date_uncertain():
    c, row = Cleaner([]), {}
    assert c.date("I1", "DEAT.DATE", "29.09.1857?", row) == "1857-09-29"
    assert row["DEAT.DATE.QUAL"] == "uncertain"


def test_dates_places_and_religion_are_normalised(family):
    rows, _ = run(family)
    assert rows["I1"]["BIRT.DATE"] == "1900-02-01"
    assert rows["I1"]["BIRT.PLAC.CTRY"] == "DE"
    assert rows["I2"]["RELI"] == "ev."
    assert rows["I1"]["MARR.DATE.1"] == "1925-05-10"


def test_manual_fixes_set_append_and_remove_lines(family):
    family["I3"]["NOTE"] = "erste Zeile\rzweite Zeile"
    rows, _ = run(family, [
        ("I3", "OCCU", "*", "Bäcker"),                      # any old value
        ("I3", "GIVN", "Karl", "Karl Heinz"),               # only if the old value matches
        ("I7", "GIVN", "Anna", "Gretel"),                   # does not match -> no change
        ("I3", "NOTE+", "*", "neue Zeile"),
        ("I3", "NOTE-", "zweite Zeile", ""),
    ])
    assert rows["I3"]["OCCU"] == "Bäcker"
    assert rows["I3"]["GIVN"] == "Karl Heinz"
    assert rows["I7"]["GIVN"] == "Grete"
    assert rows["I3"]["NOTE"].split("\r") == ["erste Zeile", "neue Zeile"]


def test_delete_removes_the_person_and_every_link_to_them(family):
    rows, c = run(family, [("I6", "#DELETE", "*", ""), ("I2", "#DELETE", "*", "")])
    assert "I6" not in rows and "I2" not in rows
    assert rows["I3"]["MOTH.#REFN"] == ""                  # child keeps its father only
    assert rows["I3"]["FATH.#REFN"] == "@I1@"
    assert rows["I1"]["FAM.WIFE.1"] == "" and rows["I1"]["MARR.SPOU.#REFN.1"] == ""
    assert any(ch["rule"].startswith("person deleted") for ch in c.changes)


def test_merge_folds_the_duplicate_into_the_keeper(family):
    rows, c = run(family, [("I4", "#MERGE", "*", "I3")])
    assert "I4" not in rows
    karl = rows["I3"]
    assert karl["OCCU"] == "Schlosser"                     # facts only the duplicate had
    assert karl["BIRT.PLAC"] == "Saarlouis"
    assert karl["NOTE"] == "Karli"
    assert karl["FATH.#REFN"] == "@I1@"                    # the keeper's own links stay
    slot = next(n for n in (1, 2, 3) if karl[f"FAM.WIFE.{n}"] == "@I5@")   # partnership moved over
    assert karl[f"FAM.HUSB.{slot}"] == "@I3@"
    assert karl[f"MARR.DATE.{slot}"] == "1950"
    assert rows["I5"]["FAM.HUSB.1"] == "@I3@"              # the partner's link is re-pointed
    assert rows["I5"]["MARR.SPOU.#REFN.1"] == "@I3@"


def test_merge_keeps_the_keepers_values_and_appends_a_different_note(family):
    family["I3"]["OCCU"] = "Schmied"
    family["I3"]["NOTE"] = "Bruder von Grete"
    rows, _ = run(family, [("I4", "#MERGE", "*", "I3")])
    assert rows["I3"]["OCCU"] == "Schmied"
    assert rows["I3"]["NOTE"].split("\r") == ["Bruder von Grete", "Karli"]


def test_merge_follows_chains(family):
    # I6 -> I4 -> I3: everything ends up in I3
    rows, _ = run(family, [("I6", "#MERGE", "*", "I4"), ("I4", "#MERGE", "*", "@I3@")])
    assert "I6" not in rows and "I4" not in rows and "I3" in rows


def test_merge_of_an_unknown_keeper_changes_nothing(family):
    rows, _ = run(family, [("I4", "#MERGE", "*", "I999")])
    assert "I4" in rows


def test_new_people_get_rows_and_parent_links(family):
    rows, _ = run(family, new_people=[{"id": "I900", "SEX": "F", "GIVN": "Lotte", "SURN": "Muster",
                                       "FATH.#REFN": "I3", "MOTH.#REFN": "I5", "BIRT.DATE": "12.12.1952"}])
    lotte = rows["I900"]
    assert lotte["FATH.#REFN"] == "@I3@" and lotte["MOTH.#REFN"] == "@I5@"
    assert lotte["BIRT.DATE"] == "1952-12-12"
    assert lotte["_UID"]


def test_divorce_note_marks_the_family_on_both_partners(family):
    family["I5"]["NOTE"] = "Scheidung am 01.04.1960"
    rows, _ = run(family)
    for pid in ("I4", "I5"):
        assert rows[pid]["FAM.DIV.1"] == "Y"
        assert rows[pid]["FAM.DIV.DATE.1"] == "1960-04-01"
    assert rows["I5"]["NOTE"] == ""


def test_phone_moves_out_of_the_note(family):
    family["I7"]["NOTE"] = "Tel. 0123-456789\rnett"
    rows, _ = run(family)
    assert rows["I7"]["PHON"] == "0123-456789"
    assert rows["I7"]["NOTE"] == "nett"


def test_wife_gets_the_husbands_surname_as_married_name(family):
    rows, _ = run(family)
    assert rows["I2"]["SURN"] == "Beispiel"                # birth surname stays
    assert rows["I2"]["SURN.MARR"] == "Muster"


def test_an_unmarried_partner_gives_no_surname(family):
    for pid in ("I4", "I5"):
        family[pid]["FAM._STAT.1"] = "NOT MARRIED"
    rows, _ = run(family)
    assert not rows["I5"].get("SURN.MARR")
