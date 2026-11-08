"""Generate the DEMO family: an entirely made-up family to show the viewer without real data.

Writes into sample/ (all fictional, safe to publish):
    sample_family.csv     Ahnenblatt-style export (UTF-8, tab separated)
    manual_fixes.tsv      a few owner decisions (nicknames, titles) like in the real workflow
    place_countries.tsv   place -> ISO country code
    img/                  drawn portraits (PNG) named <ID>_<year>.png, captions as .txt
    docs/                 drawn "documents" (PNG) and small PDFs, named <ID>_<Title>.<ext>

Run:   python sample/make_sample.py        (then: python src/build_web.py --sample)
No real person, place of residence or photo is used; names, dates and pictures are invented.
"""
from __future__ import annotations

import csv
import math
import random
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLUMNS = [
    "#REFN", "NAME", "FATH.NAME", "FATH.#REFN", "MOTH.NAME", "MOTH.#REFN", "_UID", "SEX", "GIVN", "SURN",
    "BIRT.DATE", "DEAT.DATE", "BIRT.PLAC", "DEAT.PLAC", "NOTE", "OCCU", "NAME._RUFNAME", "RELI",
    *[c for n in (1, 2, 3) for c in (f"MARR.SPOU.NAME.{n}", f"MARR.SPOU.#REFN.{n}", f"FAM.WIFE.{n}", f"FAM.MARR.{n}",
                                     f"FAM.HUSB.{n}", f"FAM.CHIL.{n}", f"MARR.DATE.{n}", f"MARR.PLAC.{n}",
                                     f"FAM._STAT.{n}", f"FAM._MARR.{n}")],
]

