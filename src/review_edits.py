"""Review change files from the viewer's edit mode before anything is published.

Usage:
    python src/review_edits.py            review every file in data/cleaned/inbox/
    python src/review_edits.py --list     only show what is waiting, change nothing

Workflow:
    1. In the viewer switch on ✏️, edit, then download the change file.
    2. Put the downloaded <date>_<time>_edits.tsv - or, with new photos, <date>_<time>_edits.zip
       (the .tsv plus the photos) - into data/cleaned/inbox/. Unpacked files work too: the .tsv
       with its photos next to it.
    3. Run this script: every change is shown (current value -> new value); answer
       y = accept, n = reject, q = stop (the rest stays in the inbox for later).
    4. Accepted changes are appended to data/cleaned/manual_fixes.tsv (field changes) and
       data/cleaned/new_people.tsv (new people, with real I-numbers). The file moves to inbox/done/.
    5. Check the result with `python src/build_web.py`, then publish as usual.

Change file columns: action (set | new | photo | delete), id, column, original, corrected.
Delete rows: original = the person's name; an accepted one becomes `<id>  #DELETE` in manual_fixes.tsv,
which makes clean_csv.py drop the person and every link to them.
Photo rows: column = year (may be empty), original = the photo's file name in the zip
(<ID>[_<year>][_n].jpg), corrected = description (shown under the photo). Older change files carry
the photo itself instead: original = uploaded file name, corrected = data: URL (JPEG).
Doc rows: original = the file name in the zip (<ID>_<Title>.<ext>, any type), corrected = title;
accepted documents go to data/docs/ under that name.
Accepted photos are saved as data/img/<ID>_<year>.jpg (or <ID>.jpg; a _2, _3 … suffix avoids
overwriting), the description as <same name>.txt next to it.
New people use temporary ids NEW1, NEW2 … which get the next free I-numbers here.
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime
import re
import shutil
import zipfile
from pathlib import Path

from build_web import DEFAULT_CSV, read_rows

ROOT = Path(__file__).resolve().parent.parent
CLEANED = ROOT / "data" / "cleaned"
INBOX = CLEANED / "inbox"
FIXES = CLEANED / "manual_fixes.tsv"
NEW_PEOPLE = CLEANED / "new_people.tsv"
CLEAN_COPY = CLEANED / "family_tree_cleaned.csv"
IMG = ROOT / "data" / "img"
DOCS = ROOT / "data" / "docs"


def save_photo(pid: str, date: str, raw: bytes, note: str = "") -> Path:
    """Save the photo to the data/img directory, with its description as caption file.

    Args:
        pid (str): The ID of the person.
        date (str): The year (or date) of the photo, may be empty.
        raw (bytes): The JPEG data.
        note (str): The description; written to <photo name>.txt when not empty.

    Returns:
        Path: The path to the saved photo.
    """
    IMG.mkdir(parents=True, exist_ok=True)
    stem = f"{pid}_{date}" if date else pid
    target, n = IMG / f"{stem}.jpg", 2
    while target.exists():
        target, n = IMG / f"{stem}_{n}.jpg", n + 1
    target.write_bytes(raw)
    if note:
        target.with_suffix(".txt").write_text(note, encoding="utf-8")
    return target


def save_doc(name: str, raw: bytes) -> Path:
    """Save a document as data/docs/<ID>_<Title>.<ext> (a _2, _3 … suffix avoids overwriting)."""
    DOCS.mkdir(parents=True, exist_ok=True)
    stem, ext = Path(name).stem, Path(name).suffix
    target, n = DOCS / name, 2
    while target.exists():
        target, n = DOCS / f"{stem}_{n}{ext}", n + 1
    target.write_bytes(raw)
    return target


def unpack(archive: Path) -> Path:
    """Unpack a downloaded <stamp>_edits.zip into inbox/<stamp>_edits/ (flat, file names only).

    Args:
        archive (Path): The zip file in the inbox.

    Returns:
        Path: The folder with the change file and the photos.
    """
    folder = archive.with_suffix("")
    folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name = Path(info.filename).name  # never follow paths inside the archive
            if info.is_dir() or not re.fullmatch(r"[\w.\- ]+\.\w{1,8}", name):  # photos, documents of any type
                continue
            (folder / name).write_bytes(z.read(info))
    return folder


def find_photo(name: str, folders: list[Path]) -> Path | None:
    """Find a photo named in a change file next to it (or in the other given folders)."""
    for folder in folders:
        if (folder / name).is_file():
            return folder / name
    return None


def read_changes(path: Path) -> list[dict[str, str]]:
    """Read the change file and return a list of dictionaries, one for each row.

    Args:
        path (Path): The path to the change file.

    Returns:
        list[dict[str, str]]: A list of dictionaries, one for each row.
    """
    # Photo rows store a data: URL; a JPEG easily exceeds the 128 KB csv default.
    csv.field_size_limit(16 * 1024 * 1024)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        lines = [line for line in fh if line.strip() and not line.startswith("#")]
    return [
        {k: (v or "") for k, v in r.items()}
        for r in csv.DictReader(lines, delimiter="\t", quoting=csv.QUOTE_NONE)
    ]


def current_values() -> dict[str, dict[str, str]]:
    """id -> cleaned row (what the viewer shows today)."""
    if not CLEAN_COPY.exists():
        return {}
    with CLEAN_COPY.open(encoding="utf-8-sig", newline="") as fh:
        return {r["#REFN"].strip("@"): r for r in csv.DictReader(fh, delimiter="\t")}


def used_ids() -> set[str]:
    """Get the IDs of the people used in the default CSV file and the new people file.

    Returns:
        set[str]: A set of IDs.
    """
    ids = {r["#REFN"].strip("@") for r in read_rows(DEFAULT_CSV)}
    if NEW_PEOPLE.exists():
        for line in NEW_PEOPLE.read_text(encoding="utf-8").splitlines()[1:]:
            if line and not line.startswith("#"):
                ids.add(line.split("\t", 1)[0])
    return ids


def next_ids(n: int) -> list[str]:
    """Get the next n IDs.

    Args:
        n (int): The number of IDs to get.

    Returns:
        list[str]: A list of IDs.
    """
    taken = used_ids()
    nums = sorted(int(i[1:]) for i in taken if re.fullmatch(r"I\d+", i))
    start, out = (nums[-1] if nums else 0) + 1, []
    while len(out) < n:
        if f"I{start}" not in taken:
            out.append(f"I{start}")
        start += 1
    return out


def ask(prompt: str) -> str:
    """Ask the user a question and return the answer.

    Args:
        prompt (str): The question to ask.

    Returns:
        str: The answer.
    """
    while True:
        a = input(prompt).strip().lower()
        if a in ("y", "j", "n", "q"):
            return "y" if a == "j" else a


def append_fixes(lines: list[str], source: str) -> None:
    """Append the fixes to the manual fixes file.

    Args:
        lines (list[str]): The lines to append.
        source (str): The source of the fixes.
    """
    text = FIXES.read_text(encoding="utf-8").rstrip("\n")
    stamp = datetime.date.today().isoformat()
    FIXES.write_text(
        text
        + "\n#\n# --- from the viewer's edit mode ("
        + source
        + ", reviewed "
        + stamp
        + ") ---\n"
        + "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )


def append_people(people: dict[str, dict[str, str]]) -> None:
    """Append the people to the new people file.

    Args:
        people (dict[str, dict[str, str]]): The people to append.
    """
    rows, header, comments = [], ["id"], []
    if NEW_PEOPLE.exists():
        lines = NEW_PEOPLE.read_text(encoding="utf-8").splitlines()
        header = lines[0].split("\t")
        comments = [l for l in lines[1:] if l.startswith("#")]
        rows = [
            dict(zip(header, l.split("\t")))
            for l in lines[1:]
            if l and not l.startswith("#")
        ]
    for pid, cols in people.items():
        rows.append({"id": pid, **cols})
        header += [c for c in cols if c not in header]
    out = ["\t".join(header), *comments] + [
        "\t".join(r.get(c, "") for c in header) for r in rows
    ]
    NEW_PEOPLE.write_text("\n".join(out) + "\n", encoding="utf-8")


def review(path: Path, current: dict[str, dict[str, str]]) -> bool:
    """Review the changes in the change file.

    Args:
        path (Path): The path to the change file.
        current (dict[str, dict[str, str]]): The current values of the people.

    Returns:
        bool: True if the changes were reviewed, False otherwise.
    """
    changes = read_changes(path)
    new_ids = sorted(
        {c["id"] for c in changes if c["action"] == "new"},
        key=lambda x: int(x[3:]) if x[3:].isdigit() else 0,
    )
    real = dict(zip(new_ids, next_ids(len(new_ids))))
    swap = lambda v: re.sub(r"NEW\d+", lambda m: real.get(m[0], m[0]), v)
    name = lambda pid: (
        " ".join(
            x
            for x in (
                current.get(pid, {}).get("GIVN", ""),
                current.get(pid, {}).get("SURN", ""),
            )
            if x
        )
        or pid
    )
    print(f"\n=== {path.name}: {len(changes)} changes ===")
    fixes, people = [], {}
    # new people first, one question per person
    for nid in new_ids:
        cols = {
            c["column"]: swap(c["corrected"])
            for c in changes
            if c["action"] == "new" and c["id"] == nid
        }
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
            continue  # belongs to a rejected new person
        old = current.get(pid, {}).get(col, "")
        show = lambda v: (
            v.replace("\\n", " / ").replace("\r", " / ") or "(empty)"
        )  # multi-line notes on one line
        print(
            f"\n{pid} {name(pid)} – {col}\n    now: {show(old)}\n    new: {show(new)}"
        )
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
        facts = ", ".join(
            f"{k} {row[k]}"
            for k in ("BIRT.DATE", "BIRT.PLAC", "DEAT.DATE", "DEAT.PLAC")
            if row.get(k)
        )
        links = sorted(
            {
                row[k].strip("@")
                for k in (
                    "FATH.#REFN",
                    "MOTH.#REFN",
                    "FAM.HUSB.1",
                    "FAM.WIFE.1",
                    "FAM.HUSB.2",
                    "FAM.WIFE.2",
                    "FAM.HUSB.3",
                    "FAM.WIFE.3",
                )
                if row.get(k)
            }
            - {pid}
        )
        print(
            f"\nDELETE {pid} {name(pid)}"
            + (f" ({facts})" if facts else "")
            + (f"\n    linked to: {', '.join(links)}" if links else "\n    no links")
        )
        a = ask("  delete this person? [y/n/q] ")
        if a == "q":
            return False
        if a == "y":
            fixes.append(f"{pid}\t#DELETE\t*\t")
    saved, used = [], []
    for c in changes:
        if c["action"] != "photo":
            continue
        pid = real.get(c["id"], c["id"])
        if re.fullmatch(r"NEW\d+", c["id"]) and pid not in people:
            continue  # photo of a rejected new person
        if c["corrected"].startswith("data:"):  # older change file: the photo is inside the row
            raw, note, source = base64.b64decode(c["corrected"].split(",", 1)[1]), "", c["original"] or "upload"
        else:
            found = find_photo(c["original"], [path.parent, INBOX])
            if not found:
                print(f"\nPHOTO {c['original']} for {pid} {name(pid)}: file not found next to {path.name} - skipped.")
                continue
            raw, note, source = found.read_bytes(), c["corrected"].replace("\\n", "\n").strip(), found.name
            used.append(found)
        print(
            f"\nPHOTO for {pid} {name(pid)} – year: {c['column'] or '(none)'} – {len(raw) // 1000} kB ({source})"
            + (f"\n    description: {note}" if note else "")
        )
        a = ask("  accept? [y/n/q] ")
        if a == "q":
            return False
        if a == "y":
            saved.append(save_photo(pid, c["column"], raw, note))
            print(f"    saved as {saved[-1].relative_to(ROOT)}")
    docs = []
    for c in changes:
        if c["action"] != "doc":
            continue
        pid = real.get(c["id"], c["id"])
        if re.fullmatch(r"NEW\d+", c["id"]) and pid not in people:
            continue  # document of a rejected new person
        found = find_photo(c["original"], [path.parent, INBOX])
        if not found:
            print(f"\nDOCUMENT {c['original']} for {pid} {name(pid)}: file not found next to {path.name} - skipped.")
            continue
        used.append(found)
        target = c["original"] if c["id"] == pid else re.sub(r"^NEW\d+", pid, c["original"])
        print(f"\nDOCUMENT for {pid} {name(pid)} – \"{c['corrected']}\" – {found.stat().st_size // 1000} kB ({found.name})")
        a = ask("  accept? [y/n/q] ")
        if a == "q":
            return False
        if a == "y":
            docs.append(save_doc(target, found.read_bytes()))
            print(f"    saved as {docs[-1].relative_to(ROOT)}")
    if fixes:
        append_fixes(fixes, path.name)
    if people:
        append_people(people)
    print(
        f"\n{len(fixes)} changes, {len(people)} new people, {len(saved)} photos and {len(docs)} documents accepted from {path.name}."
    )
    done = INBOX / "done"
    done.mkdir(exist_ok=True)
    shutil.move(str(path), done / path.name)
    for photo in used:  # the photos travel with their change file
        if photo.exists():
            (done / path.stem).mkdir(exist_ok=True)
            shutil.move(str(photo), done / path.stem / photo.name)
    return True


def main() -> None:
    """Main function.

    Args:
        args (argparse.Namespace): The arguments.
    """
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--list", action="store_true", help="only list waiting change files"
    )
    args = ap.parse_args()
    INBOX.mkdir(parents=True, exist_ok=True)
    archives = sorted(INBOX.glob("*.zip"))
    if args.list:
        for a in archives:
            with zipfile.ZipFile(a) as z:
                photos = sum(1 for n in z.namelist() if not n.lower().endswith(".tsv"))
            print(f"{a.name}: change file with {photos} photos (zip)")
        for f in sorted(INBOX.glob("*.tsv")):
            print(f"{f.name}: {len(read_changes(f))} changes")
        if not archives and not any(INBOX.glob("*.tsv")):
            print(f"No change files in {INBOX}.")
        return
    jobs = []  # (change file, zip it came from or None)
    for a in archives:
        jobs += [(f, a) for f in sorted(unpack(a).glob("*.tsv"))]
    jobs += [(f, None) for f in sorted(INBOX.glob("*.tsv"))]
    if not jobs:
        print(f"No change files in {INBOX}.")
        return
    current = current_values()
    for f, archive in jobs:
        if not review(f, current):
            print("Stopped - the remaining changes stay in the inbox.")
            return
        if archive:  # zip done: keep it in done/, drop the unpacked copy
            shutil.move(str(archive), INBOX / "done" / archive.name)
            shutil.rmtree(f.parent, ignore_errors=True)
    print("\nDone. Check with: python src/build_web.py   then publish as usual.")


if __name__ == "__main__":
    main()
