"""
Tests for PageListRemover: it strips what the plugin added and leaves the
book's own print page markers and page-list alone.
"""
import os
import sys
import unittest
from lxml import etree

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.marker_injector import MarkerInjector, find_plugin_markers
from core.nav_builder import NavBuilder
from core.page_list_remover import PageListRemover
from core.paginator import PageBreak
from test_page_map import PAGE_MAP_TYPE, XHTML_NS, EPUB_OPS_NS, OPF_NS, make_book


def print_marker():
    span = etree.Element(f'{{{XHTML_NS}}}span', nsmap={'epub': EPUB_OPS_NS})
    span.set(f'{{{EPUB_OPS_NS}}}type', 'pagebreak')
    span.set('role', 'doc-pagebreak')
    span.set('id', 'print_7')
    span.set('title', '7')
    return span


def generated_book(with_print_marker=False):
    """A book the plugin has paginated, with page-list, NCX, page-map and metadata."""
    container = make_book()
    root = container.parsed('ch1.xhtml')
    paragraphs = root.findall(f'.//{{{XHTML_NS}}}p')
    if with_print_marker:
        paragraphs[4].append(print_marker())
    pages = [PageBreak('ch1.xhtml', f'page_{i}', str(i), p, 'before') for i, p in enumerate(paragraphs[:3], 1)]
    MarkerInjector(container).inject_markers(pages)
    NavBuilder(container).build_page_list(pages, overwrite=True, synthetic=True)
    return container


class TestPageListRemover(unittest.TestCase):

    def test_removes_everything_the_plugin_added(self):
        container = generated_book()
        self.assertTrue(PageListRemover(container).has_plugin_footprint())

        result = PageListRemover(container).remove()

        self.assertEqual(result.markers, 3)
        self.assertTrue(result.nav)
        self.assertTrue(result.ncx)
        self.assertEqual(result.page_maps, 1)
        self.assertEqual(result.metadata, 3)
        self.assertEqual(find_plugin_markers(container), {})
        ns = {'x': XHTML_NS, 'e': EPUB_OPS_NS}
        self.assertFalse(container.parsed('nav.xhtml').xpath('//x:nav[@e:type="page-list"]', namespaces=ns))
        self.assertFalse(container.parsed('toc.ncx').xpath('//*[local-name()="pageList"]'))
        self.assertFalse(container.opf_xpath(f'//opf:item[@media-type="{PAGE_MAP_TYPE}"]'))
        self.assertFalse(container.has_name('page-map.xml'))
        self.assertIsNone(container.opf.find(f'{{{OPF_NS}}}spine').get('page-map'))
        self.assertIsNone(container.opf.get('page-map'))
        self.assertFalse(container.opf_xpath('//*[local-name()="meta"][@property]'))

    def test_keeps_print_page_markers(self):
        container = generated_book(with_print_marker=True)
        PageListRemover(container).remove()
        self.assertEqual(len(container.parsed('ch1.xhtml').xpath('//*[@id="print_7"]')), 1)

    def test_book_without_plugin_footprint_is_untouched(self):
        """A retail book's own page-list is not the plugin's to remove."""
        container = make_book('page-map.xml', old_pages=[('1', 'ch1.xhtml#p1')])
        result = PageListRemover(container).remove()
        self.assertFalse(result.changed)
        self.assertTrue(container.has_name('page-map.xml'))

    def test_second_run_changes_nothing(self):
        container = generated_book()
        PageListRemover(container).remove()
        self.assertFalse(PageListRemover(container).remove().changed)


if __name__ == '__main__':
    unittest.main()
