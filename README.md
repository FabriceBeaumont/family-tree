# family-tree

My family tree, maintained in [Ahnenblatt](https://www.ahnenblatt.de/), plus Python/web tools to visualize it.

## Layout

| Folder | Committed? | Contents |
|---|---|---|
| `src/` | yes | Source code: `build_web.py` (CSV → web viewer), `index.html` (viewer template) |
| `docs/` | yes | Blank questionnaire for collecting data from relatives |
| `data/` | **no** (private) | `ahnenblatt/` (`.ahn` + CSV export), `exports/` (Ahnenblatt HTML + PDF reports), `img/` (profile pictures, for later use), `archive/` |
| `web/` | **no** (generated) | Shareable viewer: `index.html` + `data.js`. Zip it to share, or upload to a web host |

`data/` and `web/` contain personal data of living people and are gitignored.

## Build the web viewer

1. In Ahnenblatt: export the tree as CSV to `data/ahnenblatt/2023_05_StammbaumFBeaumont.csv`.
2. Run `python src/build_web.py` (or pass another CSV path as argument). No dependencies.
3. Open `web/index.html` in a browser (double-click works).

The viewer loads d3 (pan/zoom) and elkjs (layout) from the jsdelivr CDN, so it needs internet on first load.

## How the layout works

- Partners (and chains of multiple marriages) are merged into one block so they always sit side by side.
- Each couple gets a small "family" dot one layer below; children hang below the dot.
- ELK's layered algorithm places the blocks to reduce edge crossings.
- The start person is set via `HOME_GIVEN` / `HOME_SURNAME` in `src/index.html`.