# id, sex, given, surname, birth, birth place, death, death place, occupation, religion, note, father, mother
P = [
    ("I1", "M", "Adam", "Wurzel", "im Jahr 1792", "Bernkastel", "14.02.1858", "Bernkastel", "Winzer", "kath.", "Der Stammvater - irgendwer musste ja anfangen.", "", ""),
    ("I2", "F", "Eva", "Ast", "03.03.1795", "Traben", "1861", "Bernkastel", "", "kath.", "", "", ""),
    ("I3", "M", "Vinzenz", "Wurzel", "11.08.1817", "Bernkastel", "02.12.1879", "Bernkastel", "Küfer", "kath.", "Übernahm den Weinberg am Doctorberg.", "I1", "I2"),
    ("I4", "F", "Mini", "Wurzel", "1819", "Bernkastel", "1820", "Bernkastel", "", "kath.", "", "I1", "I2"),
    ("I5", "M", "Fernando", "Wurzel", "1822?", "Bernkastel", "1890", "Milwaukee", "Brauer", "kath.", "Wanderte 1849 über Bremen nach Amerika aus.", "I1", "I2"),
    ("I6", "F", "Rosa", "Rinde", "1824", "Zell", "1847", "Bernkastel", "", "kath.", "Starb kurz nach der Geburt ihres Sohnes Erbert.", "", ""),
    ("I7", "F", "Stefanie", "Mutter", "17.04.1828", "Traben", "1902", "Bernkastel", "", "kath.", "Stef. Mutter - und tatsächlich die Stiefmutter von Erbert.", "", ""),
    ("I8", "M", "Erbert", "Wurzel", "02.01.1846", "Bernkastel", "1911", "Trier", "Weinhändler", "kath.", "Der Erbe des Weinbergs.", "I3", "I6"),
    ("I9", "F", "Tilly", "Wurzel", "1850", "Bernkastel", "1931", "Koblenz", "", "kath.", "", "I3", "I7"),
    ("I10", "M", "Ottokar", "Wurzel", "1853", "Bernkastel", "1920", "Bernkastel", "Winzer", "kath.", "", "I3", "I7"),
    ("I11", "F", "Hanni", "Wurzel", "12.06.1856", "Bernkastel", "1938", "Köln", "Näherin", "kath.", "Zwillingsschwester von Nanni.", "I3", "I7"),
    ("I12", "F", "Nanni", "Wurzel", "12.06.1856", "Bernkastel", "1859", "Bernkastel", "", "kath.", "", "I3", "I7"),
    ("I13", "F", "Molly", "Malone", "1830", "Cork", "1899", "Milwaukee", "Fischhändlerin", "kath.", "", "", ""),
    ("I14", "M", "Henry", "Root", "09.09.1855", "Milwaukee", "1931", "Chicago", "Ingenieur", "kath.", "Die Familie übersetzte ihren Namen in Amerika: aus Wurzel wurde Root.", "I5", "I13"),
    ("I15", "F", "Sophie", "Feuillage", "21.03.1850", "Metz", "1925", "Trier", "", "kath.", "", "", ""),
    ("I16", "M", "Ludwig", "Wurzel", "05.05.1873", "Trier", "1949", "Trier", "Lehrer", "kath.", "", "I8", "I15"),
    ("I17", "F", "Lotte", "Wurzel", "1876", "Trier", "1960", "Trier", "", "kath.", "", "I8", "I15"),
    ("I18", "F", "Christine", "Knospe", "1856", "Zell", "1930", "Bernkastel", "", "kath.", "", "", ""),
    ("I19", "M", "Wilhelm", "Wurzel", "1880", "Bernkastel", "1950", "Bernkastel", "Schmied", "kath.", "", "I10", "I18"),
    ("I20", "F", "Bella", "Fiore", "30.10.1878", "Triest", "1961", "Trier", "", "kath.", "", "", ""),
    ("I21", "M", "Frieder", "Wurzel", "14.07.1902", "Trier", "1980", "Köln", "Zahnarzt", "kath.", "Seine Patienten nannten ihn nur „Doktor Wurzelbehandlung“.", "I16", "I20"),
    ("I22", "F", "Pola", "Wurzel", "1905", "Trier", "1999", "Hamburg", "Fotografin", "kath.", "Fotografierte die halbe Familie - daher die vielen Bilder.", "I16", "I20"),
    ("I23", "M", "Paul", "Wurzel", "1908", "Trier", "1944", "", "Buchhalter", "kath.", "Gefallen im Zweiten Weltkrieg.", "I16", "I20"),
    ("I24", "F", "Berta", "Blatt", "1884", "Wittlich", "1966", "Bernkastel", "", "kath.", "", "", ""),
    ("I25", "F", "Hedwig", "Wurzel", "1909", "Bernkastel", "2001", "Koblenz", "", "kath.", "", "I19", "I24"),
    ("I26", "F", "Sissi", "Schmarrn", "1908", "Wien", "1994", "Köln", "", "ev.", "", "", ""),
    ("I27", "M", "Klaus", "Wurzel", "22.02.1933", "Köln", "2015", "Köln", "Ingenieur", "kath.", "", "I21", "I26"),
    ("I28", "F", "Ursula", "Wurzel", "1936", "Köln", "", "", "Übersetzerin", "kath.", "", "I21", "I26"),
    ("I29", "M", "Otto", "Linde", "1900", "Hamburg", "1975", "Hamburg", "Kaufmann", "ev.", "", "", ""),
    ("I30", "M", "Heinz", "Linde", "1930", "Hamburg", "2008", "Hamburg", "Kapitän", "ev.", "", "I29", "I22"),
    ("I31", "M", "Ernst", "Pfeffer", "1905", "Koblenz", "1970", "Koblenz", "Lebkuchenbäcker", "kath.", "", "", ""),
    ("I32", "F", "Renate", "Exner", "1937", "Bonn", "", "", "Lehrerin", "ev.", "geschieden", "", ""),
    ("I33", "M", "Thomas", "Wurzel", "1960", "Köln", "", "", "Informatiker", "", "Hat als Einziger in der Familie Root-Rechte.", "I27", "I32"),
    ("I34", "F", "Sabine", "Wurzel", "1963", "Köln", "", "", "Ärztin", "", "", "I27", "I32"),
    ("I35", "F", "Monika", "Wildwuchs", "1945", "Düsseldorf", "", "", "Architektin", "", "", "", ""),
    ("I36", "M", "Jan", "Wurzel", "1978", "Köln", "", "", "Musiker", "", "", "I27", "I35"),
    ("I37", "M", "Michel", "Croissant", "1934", "Lyon", "2010", "Lyon", "Koch", "kath.", "", "", ""),
    ("I38", "F", "Claire", "Croissant", "1962", "Lyon", "", "", "", "", "", "I37", "I28"),
    ("I39", "F", "Julia", "Schwieger", "1964", "München", "", "", "", "", "", "", ""),
    ("I40", "F", "Lena", "Wurzel", "1990", "München", "", "", "Biologin", "", "", "I33", "I39"),
    ("I41", "M", "Max", "Wurzel", "1993", "München", "", "", "", "", "", "I33", "I39"),
    ("I42", "M", "Kemal", "Ağaç", "1962", "Izmir", "", "", "Ingenieur", "", "Ağaç heißt auf Türkisch „Baum“.", "", ""),
    ("I43", "M", "Deniz", "Ağaç", "1995", "Köln", "", "", "", "", "", "I42", "I34"),
    ("I44", "F", "Mia", "Sprössling", "2018", "Berlin", "", "", "", "", "Die Jüngste im ganzen Baum.", "I45", "I40"),
    ("I45", "M", "Lukas", "Sprössling", "1989", "Berlin", "", "", "", "", "", "", ""),
]
# husband, wife, date, place, status (NOT MARRIED for a couple that never married)
COUPLES = [
    ("I1", "I2", "12.05.1816", "Bernkastel", ""), ("I3", "I6", "1845", "Bernkastel", ""),
    ("I3", "I7", "03.02.1849", "Bernkastel", ""), ("I5", "I13", "1852", "Milwaukee", ""),
    ("I8", "I15", "18.09.1872", "Trier", ""), ("I10", "I18", "1878", "Bernkastel", ""),
    ("I16", "I20", "1900", "Trier", ""), ("I19", "I24", "1907", "Bernkastel", ""),
    ("I21", "I26", "1931", "Köln", ""), ("I29", "I22", "1928", "Hamburg", ""), ("I31", "I25", "1934", "Koblenz", ""),
    ("I27", "I32", "1958", "Köln", ""), ("I27", "I35", "", "", "NOT MARRIED"), ("I37", "I28", "1960", "Lyon", ""),
    ("I33", "I39", "1988", "München", ""), ("I42", "I34", "1993", "Köln", ""), ("I45", "I40", "", "", "NOT MARRIED"),
]
COUNTRIES = {"Bernkastel": "DE", "Traben": "DE", "Zell": "DE", "Trier": "DE", "Koblenz": "DE", "Köln": "DE",
             "Wittlich": "DE", "Hamburg": "DE", "Bonn": "DE", "Düsseldorf": "DE", "München": "DE", "Berlin": "DE",
             "Milwaukee": "US", "Chicago": "US", "Cork": "IE", "Metz": "FR", "Lyon": "FR", "Triest": "IT",
             "Wien": "AT", "Izmir": "TR"}
