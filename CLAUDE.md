Calibre GUI plugin that injects synthetic page-list navigation (EPUB3 `nav` page-list, NCX `pageList`, Adobe `page-map.xml`) into EPUB 3 books. See `README.md` for user-facing behaviour and settings.

## Commands

- Tests: `python3 -m unittest discover -s tests -p "test_*.py" -v` (CI runs this on Python 3.10–3.13; only dependency is `lxml`)
- Build: `python3 build.py` → `epub3_pagelist.zip`
- Build + install into local Calibre: `python3 build.py --install` (needs `calibre-customize` on PATH)

## Layout

- `__init__.py` — plugin descriptor (name, version, min Calibre version). Bump `version` here for releases.
- `main.py` — `InterfaceAction`: toolbar button, batch loop over selected books, summary dialogs. Glue between Calibre and `core/`.
- `config.py` — settings widget and `plugin_prefs` (`JSONConfig`).
- `utils.py` — icon loading from the plugin ZIP.
- `core/paginator.py` — computes `PageBreak` positions. `paginate()` uses characters per page, snaps to paragraphs and starts each spine item on a new page. `fit_to_page_count()` aims for a target page count instead (used by the custom-column option).
- `core/marker_injector.py` — inserts and removes `doc-pagebreak` markers in content documents.
- `core/nav_builder.py` — writes the page-list into `nav.xhtml` and `toc.ncx`, generates `page-map.xml`, and adds accessibility metadata to the OPF.

## Constraints

- **`core/` must not import Calibre or Qt.** Tests import it directly (`from core.paginator import ...`) with a mock Polish container and no Calibre installed. Code that needs Calibre goes in `main.py`/`config.py`/`utils.py`.
- Calibre code imports plugin modules through the `calibre_plugins.epub3_pagelist.*` namespace (set by `plugin-import-name-epub3_pagelist.txt`), not by relative or top-level imports.
- Qt imports go through `qt.core`, not `PyQt5`/`PyQt6`.
- When you add a top-level file or directory that should ship, add it to `INCLUDES` in `build.py`.
- Re-running with overwrite enabled must be idempotent. `main.py` calls `MarkerInjector.remove_existing_markers()` before it injects, and `NavBuilder` replaces existing page-lists instead of appending. With overwrite disabled, books that already have a page-list are skipped.

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
