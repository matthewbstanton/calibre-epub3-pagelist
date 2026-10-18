# Development

Everything a contributor needs to build, test and change the plugin. For what the plugin does and how to use it, see [README.md](README.md).

## Requirements

- Python 3.10+
- `lxml`

```bash
pip install -r requirements-dev.txt
```

Calibre is not needed to run the tests. It is only needed to try the plugin in the real app.

## Running Unit Tests

Unit tests run using mock container objects and do not require Calibre to be installed:

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

### Continuous integration

`.github/workflows/test.yml` ("Unit Tests") runs on every push to `master` and on every pull request targeting `master`. On Ubuntu, for Python 3.10, 3.11, 3.12 and 3.13, it installs `requirements-dev.txt` and runs the same `unittest discover` command as above. Run it locally before you open a pull request.

## Building the Plugin ZIP

To package the plugin for distribution or installation:

```bash
python3 build.py
```

This writes `epub3_pagelist.zip` in the repo root.

To choose the file name (for example a versioned one), pass `--output`:

```bash
python3 build.py --output epub3_pagelist-1.0.7.zip
```

To build and immediately install/update into your local Calibre (needs `calibre-customize` on your `PATH`):

```bash
python3 build.py --install
```

If `calibre-customize` isn't found, the script says so and you can load the ZIP from Calibre instead: **Preferences → Plugins → Load plugin from file**.

When you add a top-level file or directory that should ship, add it to `INCLUDES` in `build.py`.

### Automated build and release

`.github/workflows/build.yml` ("Build Plugin") runs after the "Unit Tests" workflow completes successfully for a push to `master` (so after a PR is merged). It can also be started by hand with `workflow_dispatch`. If the tests fail, nothing is built.

1. It runs `python3 build.py`.
2. It uploads `epub3_pagelist.zip` as a workflow artifact named `epub3_pagelist-<short commit SHA>`. Download it from the workflow run page.
3. It reads `version` from `__init__.py` (for example `(1, 0, 7)` becomes `1.0.7`). If no release with that tag exists, it creates a GitHub Release with that tag and attaches the ZIP. If the tag already exists, it skips the release, so merges without a version bump never create duplicates.

To publish a release, bump `version` in `__init__.py` in your PR and merge it.

## Project layout

### Plugin entry files (need Calibre)

- `__init__.py` — plugin descriptor (name, version, minimum Calibre version). Bump `version` here for releases.
- `action.py` — `EPUB3PageListAction` (`InterfaceAction`): toolbar button and menu, the batch loop over selected books, summary dialogs. Glue between Calibre and `core/`.
- `config.py` — settings widget and `plugin_prefs` (`JSONConfig`).
- `utils.py` — icon loading from the plugin ZIP.
- `fetcher.py` — `CalibreFetcher`: fetches web pages with Calibre's browser for the Goodreads and Amazon sources.
- `plugin-import-name-epub3_pagelist.txt` — makes Calibre import the plugin as `calibre_plugins.epub3_pagelist`.
- `images/` — toolbar icon.
- `build.py` — builds the ZIP (see above).

### `core/` (no Calibre, no Qt)

