"""
Unit tests for the EPUB3 Page List Generator plugin.

These tests use mock objects to simulate Calibre's Polish Container API,
allowing testing without a full Calibre installation.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock
from lxml import etree

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.paginator import Paginator, PaginationConfig, PageBreak, XHTML_NS
from core.marker_injector import MarkerInjector, PLUGIN_MARKER_ATTR, PLUGIN_MARKER_VALUE
from core.nav_builder import NavBuilder


# ---------------------------------------------------------------------------
# Helper: build a minimal XHTML document tree for testing
# ---------------------------------------------------------------------------

EPUB_OPS_NS = "http://www.idpf.org/2007/ops"


def make_xhtml_tree(body_html: str) -> etree._ElementTree:
    """Create an lxml ElementTree from a body HTML fragment."""
    xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_OPS_NS}">
<head><title>Test</title></head>
<body>
{body_html}
</body>
</html>"""
    return etree.ElementTree(etree.fromstring(xhtml.encode('utf-8')))


def make_mock_container(spine_docs: dict[str, str]):
    """
    Create a mock Calibre container with given spine documents.

    :param spine_docs: Mapping of spine_name -> body_html content.
    :returns: Mock container object.
    """
    container = MagicMock()
    trees = {}

    for name, body_html in spine_docs.items():
        trees[name] = make_xhtml_tree(body_html)

    container.spine_names = [(name, True) for name in spine_docs]
    container.spine_items = [name for name in spine_docs]
    container.parsed = lambda name: trees[name]
    container.dirty = MagicMock()
    container.opf_name = 'content.opf'

    def name_to_href(target, base=None):
        return target  # Simplified: no path resolution in tests

    container.name_to_href = name_to_href
    return container, trees


# ===========================================================================
# Paginator Tests
# ===========================================================================

class TestPaginator(unittest.TestCase):
    """Tests for core.paginator.Paginator."""

    def test_empty_document_produces_no_breaks(self):
        """An empty body should produce zero page breaks."""
        container, _ = make_mock_container({'ch1.xhtml': ''})
        paginator = Paginator(container, PaginationConfig(chars_per_page=100))
        breaks = paginator.paginate()
        self.assertEqual(breaks, [])

    def test_short_document_produces_no_breaks(self):
        """Text shorter than chars_per_page should only have the initial page 1 break."""
        container, _ = make_mock_container({
            'ch1.xhtml': '<p>Short text here.</p>'
        })
        paginator = Paginator(container, PaginationConfig(chars_per_page=1500))
        breaks = paginator.paginate()
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0].page_label, '1')

    def test_long_document_produces_breaks(self):
        """Text longer than chars_per_page should produce multiple breaks."""
        paragraphs = ''.join(
            f'<p>{"Lorem ipsum dolor sit amet. " * 20}</p>'
            for _ in range(10)
        )
        container, _ = make_mock_container({'ch1.xhtml': paragraphs})
        paginator = Paginator(container, PaginationConfig(chars_per_page=500))
        breaks = paginator.paginate()

        self.assertGreater(len(breaks), 1)
        for b in breaks:
            self.assertEqual(b.spine_name, 'ch1.xhtml')

    def test_page_numbering_is_sequential(self):
        """Page labels should be sequential starting from 1."""
        paragraphs = ''.join(
            f'<p>{"Word " * 100}</p>' for _ in range(10)
        )
        container, _ = make_mock_container({'ch1.xhtml': paragraphs})
        paginator = Paginator(container, PaginationConfig(chars_per_page=200))
        breaks = paginator.paginate()

        labels = [b.page_label for b in breaks]
        expected = [str(i + 1) for i in range(len(breaks))]
        self.assertEqual(labels, expected)

    def test_page_numbering_continues_across_documents(self):
        """Page numbering should be continuous across spine documents."""
        body = ''.join(f'<p>{"Word " * 100}</p>' for _ in range(5))
        container, _ = make_mock_container({
            'ch1.xhtml': body,
            'ch2.xhtml': body,
        })
        paginator = Paginator(container, PaginationConfig(chars_per_page=300))
        breaks = paginator.paginate()

        labels = [int(b.page_label) for b in breaks]
        self.assertEqual(labels, list(range(1, len(breaks) + 1)))

    def test_skip_elements_are_not_counted(self):
        """Text inside skip_elements (pre, code, etc.) should not generate additional page breaks."""
        body = f'<pre>{"A" * 5000}</pre>'
        container, _ = make_mock_container({'ch1.xhtml': body})
        paginator = Paginator(container, PaginationConfig(chars_per_page=100))
        breaks = paginator.paginate()
        # Only the initial page 1 break, no breaks generated from pre content
        self.assertEqual(len(breaks), 1)

    def test_anchor_ids_are_unique(self):
        """All anchor IDs must be unique."""
        body = ''.join(f'<p>{"Word " * 60}</p>' for _ in range(20))
        container, _ = make_mock_container({'ch1.xhtml': body})
        paginator = Paginator(container, PaginationConfig(chars_per_page=200))
        breaks = paginator.paginate()

        ids = [b.anchor_id for b in breaks]
        self.assertEqual(len(ids), len(set(ids)), "Anchor IDs must be unique")

    def test_document_with_comments_and_processing_instructions(self):
        """Documents containing XML comments or PIs should not cause QName/Cython errors."""
        body = """
        <!-- Comment before paragraph -->
        <p>Paragraph with text <!-- inline comment --> and more text.</p>
        <?pi test="1"?>
        <!-- Comment between paragraphs -->
        <p>""" + "Another paragraph with enough words to trigger page breaks. " * 30 + """</p>
        <!-- Trailing comment -->
        """
        container, _ = make_mock_container({'ch1.xhtml': body})
        paginator = Paginator(container, PaginationConfig(chars_per_page=200))
        breaks = paginator.paginate()
        self.assertGreater(len(breaks), 0)


