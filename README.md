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
  - **EPUB Accessibility Metadata**: Automatically adds `schema:accessibilityFeature` (`pageBreakMarkers`, `pageNavigation`) and `pageBreakSource: none` to the OPF package.
- **Smart Paragraph Snapping**:
  - Automatically aligns page breaks with paragraph/block boundaries to avoid breaking in the middle of sentences.
- **Section-Aware Pagination**:
  - Automatically starts each major spine item (e.g., Cover, Title Page, Table of Contents, Chapters) on a new page.
- **Batch Processing**:
  - Select one or dozens of books in your Calibre library and paginate them all in a single click.
- **Safe & Non-Destructive**:
  - Automatically skips EPUB 2 files (shows informative summary after processing).
  - Safe marker cleanup: cleanly removes previously generated synthetic markers when re-running or updating.
- **Customizable**:
  - Configurable characters-per-page target, snapping threshold, overwrite behavior, and an optional custom column to set each book's page count.

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

You can customize plugin behavior via **Preferences** → **Plugins** → **EPUB3 Page List Generator** → **Customize plugin**:

| Setting | Default | Description |
|---|---|---|
| **Characters per page** | `1850` | Target character count per page (based on standard Kindle pagination). |
| **Snap to paragraph boundaries** | `True` | Snaps page breaks to nearby paragraph tags (`<p>`, `<div>`, etc.) for cleaner breaks. |
| **Overwrite existing page-list** | `True` | If enabled, replaces any existing page-list markers. If disabled, already-paginated books will be skipped. |
| **Use custom column for page count** | `False` | If enabled, the plugin reads each book's page count from a Calibre custom column and generates a page-list with that many pages (or the closest count it can reach). If disabled, **Characters per page** is used. |
| **Custom column name** | empty | Lookup name of the custom column holding the page count, e.g. `#pages` (the leading `#` is optional). Must be a numeric column. Only used when **Use custom column for page count** is enabled. |

When the custom column is enabled, the plugin shows a dialog after processing listing the page count read for each book. A book whose column is empty or non-numeric, or a column name that doesn't exist, is reported as an error for that book.

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

