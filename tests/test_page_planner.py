"""
Unit tests for core.page_planner: deciding a book's pages without writing them.

Uses a mock Polish container; no Calibre needed.
"""
import os
import sys
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.marker_injector import MarkerInjector, find_plugin_markers
from core.nav_builder import NavBuilder
from core.page_count.base import PageCount, PageCountSource
from core.page_planner import (plan_pages, PLAN_EXISTING, PLAN_MARKERS, PLAN_GENERATED, PLAN_NO_MARKERS,
                               PLAN_NO_PAGE_COUNT, PLAN_EMPTY)
from core.paginator import Paginator, PaginationConfig
from test_existing_markers import make_container, XHTML_NS, EPUB_OPS_NS

NAV_ITEM = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
CONFIG = PaginationConfig(chars_per_page=500, snap_to_paragraph=False)


class FakeSource(PageCountSource):
    """Returns a fixed answer and counts how often it was asked."""

    def __init__(self, result=None):
        self.result = result or PageCount()
        self.calls = 0

    def get_page_count(self, db, book_id):
        self.calls += 1
        return self.result


def nav_xml(page_list=''):
    return (f'<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_OPS_NS}"><head><title>Nav</title></head>'
            f'<body><nav epub:type="toc"><ol/></nav>{page_list}</body></html>')


def make_book(body=None, page_list=''):
    body = body if body is not None else ''.join(f'<p>{"Word " * 60}</p>' for _ in range(20))
    return make_container({'ch1.xhtml': body}, extra_files={'nav.xhtml': nav_xml(page_list)},
                          manifest_extra=NAV_ITEM)


def retail_body(count=10):
    return ''.join(f'<p>{"Word " * 20}<span epub:type="pagebreak" id="page_{n}" title="{n}"/></p>'
                   for n in range(1, count + 1))


def plan(container, source, overwrite=False, use_markers=True, markers_only=False):
    return plan_pages(container, source, None, 1, CONFIG, overwrite,
                      use_markers=use_markers, markers_only=markers_only)


class TestPlanPages(unittest.TestCase):

    def test_existing_page_list_is_kept_when_not_overwriting(self):
        page_list = ('<nav epub:type="page-list"><ol>'
                     + ''.join(f'<li><a href="ch1.xhtml#p{n}">{n}</a></li>' for n in range(1, 8))
                     + '</ol></nav>')
        container, _ = make_book(page_list=page_list)
        source = FakeSource(PageCount(pages=3))
        result = plan(container, source)
        self.assertEqual(result.outcome, PLAN_EXISTING)
        self.assertEqual(result.page_count, 7)
        self.assertEqual(source.calls, 0)

    def test_book_markers_are_used_without_asking_the_source(self):
        container, _ = make_book(body=retail_body(10))
        source = FakeSource(PageCount(pages=3))
        result = plan(container, source)
        self.assertEqual(result.outcome, PLAN_MARKERS)
        self.assertTrue(result.from_markers)
        self.assertEqual(result.page_count, 10)
        self.assertEqual(source.calls, 0)

    def test_book_markers_ignored_when_disabled(self):
        container, _ = make_book(body=retail_body(10))
        result = plan(container, FakeSource(PageCount(pages=3)), use_markers=False)
        self.assertEqual(result.outcome, PLAN_GENERATED)
        self.assertEqual(result.target_pages, 3)

    def test_markers_only_skips_books_without_markers(self):
        container, _ = make_book()
        source = FakeSource()
        result = plan(container, source, markers_only=True)
        self.assertEqual(result.outcome, PLAN_NO_MARKERS)
        self.assertIsNone(result.page_count)
        self.assertEqual(source.calls, 0)

    def test_source_target_count_is_paginated_without_changing_the_book(self):
        container, trees = make_book()
        result = plan(container, FakeSource(PageCount(pages=4)))
        self.assertEqual(result.outcome, PLAN_GENERATED)
        self.assertEqual(result.page_count, len(Paginator(container, CONFIG).fit_to_page_count(4)))
        self.assertEqual(result.target_pages, 4)
        # Nothing was written: no markers and no page-list
        self.assertEqual(find_plugin_markers(container), {})
        self.assertFalse(NavBuilder(container).has_existing_page_list())

    def test_chars_per_page_matches_paginate(self):
        container, _ = make_book()
        result = plan(container, FakeSource())
        self.assertEqual(result.outcome, PLAN_GENERATED)
        self.assertIsNone(result.target_pages)
        self.assertEqual(result.page_count, len(Paginator(container, CONFIG).paginate()))

    def test_source_skip_is_reported(self):
        container, _ = make_book()
        result = plan(container, FakeSource(PageCount(skip_reason='no id', details='more')))
        self.assertEqual(result.outcome, PLAN_NO_PAGE_COUNT)
        self.assertEqual(result.source_result.skip_reason, 'no id')
        self.assertIsNone(result.page_count)

    def test_empty_book_has_no_pages(self):
        container, _ = make_book(body='')
        result = plan(container, FakeSource())
        self.assertEqual(result.outcome, PLAN_EMPTY)
        self.assertIsNone(result.page_count)

    def test_overwrite_ignores_the_plugins_own_markers(self):
        container, _ = make_book()
        pages = Paginator(container, CONFIG).paginate()
        MarkerInjector(container).inject_markers(pages)
        NavBuilder(container).build_page_list(pages, overwrite=True, synthetic=True)

        # Overwrite off: the existing page-list is counted
        self.assertEqual(plan(container, FakeSource()).outcome, PLAN_EXISTING)

        # Overwrite on: the plugin's markers are removed and pages generated again
        result = plan(container, FakeSource(), overwrite=True)
        self.assertEqual(result.outcome, PLAN_GENERATED)
        self.assertEqual(result.page_count, len(pages))
        self.assertEqual(find_plugin_markers(container), {})


if __name__ == '__main__':
    unittest.main()
