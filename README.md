# family-tree

My family tree, maintained in [Ahnenblatt](https://www.ahnenblatt.de/), plus Python/web tools to visualize it.

## Layout

| Folder | Committed? | Contents |
|---|---|---|
| `src/` | yes | Source code: `build_web.py` (CSV → web viewer), `index.html` (viewer template) |
| `docs/` | yes | Blank questionnaire for collecting data from relatives |
| `data/` | **no** (private) | `ahnenblatt/` (`.ahn` + CSV export), `exports/` (Ahnenblatt HTML + PDF reports), `img/` (profile pictures, for later use), `archive/` |
| `web/` | **no** (generated) | Private viewer with plain data: `index.html` + `data.js`. Zip it to share |
| `public/` | yes (generated) | Password-encrypted viewer, deployed to GitHub Pages |

`data/` and `web/` contain personal data of living people and are gitignored.
`public/` only contains the data encrypted (AES-256-GCM, key from your password via PBKDF2-SHA256, 600k iterations).

## Build the web viewer

1. In Ahnenblatt: export the tree as CSV to `data/ahnenblatt/2023_05_StammbaumFBeaumont.csv`.
2. Run `python src/build_web.py` (or pass another CSV path as argument). No dependencies.
3. Open `web/index.html` in a browser (double-click works).

The viewer loads d3 (pan/zoom) and elkjs (layout) from the jsdelivr CDN, so it needs internet on first load.

## Publish to GitHub Pages (password-protected)

1. Once: `pip install -r requirements.txt`
2. `python src/build_web.py --publish` → asks for the password, writes `public/`.
   Use a long passphrase: the encrypted file is public and can be attacked offline.
3. Commit and push `public/`. The workflow `.github/workflows/pages.yml` deploys it
   (it refuses to deploy if `public/` contains unencrypted data).

Re-run step 2 after every Ahnenblatt export. Visitors enter the password once per browser tab.

## How the layout works

- Partners (and chains of multiple marriages) are merged into one block so they always sit side by side.
- Each couple gets a small "family" dot one layer below; children hang below the dot.
- ELK's layered algorithm places the blocks to reduce edge crossings.
- The start person is set via `HOME_GIVEN` / `HOME_SURNAME` in `src/index.html`.
