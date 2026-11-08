# Our family tree 🌳

🇩🇪 **[Deutsche Version: LIESMICH.md](LIESMICH.md)**

An interactive map of our family — almost 800 relatives across more than nine generations.
Move around it like a map, zoom in on any branch, and click a person to see who they were.

## 👉 View the family tree

**[Open the family tree](https://fabricebeaumont.github.io/family-tree/?lang=en)**

*Tip: Ctrl+click (Mac: Cmd+click, phone: press and hold) opens it in a new tab.*

1. Click the link above. It works on computers, tablets and phones.
2. You will be asked for a **password**. You get it from Fabrice (the family member who looks after
   the tree) — just ask. The password is never written on this page.
3. Type the password and click **Öffnen** (open). The tree loads after a few seconds.

## How to use it

| To… | Do this |
|---|---|
| Move around | Click and drag (on a phone: swipe) |
| Zoom in or out | Mouse wheel, or pinch with two fingers |
| Find someone | Type a name into the search box at the top left |
| See details about a person | Click their card — a panel shows dates, places, parents, partners, children |
| Jump to a relative | Click their name in that panel |
| Show only a few generations | Type numbers into **↑** (ancestors) and **↓** (descendants) at the top; empty = all |
| Show or hide photos | Click **Fotos** |
| See the whole tree at once | Click the **⤢** button next to the search box |

When you click a person, their direct line (parents, grandparents… and children, grandchildren…)
is highlighted in orange. The person stays selected while you explore; click **⤢** to clear the selection and see the whole tree.

Card colors: **blue** = male, **pink** = female.

## Found a mistake or know more?

Missing someone, a wrong date, or an old photo? Click **✏️** at the top, correct the details or add people
and photos, then click **Changes** → **Download as file** and send the file to Fabrice. Nothing is changed
online – he checks every change before it appears. Or simply tell him. If you want to collect details
about your branch, there is a simple questionnaire to fill in:
[docs/Fragebogen Familienstammbaum.xlsx](docs/Fragebogen%20Familienstammbaum.xlsx).

## Is our data safe?

Yes. The family data on this website is **encrypted**: without the password it is unreadable,
even for someone who downloads the files. Search engines are asked not to list the page.
Please don't post the password publicly — share it only with family, and preferably not in the same
message as the link.

---

## Technical information

Everything below is for whoever maintains the tree.

### How it works

The tree is maintained in [Ahnenblatt](https://www.ahnenblatt.de/). A Python script reads
Ahnenblatt's CSV export and builds a web viewer from it. For the website, the data is encrypted with
a password and published with GitHub Pages.

### Folder layout

| Folder | Committed? | Contents |
|---|---|---|
| `src/` | yes | `build_web.py` (CSV → viewer), `index.html` (viewer template), `clean_csv.py` (CSV → cleaned copy) |
| `public/` | yes (generated) | Password-encrypted viewer, deployed to GitHub Pages |
| `docs/` | yes | Blank questionnaire for collecting data from relatives |
| `data/` | **no** (private) | `ahnenblatt/` (`.ahn` + CSV export), `exports/` (HTML + PDF reports), `img/` (photos), `archive/` |
| `web/` | **no** (generated) | Viewer with unencrypted data, for private sharing as a zip |

`data/` and `web/` contain personal data of living people and are never committed.

**Cleaned data:** the viewer is built from a cleaned copy: `build_web.py` first runs `clean_csv.py`
(use `--raw` to skip it). `python src/clean_csv.py` alone writes a normalised copy of the Ahnenblatt export to
`data/cleaned/family_tree_cleaned.csv` (ISO dates, countries, nicknames, addresses, …) plus a log of
every change and a list of values that still need a decision. Corrections that are specific to this
family live in private files next to it (`manual_fixes.tsv`, `place_countries.tsv`, `new_people.tsv`).

**Editing:** the ✏️ button in the viewer turns the info panel into a form. Changes are only collected in your browser and downloaded as a file; nothing is saved
online. Put the file into `data/cleaned/inbox/` and run `python src/review_edits.py`: it shows every
change and only what you accept goes into the private fix files (accepted photos are saved into
`data/img/` with the right name). Then publish as usual.

**Photos:** put them into `data/img/`. Name each file after the person's ID (shown at the top of the
person's info panel, e.g. `I81`) plus an optional date: `I81_2019-06-12.jpg`, `I81_2019-06.jpg`,
`I81_2019.jpg` or just `I81.jpg`. `Surname_Given_2019.jpg` also works, but only if exactly one person
has that name (the build prints a warning otherwise). A person can have several photos: the card shows
the newest; clicking it opens all of them (‹ › or swipe). JPG, PNG and WebP; ~1200 px wide is plenty.
The build embeds them in the data, so `--publish` encrypts them like everything else.

### Update the website after changing the tree

1. Once: `pip install -r requirements.txt`
2. In Ahnenblatt, export the tree as CSV to `data/ahnenblatt/2023_05_StammbaumFBeaumont.csv`.
3. Run `python src/build_web.py --publish` and enter the password twice (it is asked for, not typed
   into the command). This writes `public/`.
4. Commit and push `public/`. The workflow `.github/workflows/pages.yml` deploys it within about a
   minute, and refuses to deploy if `public/` contains unencrypted data.

Use a long passphrase (4+ random words): the encrypted file is public and could be attacked offline.

### Private zip version (no password)

`python src/build_web.py` builds `web/` with unencrypted data. Zip the folder and send it;
the recipient double-clicks `index.html`. Internet is needed on first open (libraries load from a CDN).

### Under the hood

- **Data**: CSV (UTF-16, tab-separated, GEDCOM-style columns) → `people` + `families` JSON.
- **Encryption**: AES-256-GCM, key derived from the password with PBKDF2-SHA256 (600 000 iterations);
  decrypted in the browser with the Web Crypto API.
- **Layout**: partners (and chains of remarriages) are merged into one block so they sit side by side;
  each couple gets a small family dot, children hang below it. [ELK](https://eclipse.dev/elk/)'s layered
  algorithm places everything to reduce crossing lines.
- **Rendering**: SVG with [d3](https://d3js.org/) pan/zoom, a minimap, search, and lineage highlighting.
- No person is preferred: the viewer opens on the whole tree.