# ===========================================================================
# MarkerInjector Tests
# ===========================================================================

class TestMarkerInjector(unittest.TestCase):
    """Tests for core.marker_injector.MarkerInjector."""

    def _make_breaks_and_container(self):
        """Helper to create a container and paginated breaks."""
        body = ''.join(f'<p>{"Word " * 60}</p>' for _ in range(10))
        container, trees = make_mock_container({'ch1.xhtml': body})
        paginator = Paginator(container, PaginationConfig(chars_per_page=300))
        breaks = paginator.paginate()
        return container, trees, breaks

    def test_inject_markers_inserts_spans(self):
        """inject_markers should insert pagebreak spans into the document."""
        container, trees, breaks = self._make_breaks_and_container()
        if not breaks:
            self.skipTest("No page breaks generated for this test input")

        injector = MarkerInjector(container)
        count = injector.inject_markers(breaks)

        self.assertEqual(count, len(breaks))

        # Verify spans exist in the tree
        tree = trees['ch1.xhtml']
        ns = {'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS}
        spans = tree.xpath('//xhtml:span[@epub:type="pagebreak"]', namespaces=ns)
        self.assertEqual(len(spans), len(breaks))

    def test_injected_spans_have_correct_attributes(self):
        """Each injected span should have id, role, epub:type, aria-label."""
        container, trees, breaks = self._make_breaks_and_container()
        if not breaks:
            self.skipTest("No page breaks generated")

        injector = MarkerInjector(container)
        injector.inject_markers(breaks)

        tree = trees['ch1.xhtml']
        ns = {'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS}
        spans = tree.xpath('//xhtml:span[@epub:type="pagebreak"]', namespaces=ns)

        for span in spans:
            self.assertIsNotNone(span.get('id'))
            self.assertEqual(span.get('role'), 'doc-pagebreak')
            self.assertIsNotNone(span.get('aria-label'))

    def test_remove_existing_markers(self):
        """remove_existing_markers should remove all pagebreak spans."""
        container, trees, breaks = self._make_breaks_and_container()
        if not breaks:
            self.skipTest("No page breaks generated")

        injector = MarkerInjector(container)
        injector.inject_markers(breaks)

        # Now remove them
        removed = injector.remove_existing_markers()
        self.assertEqual(removed, len(breaks))

        # Verify they're gone
        tree = trees['ch1.xhtml']
        ns = {'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS}
        spans = tree.xpath('//xhtml:span[@epub:type="pagebreak"]', namespaces=ns)
        self.assertEqual(len(spans), 0)

    def test_injected_spans_are_tagged(self):
        """Injected spans carry the plugin's data attribute."""
        container, trees, breaks = self._make_breaks_and_container()
        MarkerInjector(container).inject_markers(breaks)
        spans = trees['ch1.xhtml'].xpath('//xhtml:span', namespaces={'xhtml': XHTML_NS})
        self.assertTrue(spans)
        for span in spans:
            self.assertEqual(span.get(PLUGIN_MARKER_ATTR), PLUGIN_MARKER_VALUE)

    def test_remove_keeps_retail_markers(self):
        """Print page markers that came with the book are never removed."""
        retail = (
            '<p>A<span epub:type="pagebreak" id="page_12" title="12"/></p>'
            '<p>B<span role="doc-pagebreak" epub:type="pagebreak" id="page_13" aria-label="13"/></p>'
            '<p>C<a id="page14"/></p>'
        )
        body = retail + ''.join(f'<p>{"Word " * 60}</p>' for _ in range(5))
        container, trees = make_mock_container({'ch1.xhtml': body})
        breaks = Paginator(container, PaginationConfig(chars_per_page=300)).paginate()
        injector = MarkerInjector(container)
        injector.inject_markers(breaks)

        removed = injector.remove_existing_markers()

        self.assertEqual(removed, len(breaks))
        ns = {'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS}
        ids = [s.get('id') for s in trees['ch1.xhtml'].xpath('//xhtml:span[@epub:type="pagebreak"]', namespaces=ns)]
        self.assertEqual(ids, ['page_12', 'page_13'])
        self.assertEqual(len(trees['ch1.xhtml'].xpath('//xhtml:a[@id="page14"]', namespaces=ns)), 1)

    def test_remove_untagged_markers_from_older_versions(self):
        """Markers injected before they were tagged are still recognised and removed."""
        body = ''.join(f'<p>{"Word " * 60}</p>' for _ in range(10))
        container, trees = make_mock_container({'ch1.xhtml': body, 'ch2.xhtml': body})
        breaks = Paginator(container, PaginationConfig(chars_per_page=300)).paginate()
        injector = MarkerInjector(container)
        injector.inject_markers(breaks)
        for tree in trees.values():
            for span in tree.iter(f'{{{XHTML_NS}}}span'):
                del span.attrib[PLUGIN_MARKER_ATTR]

        self.assertEqual(injector.remove_existing_markers(), len(breaks))

    def test_remove_keeps_legacy_shaped_retail_markers(self):
        """Untagged markers not numbered 1..N from the start of the book are retail markers."""
        body = ''.join(
            f'<p>Text<span id="page_{n}" role="doc-pagebreak" epub:type="pagebreak" aria-label="{n}"/></p>'
            for n in range(1, 6))
        container, trees = make_mock_container({'ch1.xhtml': body})
        self.assertEqual(MarkerInjector(container).remove_existing_markers(), 0)
        self.assertEqual(len(list(trees['ch1.xhtml'].iter(f'{{{XHTML_NS}}}span'))), 5)

    def test_inject_avoids_existing_ids(self):
        """A synthetic marker gets a new id when the book already uses its id."""
        body = '<p>Old<a id="page_1"/></p>' + ''.join(f'<p>{"Word " * 60}</p>' for _ in range(3))
        container, trees = make_mock_container({'ch1.xhtml': body})
        breaks = Paginator(container, PaginationConfig(chars_per_page=300)).paginate()
        MarkerInjector(container).inject_markers(breaks)

        self.assertEqual(breaks[0].anchor_id, 'page_1_2')
        ids = [e.get('id') for e in trees['ch1.xhtml'].iter() if e.get('id')]
        self.assertEqual(len(ids), len(set(ids)))


# ===========================================================================
# NavBuilder Tests
# ===========================================================================

class TestNavBuilder(unittest.TestCase):
    """Tests for core.nav_builder.NavBuilder."""

    def _make_container_with_nav(self):
        """Create a container that has an existing nav.xhtml."""
        nav_html = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_OPS_NS}">
<head><title>Navigation</title></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>Table of Contents</h1>
    <ol><li><a href="ch1.xhtml">Chapter 1</a></li></ol>
  </nav>
</body>
</html>"""
        nav_tree = etree.ElementTree(etree.fromstring(nav_html.encode('utf-8')))

        # Build mock OPF
        opf_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="ch1"/>
  </spine>
</package>"""
        opf_tree = etree.ElementTree(etree.fromstring(opf_xml.encode('utf-8')))

        container = MagicMock()
        container.opf_name = 'content.opf'
        container.opf = opf_tree.getroot()

        OPF_NS = "http://www.idpf.org/2007/opf"

        def opf_xpath(expr):
            ns = {'opf': OPF_NS, 'dc': 'http://purl.org/dc/elements/1.1/'}
            return opf_tree.xpath(expr, namespaces=ns)

        container.opf_xpath = opf_xpath

        def parsed(name):
            if name == 'nav.xhtml':
                return nav_tree
            return None

        container.parsed = parsed
        container.dirty = MagicMock()
        container.name_to_href = lambda target, base=None: target
        container.href_to_name = lambda href, base=None: href

        return container, nav_tree

    def test_build_page_list_creates_nav_element(self):
        """build_page_list should create a <nav epub:type='page-list'> element."""
        container, nav_tree = self._make_container_with_nav()

        # Create fake page breaks
        dummy_elem = etree.Element('p')
        breaks = [
            PageBreak('ch1.xhtml', 'page_1', '1', dummy_elem, 'after'),
            PageBreak('ch1.xhtml', 'page_2', '2', dummy_elem, 'after'),
            PageBreak('ch1.xhtml', 'page_3', '3', dummy_elem, 'after'),
        ]

        builder = NavBuilder(container)
        builder.build_page_list(breaks, overwrite=True)

        ns = {'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS}
        page_lists = nav_tree.xpath('//xhtml:nav[@epub:type="page-list"]', namespaces=ns)
        self.assertEqual(len(page_lists), 1)

    def test_page_list_has_correct_entries(self):
        """The page-list should contain an <a> entry for each PageBreak."""
        container, nav_tree = self._make_container_with_nav()

        dummy_elem = etree.Element('p')
        breaks = [
            PageBreak('ch1.xhtml', 'page_1', '1', dummy_elem, 'after'),
            PageBreak('ch1.xhtml', 'page_2', '2', dummy_elem, 'after'),
        ]

        builder = NavBuilder(container)
        builder.build_page_list(breaks, overwrite=True)

        ns = {'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS}
        links = nav_tree.xpath(
            '//xhtml:nav[@epub:type="page-list"]//xhtml:a',
            namespaces=ns,
        )
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].text, '1')
        self.assertIn('#page_1', links[0].get('href'))
        self.assertEqual(links[1].text, '2')
        self.assertIn('#page_2', links[1].get('href'))

    def test_page_list_is_hidden(self):
        """The page-list nav should have hidden='hidden' attribute."""
        container, nav_tree = self._make_container_with_nav()

        dummy_elem = etree.Element('p')
        breaks = [PageBreak('ch1.xhtml', 'page_1', '1', dummy_elem, 'after')]

        builder = NavBuilder(container)
        builder.build_page_list(breaks, overwrite=True)

        ns = {'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS}
        page_list = nav_tree.xpath('//xhtml:nav[@epub:type="page-list"]', namespaces=ns)
        self.assertEqual(page_list[0].get('hidden'), 'hidden')

    def test_overwrite_false_skips_existing(self):
        """When overwrite=False and page-list exists, it should not be replaced."""
        container, nav_tree = self._make_container_with_nav()

        dummy_elem = etree.Element('p')
        breaks = [PageBreak('ch1.xhtml', 'page_1', '1', dummy_elem, 'after')]

        builder = NavBuilder(container)
        # First call creates the page-list
        builder.build_page_list(breaks, overwrite=True)

        # Second call with overwrite=False should skip
        breaks2 = [
            PageBreak('ch1.xhtml', 'page_1', '1', dummy_elem, 'after'),
            PageBreak('ch1.xhtml', 'page_2', '2', dummy_elem, 'after'),
            PageBreak('ch1.xhtml', 'page_3', '3', dummy_elem, 'after'),
        ]
        builder.build_page_list(breaks2, overwrite=False)

        ns = {'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS}
        links = nav_tree.xpath(
            '//xhtml:nav[@epub:type="page-list"]//xhtml:a',
            namespaces=ns,
        )
        # Should still have only 1 entry from the first call
        self.assertEqual(len(links), 1)

    def _page_break_source(self, container):
        return [m.text for m in container.opf_xpath('//*[local-name()="meta"][@property="pageBreakSource"]')]

    def test_synthetic_page_list_sets_page_break_source_none(self):
        container, _ = self._make_container_with_nav()
        breaks = [PageBreak('ch1.xhtml', 'page_1', '1', etree.Element('p'), 'after')]
        NavBuilder(container).build_page_list(breaks, overwrite=True)
        self.assertEqual(self._page_break_source(container), ['none'])

    def test_page_list_from_book_markers_drops_page_break_source_none(self):
        container, _ = self._make_container_with_nav()
        breaks = [PageBreak('ch1.xhtml', 'page_1', '1', etree.Element('p'), 'after')]
        builder = NavBuilder(container)
        builder.build_page_list(breaks, overwrite=True)
        builder.build_page_list(breaks, overwrite=True, synthetic=False)
        self.assertEqual(self._page_break_source(container), [])

    def test_empty_anchor_id_targets_document(self):
        container, nav_tree = self._make_container_with_nav()
        breaks = [PageBreak('ch1.xhtml', '', '1', etree.Element('p'), 'after')]
        NavBuilder(container).build_page_list(breaks, overwrite=True)
        ns = {'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS}
        link = nav_tree.xpath('//xhtml:nav[@epub:type="page-list"]//xhtml:a', namespaces=ns)[0]
        self.assertEqual(link.get('href'), 'ch1.xhtml')


# ===========================================================================
# Run tests
# ===========================================================================

if __name__ == '__main__':
    unittest.main(verbosity=2)

