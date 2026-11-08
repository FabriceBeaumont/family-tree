"""Review change files from the viewer's edit mode before anything is published.

Usage:
    python src/review_edits.py            review every file in data/cleaned/inbox/
    python src/review_edits.py --list     only show what is waiting, change nothing

Workflow:
    1. In the viewer switch on ✏️, edit, then download the change file.
    2. Put the downloaded <date>_<time>_edits.tsv into data/cleaned/inbox/.
    3. Run this script: every change is shown (current value -> new value); answer
       y = accept, n = reject, q = stop (the rest stays in the inbox for later).
    4. Accepted changes are appended to data/cleaned/manual_fixes.tsv (field changes) and
       data/cleaned/new_people.tsv (new people, with real I-numbers). The file moves to inbox/done/.
    5. Check the result with `python src/build_web.py`, then publish as usual.

Change file columns: action (set | new | photo | delete), id, column, original, corrected.
Delete rows: original = the person's name; an accepted one becomes `<id>  #DELETE` in manual_fixes.tsv,
which makes clean_csv.py drop the person and every link to them.
Photo rows: column = date (may be empty), original = original file name, corrected = data: URL (JPEG);
accepted photos are saved as data/img/<ID>_<date>.jpg (or <ID>.jpg; a _2, _3 … suffix avoids overwriting).
New people use temporary ids NEW1, NEW2 … which get the next free I-numbers here.
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime
import re
import shutil
from pathlib import Path

from build_web import DEFAULT_CSV, read_rows

ROOT = Path(__file__).resolve().parent.parent
CLEANED = ROOT / "data" / "cleaned"
INBOX = CLEANED / "inbox"
FIXES = CLEANED / "manual_fixes.tsv"
NEW_PEOPLE = CLEANED / "new_people.tsv"
CLEAN_COPY = CLEANED / "family_tree_cleaned.csv"
IMG = ROOT / "data" / "img"


def save_photo(pid: str, date: str, data_url: str) -> Path:
    raw = base64.b64decode(data_url.split(",", 1)[1])
    IMG.mkdir(parents=True, exist_ok=True)
    stem = f"{pid}_{date}" if date else pid
    target, n = IMG / f"{stem}.jpg", 2
    while target.exists():
        target, n = IMG / f"{stem}_{n}.jpg", n + 1
    target.write_bytes(raw)
    return target


def read_changes(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        lines = [line for line in fh if line.strip() and not line.startswith("#")]
    return [{k: (v or "") for k, v in r.items()} for r in csv.DictReader(lines, delimiter="\t", quoting=csv.QUOTE_NONE)]


def current_values() -> dict[str, dict[str, str]]:
    """id -> cleaned row (what the viewer shows today)."""
    if not CLEAN_COPY.exists():
        return {}
    with CLEAN_COPY.open(encoding="utf-8-sig", newline="") as fh:
        return {r["#REFN"].strip("@"): r for r in csv.DictReader(fh, delimiter="\t")}


def used_ids() -> set[str]:
    ids = {r["#REFN"].strip("@") for r in read_rows(DEFAULT_CSV)}
    if NEW_PEOPLE.exists():
        for line in NEW_PEOPLE.read_text(encoding="utf-8").splitlines()[1:]:
            if line and not line.startswith("#"):
                ids.add(line.split("\t", 1)[0])
    return ids


def next_ids(n: int) -> list[str]:
    taken = used_ids()
    nums = sorted(int(i[1:]) for i in taken if re.fullmatch(r"I\d+", i))
    start, out = (nums[-1] if nums else 0) + 1, []
    while len(out) < n:
        if f"I{start}" not in taken:
            out.append(f"I{start}")
        start += 1
    return out


def ask(prompt: str) -> str:
    while True:
        a = input(prompt).strip().lower()
        if a in ("y", "j", "n", "q"):
            return "y" if a == "j" else a


def append_fixes(lines: list[str], source: str) -> None:
    text = FIXES.read_text(encoding="utf-8").rstrip("\n")
    stamp = datetime.date.today().isoformat()
    FIXES.write_text(text + "\n#\n# --- from the viewer's edit mode (" + source + ", reviewed " + stamp + ") ---\n"
                     + "\n".join(lines) + "\n", encoding="utf-8")


def append_people(people: dict[str, dict[str, str]]) -> None:
    rows, header, comments = [], ["id"], []
    if NEW_PEOPLE.exists():
        lines = NEW_PEOPLE.read_text(encoding="utf-8").splitlines()
        header = lines[0].split("\t")
        comments = [l for l in lines[1:] if l.startswith("#")]
        rows = [dict(zip(header, l.split("\t"))) for l in lines[1:] if l and not l.startswith("#")]
    for pid, cols in people.items():
        rows.append({"id": pid, **cols})
        header += [c for c in cols if c not in header]
    out = ["\t".join(header), *comments] + ["\t".join(r.get(c, "") for c in header) for r in rows]
    NEW_PEOPLE.write_text("\n".join(out) + "\n", encoding="utf-8")


def review(path: Path, current: dict[str, dict[str, str]]) -> bool:
    changes = read_changes(path)
    new_ids = sorted({c["id"] for c in changes if c["action"] == "new"}, key=lambda x: int(x[3:]) if x[3:].isdigit() else 0)
    real = dict(zip(new_ids, next_ids(len(new_ids))))
    swap = lambda v: re.sub(r"NEW\d+", lambda m: real.get(m[0], m[0]), v)
    name = lambda pid: " ".join(x for x in (current.get(pid, {}).get("GIVN", ""), current.get(pid, {}).get("SURN", "")) if x) or pid
    print(f"\n=== {path.name}: {len(changes)} changes ===")
    fixes, people = [], {}
    # new people first, one question per person
    for nid in new_ids:
        cols = {c["column"]: swap(c["corrected"]) for c in changes if c["action"] == "new" and c["id"] == nid}
        print(f"\nNEW person {real[nid]}:")
        for k, v in cols.items():
            print(f"    {k:14} {v}")
        a = ask("  accept this person? [y/n/q] ")
        if a == "q":
            return False
        if a == "y":
            people[real[nid]] = cols
    for c in changes:
        if c["action"] != "set":
            continue
        pid, col, new = c["id"], c["column"], swap(c["corrected"])
        if pid in real:
            pid = real[pid]
        if re.fullmatch(r"NEW\d+", c["id"]) and real.get(c["id"]) not in people:
            continue                                    # belongs to a rejected new person
        old = current.get(pid, {}).get(col, "")
        show = lambda v: v.replace("\\n", " / ").replace("\r", " / ") or "(empty)"   # multi-line notes on one line
        print(f"\n{pid} {name(pid)} – {col}\n    now: {show(old)}\n    new: {show(new)}")
        a = ask("  accept? [y/n/q] ")
        if a == "q":
            return False
        if a == "y":
            fixes.append(f"{pid}\t{col}\t*\t{new}")
    for c in changes:
        if c["action"] != "delete":
            continue
        pid, row = c["id"], current.get(c["id"], {})
        if not row:
            print(f"\nDELETE {pid}: not in the data any more - skipped.")
            continue
        facts = ", ".join(f"{k} {row[k]}" for k in ("BIRT.DATE", "BIRT.PLAC", "DEAT.DATE", "DEAT.PLAC") if row.get(k))
        links = sorted({row[k].strip("@") for k in ("FATH.#REFN", "MOTH.#REFN", "FAM.HUSB.1", "FAM.WIFE.1",
                        "FAM.HUSB.2", "FAM.WIFE.2", "FAM.HUSB.3", "FAM.WIFE.3") if row.get(k)} - {pid})
        print(f"\nDELETE {pid} {name(pid)}" + (f" ({facts})" if facts else "")
              + (f"\n    linked to: {', '.join(links)}" if links else "\n    no links"))
        a = ask("  delete this person? [y/n/q] ")
        if a == "q":
            return False
        if a == "y":
            fixes.append(f"{pid}\t#DELETE\t*\t")
    saved = []
    for c in changes:
        if c["action"] != "photo":
            continue
        pid = real.get(c["id"], c["id"])
        size = len(c["corrected"]) * 3 // 4 // 1000
        print(f"\nPHOTO for {pid} {name(pid)} – date: {c['column'] or '(none)'} – {size} kB (from {c['original'] or 'upload'})")
        a = ask("  accept? [y/n/q] ")
        if a == "q":
            return False
        if a == "y":
            saved.append(save_photo(pid, c["column"], c["corrected"]))
            print(f"    saved as {saved[-1].relative_to(ROOT)}")
    if fixes:
        append_fixes(fixes, path.name)
    if people:
        append_people(people)
    print(f"\n{len(fixes)} changes, {len(people)} new people and {len(saved)} photos accepted from {path.name}.")
    (INBOX / "done").mkdir(exist_ok=True)
    shutil.move(str(path), INBOX / "done" / path.name)
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="only list waiting change files")
    args = ap.parse_args()
    INBOX.mkdir(parents=True, exist_ok=True)
    files = sorted(INBOX.glob("*.tsv"))
    if not files:
        print(f"No change files in {INBOX}.")
        return
    if args.list:
        for f in files:
            print(f"{f.name}: {len(read_changes(f))} changes")
        return
    current = current_values()
    for f in files:
        if not review(f, current):
            print("Stopped - the remaining changes stay in the inbox.")
            return
    print("\nDone. Check with: python src/build_web.py   then publish as usual.")


if __name__ == "__main__":
    main()