FIXES = [("I1", "NICK", "*", "der Urahn"), ("I5", "NICK", "*", "Fernweh"), ("I16", "NICK", "*", "Lehrer Lämpel"),
         ("I21", "TITL", "*", "Dr. med. dent."), ("I21", "NICK", "*", "Doktor Wurzelbehandlung"),
         ("I22", "NICK", "*", "Polaroid-Pola"), ("I27", "NICK", "*", "Tüftel-Klaus"), ("I30", "NICK", "*", "Käpt'n Linde"),
         ("I33", "NICK", "*", "root"), ("I34", "TITL", "*", "Dr."), ("I41", "NICK", "*", "Max Mustermann")]

# photos: file stem, sex, birth year of the person (for the age look), photo year, caption
PHOTOS = [
    ("I3_1870", "M", 1817, 1870, "Vinzenz Wurzel vor dem Weinkeller, um 1870."),
    ("I8_1872", "M", 1846, 1872, "Hochzeitsbild Erbert und Sophie, Trier 1872."),
    ("I15_1872", "F", 1850, 1872, "Hochzeitsbild Erbert und Sophie, Trier 1872."),
    ("I16_1900", "M", 1873, 1900, "Ludwig Wurzel als junger Lehrer („Lehrer Lämpel“)."),
    ("I20_1900", "F", 1878, 1900, "Bella Fiore kurz nach der Ankunft in Trier."),
    ("I21_1935", "M", 1902, 1935, "Dr. Frieder Wurzel in seiner Zahnarztpraxis."),
    ("I22_1928", "F", 1905, 1928, "Pola am Tag ihrer Hochzeit in Hamburg – das einzige Foto, das sie nicht selbst gemacht hat."),
    ("I26_1950", "F", 1908, 1950, ""),
    ("I27_1960", "M", 1933, 1960, "Tüftel-Klaus nach dem Ingenieurexamen."),
    ("I32_1960", "F", 1937, 1960, ""),
    ("I33_1990", "M", 1960, 1990, "Thomas („root“), Sommer 1990."),
    ("I40_2015", "F", 1990, 2015, "Lena bei der Feldforschung."),
    ("I44_2021", "F", 2018, 2021, "Mia mit drei Jahren."),
]
# documents: file name, kind, caption
DOCS = [
    ("I5_Passagierliste_Bremen_1849.png", "list", "Auszug aus der (erfundenen) Passagierliste des Schiffs „Hoffnung“, Bremen – New York, 1849."),
    ("I14_Geburtsurkunde_1855.png", "certificate", "Birth certificate of Henry Root, City of Milwaukee, 1855 (Beispiel)."),
    ("I21_Approbationsurkunde_1928.pdf", "pdf", ""),
    ("I23_Feldpostbrief_1943.pdf", "pdf", ""),
]


