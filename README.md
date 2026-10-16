Original repo https://github.com/Kaspyy/calibre-epub3-pagelist/

# EPUB3 Page List Generator (Calibre Plugin)

[![Unit Tests](https://github.com/Kaspyy/calibre-epub3-pagelist/actions/workflows/test.yml/badge.svg?branch=master)](https://github.com/Kaspyy/calibre-epub3-pagelist/actions/workflows/test.yml)
[![Calibre](https://img.shields.io/badge/Calibre-6.0%2B-blue.svg)](https://calibre-ebook.com/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

A Calibre plugin that automatically generates and injects synthetic page-list navigation into EPUB 3 ebooks.

---

## Overview

Many modern e-readers and reading apps (including **Amazon Kindle** via *Send to Kindle*, **Kobo**, **Apple Books**, and **Adobe Digital Editions**) support real-feeling page numbers through standard page-list navigation structures. Without them, readers are often left with abstract "locations" or percentages.

**EPUB3 Page List Generator** scans EPUB 3 ebooks, calculates synthetic page break positions using **Kindle-standard character-count pagination** (~1,850 characters per page), and injects universal multi-format page navigation without altering the book's visual rendering or formatting.

---

## Features

- **Universal Multi-Format Compatibility**:
  - **EPUB 3 Navigation Document**: Injects `<nav epub:type="page-list">` with `doc-pagebreak` milestones into `nav.xhtml`.
  - **EPUB 2 NCX Fallback**: Injects `<pageList>` into `toc.ncx` (ensures page numbers work when sending EPUBs to Kindle via *Send to Kindle*).
  - **Adobe Page Map**: Generates `page-map.xml` for Adobe Digital Editions and legacy reading engines.
  - **EPUB Accessibility Metadata**: Automatically adds `schema:accessibilityFeature` (`pageBreakMarkers`, `pageNavigation`) and, for synthetic pages, `pageBreakSource: none` to the OPF package.
- **Real Print Pages When Available**:
  - Retail EPUBs often already mark their print pages but lack a complete page-list. The plugin can build the page-list from those markers instead of generating synthetic pages.
- **Smart Paragraph Snapping**:
  - Automatically aligns page breaks with paragraph/block boundaries to avoid breaking in the middle of sentences.
- **Section-Aware Pagination**:
  - Automatically starts each major spine item (e.g., Cover, Title Page, Table of Contents, Chapters) on a new page.
- **Batch Processing**:
  - Select one or dozens of books in your Calibre library and paginate them all in a single click.
- **Safe & Non-Destructive**:
  - Automatically skips EPUB 2 files (shows informative summary after processing).
  - Safe marker cleanup: cleanly removes previously generated synthetic markers when re-running or updating. Print page markers that came with the book are never removed.
- **Customizable**:
  - Configurable characters-per-page target, snapping threshold, overwrite behavior, and an optional custom column, Goodreads ID or Amazon ID to set each book's page count.

---

## Installation

### Method 1: Using Calibre GUI (Recommended)

1. Download the latest `epub3_pagelist.zip` from the [Releases](https://github.com/Kaspyy/calibre-epub3-pagelist/releases) tab (or build it from source).
2. Open **Calibre**.
3. Go to **Preferences** (`Ctrl+P` or `Cmd+,`) → **Advanced** → **Plugins**.
4. Click **Load plugin from file** in the bottom right corner.
5. Select `epub3_pagelist.zip` and confirm any security prompts.
6. Restart Calibre when prompted.

### Method 2: Using Calibre CLI

```bash
calibre-customize -a epub3_pagelist.zip
```

---

## How to Use

1. Select one or more **EPUB 3** books in your Calibre library.
2. Click the **Generate Page List** icon in the Calibre toolbar.
3. The plugin will process the selected books and display a summary dialog showing:
   - Number of successfully processed books
   - Any skipped non-EPUB3 or already-paginated titles
   - Any errors encountered (with full tracebacks available)

---

## Configuration

You can customize plugin behavior via **Preferences** → **Plugins** → **EPUB3 Page List Generator** → **Customize plugin**, or straight from the toolbar: click the arrow next to the **Generate Page List** button and choose **Customize plugin…**. Both open the same settings.

| Setting | Default | Description |
|---|---|---|
| **Page count source** | Characters per page | Radio group that picks how the page count is decided. See the options below. |
| ↳ **Characters per page** | `1850` | Default option. Splits the book into pages of this many characters (based on standard Kindle pagination). The spin box is only enabled when this option is selected. |
| ↳ **Custom column** | empty | Reads each book's page count from a Calibre custom column and generates a page-list with that many pages (or the closest count it can reach). Enter the column's lookup name, e.g. `#pages` (the leading `#` is optional). Must be a numeric column. The name box is only enabled when this option is selected. |
| ↳ **Use Goodreads Id** | — | Looks up each book's `goodreads` identifier (as stored by the Goodreads metadata source plugin), fetches `https://www.goodreads.com/book/show/<id>` and generates a page-list with the page count shown there (or the closest count it can reach). Needs an internet connection. |
| ↳ **Use Amazon Id** | — | Looks up each book's `amazon` identifier (the ASIN, as stored by Calibre's Amazon metadata source), fetches `https://www.amazon.com/dp/<ASIN>` and generates a page-list with the print length shown there (or the closest count it can reach). Only the `amazon` identifier is used; regional ones such as `amazon_uk` are ignored. Needs an internet connection. |
| **Existing page markers** | Use the book's page markers, generate pages if it has none | Radio group that picks what to do with print page markers already in the book. See [Existing page markers](#existing-page-markers). |
| ↳ **Use the book's page markers, generate pages if it has none** | — | Default option. If the book marks its print pages, builds the page-list from those real page numbers and adds no synthetic markers. Books without markers are paginated with the page count source as usual. |
| ↳ **Use the book's page markers, skip books without them** | — | As above, but books without page markers are skipped and listed in the summary dialog. |
| ↳ **Ignore page markers, always generate pages** | — | Always paginates with the page count source, as earlier versions did. |
| **Snap to paragraph boundaries** | `True` | Snaps page breaks to nearby paragraph tags (`<p>`, `<div>`, etc.) for cleaner breaks. |
| **Overwrite existing page-list** | `False` | If enabled, replaces any existing page-list markers. If disabled, already-paginated books will be skipped. |

If you used the earlier **Use custom column for page count** checkbox, your setting carries over: if it was ticked, **Custom column** is selected.

When **Use Goodreads Id** or **Use Amazon Id** is selected, a book is skipped, and listed with the reason in the summary dialog, if it has no ID of that kind, the page can't be fetched (each request times out after 30 seconds), or no page count can be found on it. Amazon sometimes answers automated requests with a bot check page instead of the product page; those books are skipped with "no page count found", and "Show details" shows the response. The other books in the batch are still processed. Books that already have a page list with overwrite disabled are skipped before any request is made.

### Existing page markers

Unless **Ignore page markers, always generate pages** is selected, the plugin looks for print page markers before it paginates a book. It uses the first of these it finds:

1. **An existing page-list**: a nav page-list, NCX `pageList` or `page-map.xml` whose links point at elements in the book. This completes a book that has only one or two of the three.
2. **Page break markers**: elements with `epub:type="pagebreak"` or `role="doc-pagebreak"`, e.g. `<span epub:type="pagebreak" id="page_12" title="12"/>`. The page number comes from `aria-label`, `title` or the element's text. A marker without an `id` is given one (`page-12`).
3. **Page-like ids**: empty `<a>` or `<span>` elements (or ones whose only text is the page number) with ids such as `page12`, `page_12`, `p12`, `pg12`, `Page_xii` or `pagexii`, including roman numerals for front matter. Only used when the book has no page break markers, and only if there are at least 10 of them and their numbers go up in reading order (arabic and roman numbers are checked separately), so that ordinary ids such as paragraph numbers aren't mistaken for pages.

The nav page-list, NCX `pageList` and `page-map.xml` are then built from those markers, and no synthetic markers are added. Because the pages follow a print edition, `pageBreakSource: none` is not added (and an existing `none` is removed). The page count source isn't used for these books, so no web request is made for them.

The **Overwrite existing page-list** setting still applies: with it off, a book that already has any page-list (even one of the three) is skipped. To complete a partial page-list, tick **Overwrite existing page-list**; the page-list is then rebuilt from the existing one.

The default uses the book's markers because real print page numbers are what a page-list is for: they match citations, book clubs and the printed edition, and a book without markers is paginated exactly as before. Select **Use the book's page markers, skip books without them** if you only want page-lists for books with real print pages.

Markers the plugin adds are tagged with `data-epub3-pagelist="synthetic"`, and only those (plus untagged markers from older plugin versions, recognised by their exact form and numbering) are removed when a page-list is regenerated.

When **Custom column** is selected, the plugin shows a dialog after processing listing the page count read for each book. A book whose column is empty or non-numeric, or a column name that doesn't exist, is reported as an error for that book.

---

## Development & Building

### Requirements
- Python 3.10+
- `lxml`

```bash
pip install -r requirements-dev.txt
```

### Running Unit Tests

Unit tests run using mock container objects and do not require Calibre to be installed:

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

### Building the Plugin ZIP

To package the plugin for distribution or installation:

```bash
python3 build.py
```

To build and immediately install/update into your local Calibre:

```bash
python3 build.py --install
```

---

## License

This project is licensed under the **GNU General Public License v3.0** (GPL-3.0) — see the [LICENSE](LICENSE) file for details.