- `paginator.py` — computes `PageBreak` positions. `paginate()` uses characters per page, snaps to paragraphs and starts each spine item on a new page. `fit_to_page_count()` aims for a target page count instead.
- `page_list_remover.py` — `PageListRemover`: the "Remove page list" menu action. Strips markers, nav page-list, NCX `pageList`, `page-map.xml` and metadata, but only from books with the plugin's footprint.
- `page_planner.py` — `plan_pages()` decides what a book gets (keep its existing page-list, use its own print page markers, or paginate) and returns a `PagePlan` without writing anything.
- `existing_markers.py` — `ExistingMarkerDetector`: finds print page markers already in a book.
- `marker_injector.py` — inserts and removes `doc-pagebreak` markers in content documents.
- `nav_builder.py` — writes the page-list into `nav.xhtml` and `toc.ncx`, generates `page-map.xml`, and adds accessibility metadata to the OPF.
- `page_count_column.py` — column name normalising and type checks for the "Save page count to column" option.
- `page_count/` — page count sources, one class per file. Each implements `PageCountSource.get_page_count(db, book_id)` from `base.py`:
  - `chars_per_page.py` (`CharsPerPageSource`), `custom_column.py` (`CustomColumnSource`)
  - `goodreads/` (`GoodreadsSource`) and `amazon/` (`AmazonSource`): `source.py` reads the identifier and fetches; `parser.py` builds the URL and parses the page count from HTML (no network). `AmazonSource` takes the identifier name and a label, so the `amazon` and `mobi-asin` options share it.
  - Every source has a `label` (e.g. `Amazon ID`). `PagePlan.origin` turns it into the "from ..." text that the summary dialogs show next to each page count; give a new source a `label`.
  - `fetch.py` — `FetchResult`, the result of a web request.
  - `factory.py` — `create_page_count_source()` maps the `page_count_source` pref to a source. `action.py` calls it and passes in `CalibreFetcher().fetch`.

### `tests/`

One `test_*.py` per area (`test_core.py`, `test_page_planner.py`, `test_existing_markers.py`, `test_page_count.py`, `test_goodreads.py`, `test_amazon.py`, `test_page_map.py`, `test_page_list_remover.py`, `test_page_count_column.py`). They import `core` directly, e.g. `from core.paginator import ...`, and use a mock Polish container. Add tests next to the area you change.

## Rules for changing the code

- **`core/` must not import Calibre or Qt.** Code that needs Calibre goes in `action.py`, `fetcher.py`, `config.py` or `utils.py`.
- Calibre code imports plugin modules through the `calibre_plugins.epub3_pagelist.*` namespace, not by relative or top-level imports.
- Qt imports go through `qt.core`, not `PyQt5`/`PyQt6`.
- Re-running with overwrite enabled must be idempotent. `action.py` calls `MarkerInjector.remove_existing_markers()` before it injects, and `NavBuilder` replaces existing page-lists instead of appending. With overwrite disabled, books that already have a page-list are skipped.
- Network code stays out of parsers. Parsers take HTML and return values, so tests need no network.

## Design principles (SOLID, within reason)

The code is already split along these lines. Follow the existing structure rather than adding abstractions for their own sake.

- **Single responsibility.** Each module does one job: `paginator.py` decides where breaks go, `marker_injector.py` edits content documents, `nav_builder.py` writes navigation files, `page_planner.py` decides what a book gets, `goodreads/parser.py` only parses. Keep `action.py` as glue; put logic in `core/` where it can be tested.
- **Open/closed.** Add behaviour by adding a class, not by editing a branching function. To add a page count source:
  1. Create a class implementing `PageCountSource.get_page_count(db, book_id)` in `core/page_count/`, returning a `PageCount`.
  2. Add a `SOURCE_*` value to `PAGE_COUNT_SOURCES` and a branch in `create_page_count_source()` in `factory.py`.
  3. Add the option in `config.py` and document it in `README.md`.
  4. Add tests. `paginator.py` and `page_planner.py` don't change.
- **Liskov substitution.** Every `PageCountSource` must be usable wherever another is. Report "can't do this book" through `PageCount.skip_reason`, not by raising or returning something the caller has to special-case.
- **Interface segregation.** Keep interfaces small. `PageCountSource` has one method; `core/` functions take only what they need (a container, a config, a count) instead of the whole database or prefs object.
- **Dependency inversion.** High-level code depends on abstractions passed in, not on Calibre. The factory takes a `fetch` callable instead of importing `CalibreFetcher`, and `core/` works on a container object, so tests use mocks and no Calibre install.

Don't split a module or add an interface until a second use or a test needs it.