# ---------------------------------------------------------------- data files
def write_csv() -> None:
    rows = {}
    names = {p[0]: f"{p[2]} {p[3]}" for p in P}
    for pid, sex, giv, sur, bd, bp, dd, dp, occ, rel, note, fa, mo in P:
        r = dict.fromkeys(COLUMNS, "")
        r.update({"#REFN": f"@{pid}@", "NAME": names[pid], "SEX": sex, "GIVN": giv, "SURN": sur, "BIRT.DATE": bd,
                  "BIRT.PLAC": bp, "DEAT.DATE": dd, "DEAT.PLAC": dp, "OCCU": occ, "RELI": rel, "NOTE": note,
                  "_UID": f"DEMO{int(pid[1:]):032d}"})
        for col, ref in (("FATH", fa), ("MOTH", mo)):
            if ref:
                r[f"{col}.#REFN"], r[f"{col}.NAME"] = f"@{ref}@", names[ref]
        rows[pid] = r
    for h, w, date, place, status in COUPLES:
        for me, other in ((h, w), (w, h)):
            r = rows[me]
            n = next(k for k in (1, 2, 3) if not r[f"FAM.HUSB.{k}"])
            r.update({f"FAM.HUSB.{n}": f"@{h}@", f"FAM.WIFE.{n}": f"@{w}@", f"MARR.SPOU.#REFN.{n}": f"@{other}@",
                      f"MARR.SPOU.NAME.{n}": names[other], f"MARR.DATE.{n}": date, f"MARR.PLAC.{n}": place,
                      f"FAM._STAT.{n}": status, f"FAM.MARR.{n}": "" if status else "Y"})
    with (HERE / "sample_family.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter="\t")
        w.writeheader()
        w.writerows(rows.values())
    lines = ["id\tcolumn\toriginal\tcorrected", "# DEMO: invented family - owner decisions as in the real workflow"]
    (HERE / "manual_fixes.tsv").write_text("\n".join(lines + ["\t".join(f) for f in FIXES]) + "\n", encoding="utf-8")
    (HERE / "place_countries.tsv").write_text(
        "place\tcountry\n" + "".join(f"{p}\t{c}\n" for p, c in COUNTRIES.items()), encoding="utf-8")


# ---------------------------------------------------------------- tiny PNG / PDF writers (no libraries)
def write_png(path: Path, w: int, h: int, px: bytearray) -> None:
    raw = b"".join(b"\x00" + bytes(px[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def write_pdf(path: Path, title: str, lines: list[str]) -> None:
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    text = "BT /F1 20 Tf 60 760 Td (" + esc(title) + ") Tj /F1 12 Tf " + \
           "".join(f"0 -28 Td ({esc(l)}) Tj " for l in lines) + "ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("cp1252")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


# ---------------------------------------------------------------- drawn pictures
def tone(r: float, g: float, b: float, year: int) -> tuple[int, int, int]:
    """Old photos sepia, 1950-1985 faded colour, later full colour."""
    if year < 1950:
        lum = 0.3 * r + 0.59 * g + 0.11 * b
        r, g, b = lum * 1.07 + 18, lum * 0.92 + 8, lum * 0.72
    elif year < 1986:
        r, g, b = r * 0.85 + 30, g * 0.85 + 26, b * 0.8 + 20
    return tuple(max(0, min(255, int(v))) for v in (r, g, b))


def portrait(path: Path, sex: str, age: int, year: int, seed: int) -> None:
    rnd, w, h = random.Random(seed), 300, 360
    bg = [rnd.randint(90, 160) for _ in range(3)]
    coat = [rnd.randint(30, 110) for _ in range(3)]
    skin = (224, 186, 160) if rnd.random() < 0.7 else (196, 150, 118)
    grey = max(0.0, min(1.0, (age - 45) / 30))
    hair = [int(c + (190 - c) * grey) for c in rnd.choice([(60, 40, 25), (110, 80, 45), (30, 25, 20), (150, 110, 60)])]
    long_hair = sex == "F" and age > 4
    px = bytearray(w * h * 3)
    for y in range(h):
        for x in range(w):
            g = 1 - y / h * 0.35
            col = [c * g for c in bg]
            dx, dy = (x - 150) / 105, (y - 400) / 130            # shoulders
            if dx * dx + dy * dy < 1:
                col = list(coat)
                if abs(x - 150) < 16 and 285 < y < 330 and sex == "M" and age > 15:
                    col = [200, 200, 205]                          # shirt collar
            if long_hair and ((x - 150) / 70) ** 2 + ((y - 190) / 105) ** 2 < 1:
                col = list(hair)
            if abs(x - 150) < 22 and 220 < y < 290:                # neck
                col = [c * 0.92 for c in skin]
            hx, hy = (x - 150) / 52, (y - 175) / 66                # head
            if hx * hx + hy * hy < 1:
                col = list(skin)
                if hy < -0.35 + (0.25 if not long_hair else 0.05) * math.cos(hx * 3):
                    col = list(hair)                               # hair line
                for ex in (-0.38, 0.38):                           # eyes
                    if (hx - ex) ** 2 / 0.012 + (hy + 0.05) ** 2 / 0.006 < 1:
                        col = [45, 35, 30]
                if abs(hx) < 0.28 and abs(hy - 0.48) < 0.03:       # mouth
                    col = [150, 80, 75]
                if sex == "M" and age > 25 and seed % 3 == 0 and 0.3 < hy < 0.42 and abs(hx) < 0.35:
                    col = list(hair)                               # moustache
            v = 1 - 0.55 * (((x - 150) / 190) ** 2 + ((y - 170) / 230) ** 2)   # vignette
            n = rnd.uniform(-6, 6) if year < 1950 else 0
            i = (y * w + x) * 3
            px[i:i + 3] = bytes(tone(*[c * v + n for c in col], year))
    write_png(path, w, h, px)


def document_image(path: Path, kind: str, seed: int) -> None:
    rnd, w, h = random.Random(seed), 520, 700
    px = bytearray(w * h * 3)
    lines = []
    y = 120
    while y < 600:
        x0 = rnd.randint(60, 90) if kind == "list" else 70
        lines.append((y, x0, min(rnd.randint(250, 450), w - 60 - x0)))
        y += 26 if kind == "list" else 34
    for yy in range(h):
        for x in range(w):
            p = 236 - 10 * ((x / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) + rnd.uniform(-4, 4)
            col = [p, p * 0.96, p * 0.85]
            if 18 < x < w - 18 and 18 < yy < h - 18 and (x < 24 or x > w - 24 or yy < 24 or yy > h - 24):
                col = [120, 90, 60]                                    # border
            if 60 < yy < 84 and 110 < x < w - 110:
                col = [70, 55, 45]                                     # heading
            for ly, x0, length in lines:
                if ly < yy < ly + 7 and x0 < x < x0 + length and (x // 9) % 7:
                    col = [95, 85, 80]                                 # "handwriting" / text
                if kind == "list" and ly - 2 < yy < ly - 1:
                    col = [190, 170, 150]                              # table rules
            cx, cy = x - 400, yy - 625                                  # stamp
            d = math.hypot(cx, cy)
            if 40 < d < 46 or (d < 30 and (x + yy) % 5 == 0):
                col = [150, 60, 60]
            sx = 130 + 140 * (x - 90) / 140
            if 90 < x < 230 and abs(yy - (630 + 12 * math.sin(sx / 14))) < 1.5:
                col = [40, 40, 90]                                     # signature
            i = (yy * w + x) * 3
            px[i:i + 3] = bytes(max(0, min(255, int(c))) for c in col)
    write_png(path, w, h, px)


def main() -> None:
    write_csv()
    img, docs = HERE / "img", HERE / "docs"
    for d in (img, docs):
        d.mkdir(exist_ok=True)
        for old in d.iterdir():
            old.unlink()
    for i, (stem, sex, born, year, caption) in enumerate(PHOTOS):
        portrait(img / f"{stem}.png", sex, year - born, year, seed=i * 7 + 3)
        if caption:
            (img / f"{stem}.txt").write_text(caption, encoding="utf-8")
    for i, (name, kind, caption) in enumerate(DOCS):
        if kind == "pdf":
            title = name.split("_", 1)[1].rsplit(".", 1)[0].replace("_", " ")
            write_pdf(docs / name, title + " (Beispiel)",
                      ["Dieses Dokument gehoert zur erfundenen Demo-Familie Wurzel.",
                       "Es zeigt, wie der Stammbaum Dokumente auflistet, die er nicht anzeigt."])
        else:
            document_image(docs / name, kind, seed=100 + i)
        if caption:
            (docs / name).with_suffix(".txt").write_text(caption, encoding="utf-8")
    print(f"demo family: {len(P)} people, {len(COUPLES)} couples, {len(PHOTOS)} photos, {len(DOCS)} documents")


if __name__ == "__main__":
    main()
