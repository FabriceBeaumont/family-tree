# Stammbaum Explorer (web)

Pan/zoom family-tree map built from an Ahnenblatt CSV export.

## Update after editing in Ahnenblatt

1. In Ahnenblatt: export the tree as CSV (overwrite `Windows_Ahnenblatt/2023_05_StammbaumFBeaumont.csv`, or any path).
2. `python web/build_data.py [path/to/export.csv]` → regenerates `web/data.js`.
3. Open `web/index.html` in a browser (double-click works; or `python -m http.server 8765 --directory web`).

## Files

- `build_data.py` — CSV (UTF-16, tab-separated, GEDCOM-style columns) → `data.js` (people + families). No dependencies.
- `index.html` — viewer. Uses d3 (pan/zoom) and elkjs (layout) from the jsdelivr CDN, so it needs internet on first load.
- `data.js` — generated, do not edit.

## How the layout works

- Partners (and chains of multiple marriages) are merged into one block so they always sit side by side.
- Each couple gets a small "family" dot one layer below; children hang below the dot.
- ELK's layered algorithm places blocks to reduce edge crossings. Start person is set via `HOME_GIVEN` / `HOME_SURNAME` in `index.html`.
