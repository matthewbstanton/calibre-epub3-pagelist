"""
Unit tests for core.existing_markers: finding the print page markers that
retail EPUBs already contain.

Uses a mock Polish container; no Calibre needed.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock
from lxml import etree

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.existing_markers import (
    ExistingMarkerDetector, parse_page_id, roman_to_int,
    METHOD_PAGE_LIST, METHOD_SEMANTIC, METHOD_ID_PATTERN, MIN_ID_PATTERN_MARKERS,
)
from core.marker_injector import MarkerInjector, PLUGIN_MARKER_ATTR
from core.nav_builder import NavBuilder
from core.paginator import Paginator, PaginationConfig

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_OPS_NS = "http://www.idpf.org/2007/ops"
OPF_NS = "http://www.idpf.org/2007/opf"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"


def make_xhtml_tree(body_html: str) -> etree._ElementTree:
    xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_OPS_NS}">
<head><title>Test</title></head>
<body>
{body_html}
</body>
</html>"""
    return etree.ElementTree(etree.fromstring(xhtml.encode('utf-8')))


def make_container(spine_docs: dict, extra_files: dict | None = None, manifest_extra: str = ''):
    """
    Mock container with spine documents (name -> body html), optional extra
    parsed files (name -> xml string) and extra OPF manifest items.
    """
    trees = {name: make_xhtml_tree(body) for name, body in spine_docs.items()}
    for name, xml in (extra_files or {}).items():
        trees[name] = etree.ElementTree(etree.fromstring(xml.encode('utf-8')))

    items = ''.join(f'<item id="i{n}" href="{name}" media-type="application/xhtml+xml"/>'
                    for n, name in enumerate(spine_docs))
    opf_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="{OPF_NS}" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test</dc:title></metadata>
  <manifest>{items}{manifest_extra}</manifest>
  <spine/>
</package>"""
    opf_tree = etree.ElementTree(etree.fromstring(opf_xml.encode('utf-8')))

    container = MagicMock()
    container.spine_names = [(name, True) for name in spine_docs]
    container.parsed = lambda name: trees.get(name)
    container.dirty = MagicMock()
    container.opf_name = 'content.opf'
    container.opf = opf_tree.getroot()
    container.opf_xpath = lambda expr: opf_tree.xpath(
        expr, namespaces={'opf': OPF_NS, 'dc': 'http://purl.org/dc/elements/1.1/'})
    container.manifest_items_with_property = lambda prop: []
    container.name_to_href = lambda target, base=None: target
    container.href_to_name = lambda href, base=None: href
    container.has_name = lambda name: name in trees
    return container, trees


def anchors(ids, tag='a'):
    return ''.join(f'<p>Text before.<{tag} id="{i}"/> Text after.</p>' for i in ids)


class TestParsePageId(unittest.TestCase):

    def test_arabic_forms(self):
        for page_id in ('page12', 'page_12', 'page-12', 'p12', 'pg12', 'Page_12', 'PAGE012'):
            self.assertEqual(parse_page_id(page_id), ('12', 12, False), page_id)

    def test_roman_forms(self):
        self.assertEqual(parse_page_id('Page_xii'), ('xii', 12, True))
        self.assertEqual(parse_page_id('pagexii'), ('xii', 12, True))
        self.assertEqual(parse_page_id('p_iv'), ('iv', 4, True))

    def test_non_page_ids(self):
        for other in ('para12', 'chapter1', 'page', 'p', 'pageiiii', 'pagexyz', 'note12', ''):
            self.assertIsNone(parse_page_id(other), other)

    def test_roman_to_int(self):
        self.assertEqual(roman_to_int('mcmxcix'), 1999)
        self.assertEqual(roman_to_int('XL'), 40)
        self.assertIsNone(roman_to_int('iiii'))
        self.assertIsNone(roman_to_int(''))


class TestSemanticMarkers(unittest.TestCase):

    def test_epub_type_markers_with_title(self):
        container, _ = make_container({
            'ch1.xhtml': '<p>One<span epub:type="pagebreak" id="page_1" title="1"/> two</p>'
                         '<p>Three<span epub:type="pagebreak" id="page_2" title="2"/></p>',
            'ch2.xhtml': '<p><span epub:type="pagebreak" id="page_3" title="3"/>Four</p>',
        })
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual(result.method, METHOD_SEMANTIC)
        self.assertEqual([(m.spine_name, m.anchor_id, m.page_label) for m in result.markers], [
            ('ch1.xhtml', 'page_1', '1'),
            ('ch1.xhtml', 'page_2', '2'),
            ('ch2.xhtml', 'page_3', '3'),
        ])

    def test_role_marker_with_aria_label(self):
        container, _ = make_container({
            'ch1.xhtml': '<p>One<span role="doc-pagebreak" id="pg7" aria-label="7"/></p>',
        })
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual([(m.anchor_id, m.page_label) for m in result.markers], [('pg7', '7')])

    def test_label_from_text_content(self):
        container, _ = make_container({
            'ch1.xhtml': '<div epub:type="pagebreak" id="pb5"> 5 </div><p>Text</p>',
        })
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual(result.markers[0].page_label, '5')

    def test_marker_without_id_gets_one(self):
        container, trees = make_container({
            'ch1.xhtml': '<p id="page-12">x</p><p>One<span epub:type="pagebreak" title="12"/></p>',
        })
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual(result.markers[0].anchor_id, 'page-12-2')
        span = trees['ch1.xhtml'].xpath('//x:span', namespaces={'x': XHTML_NS})[0]
        self.assertEqual(span.get('id'), 'page-12-2')
        container.dirty.assert_called_with('ch1.xhtml')

        # A second scan reuses the id it assigned
        again = ExistingMarkerDetector(container).detect()
        self.assertEqual(again.markers[0].anchor_id, 'page-12-2')

    def test_unlabelled_marker_is_ignored(self):
        container, _ = make_container({
            'ch1.xhtml': '<hr epub:type="pagebreak"/><p>Text</p>',
        })
        self.assertFalse(ExistingMarkerDetector(container).detect().found)

    def test_semantic_markers_win_over_id_pattern(self):
        ids = [f'page{n}' for n in range(1, 21)]
        container, _ = make_container({
            'ch1.xhtml': anchors(ids) + '<p><span epub:type="pagebreak" id="pb1" title="1"/></p>',
        })
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual(result.method, METHOD_SEMANTIC)
        self.assertEqual(len(result.markers), 1)


class TestIdPatternMarkers(unittest.TestCase):

    def test_page_ids_across_documents(self):
        container, _ = make_container({
            'ch1.xhtml': anchors([f'page_{n}' for n in range(1, 8)]),
            'ch2.xhtml': anchors([f'page_{n}' for n in range(8, 16)], tag='span'),
        })
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual(result.method, METHOD_ID_PATTERN)
        self.assertEqual([m.page_label for m in result.markers], [str(n) for n in range(1, 16)])
        self.assertEqual(result.markers[7].spine_name, 'ch2.xhtml')
        self.assertEqual(result.markers[7].anchor_id, 'page_8')

    def test_roman_front_matter_then_arabic(self):
        roman = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii']
        container, _ = make_container({
            'front.xhtml': anchors([f'Page_{r}' for r in roman]),
            'ch1.xhtml': anchors([f'p{n}' for n in range(1, 21)]),
        })
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual(result.method, METHOD_ID_PATTERN)
        labels = [m.page_label for m in result.markers]
        self.assertEqual(labels, roman + [str(n) for n in range(1, 21)])

    def test_visible_page_number_text_is_accepted(self):
        body = ''.join(f'<p>Text <span id="pg{n}">{n}</span> more.</p>' for n in range(1, 13))
        container, _ = make_container({'ch1.xhtml': body})
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual(len(result.markers), 12)

    def test_no_markers_found(self):
        container, _ = make_container({
            'ch1.xhtml': '<p id="intro">Plain text.</p><p>More text.</p>',
        })
        result = ExistingMarkerDetector(container).detect()
        self.assertFalse(result.found)
        self.assertIsNone(result.method)
        self.assertEqual(result.markers, [])

    def test_too_few_matches_rejected(self):
        ids = [f'page{n}' for n in range(1, MIN_ID_PATTERN_MARKERS)]
        container, _ = make_container({'ch1.xhtml': anchors(ids)})
        self.assertFalse(ExistingMarkerDetector(container).detect().found)

    def test_unordered_numbers_rejected(self):
        numbers = [7, 3, 19, 1, 12, 5, 30, 2, 14, 9, 4, 22]
        container, _ = make_container({'ch1.xhtml': anchors([f'p{n}' for n in numbers])})
        self.assertFalse(ExistingMarkerDetector(container).detect().found)

    def test_paragraph_ids_with_text_rejected(self):
        body = ''.join(f'<p><span id="p{n}">Paragraph {n} of the story.</span></p>' for n in range(1, 40))
        container, _ = make_container({'ch1.xhtml': body})
        self.assertFalse(ExistingMarkerDetector(container).detect().found)

    def test_only_anchors_and_spans_count(self):
        body = ''.join(f'<div id="page{n}"/>' for n in range(1, 30))
        container, _ = make_container({'ch1.xhtml': body})
        self.assertFalse(ExistingMarkerDetector(container).detect().found)


class TestExistingPageList(unittest.TestCase):

    def _ncx(self, targets):
        points = ''.join(
            f'<pageTarget id="pt{label}" type="normal" value="{label}">'
            f'<navLabel><text>{label}</text></navLabel><content src="{src}"/></pageTarget>'
            for label, src in targets)
        return (f'<ncx xmlns="{NCX_NS}" version="2005-1"><navMap/>'
                f'<pageList><navLabel><text>Pages</text></navLabel>{points}</pageList></ncx>')

    def test_ncx_page_list_is_used(self):
        container, _ = make_container(
            {'ch1.xhtml': '<p><a id="x1"/>One</p><p><a id="x2"/>Two</p>'},
            extra_files={'toc.ncx': self._ncx([('ix', 'ch1.xhtml#x1'), ('x', 'ch1.xhtml#x2')])},
            manifest_extra='<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        )
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual(result.method, METHOD_PAGE_LIST)
        self.assertEqual([(m.anchor_id, m.page_label) for m in result.markers], [('x1', 'ix'), ('x2', 'x')])

    def test_target_without_fragment(self):
        container, _ = make_container(
            {'ch1.xhtml': '<p>One</p>'},
            extra_files={'toc.ncx': self._ncx([('1', 'ch1.xhtml')])},
            manifest_extra='<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        )
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual([(m.spine_name, m.anchor_id) for m in result.markers], [('ch1.xhtml', '')])

    def test_unresolved_page_list_falls_through(self):
        container, _ = make_container(
            {'ch1.xhtml': '<p><span epub:type="pagebreak" id="pb4" title="4"/>One</p>'},
            extra_files={'toc.ncx': self._ncx([('1', 'ch1.xhtml#gone1'), ('2', 'ch1.xhtml#gone2')])},
            manifest_extra='<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        )
        result = ExistingMarkerDetector(container).detect()
        self.assertEqual(result.method, METHOD_SEMANTIC)
        self.assertEqual(result.markers[0].page_label, '4')


class TestPluginMarkersAreNotExistingMarkers(unittest.TestCase):

    def _synthetic_book(self):
        body = ''.join(f'<p>{"Word " * 60}</p>' for _ in range(10))
        container, trees = make_container({'ch1.xhtml': body, 'ch2.xhtml': body})
        pages = Paginator(container, PaginationConfig(chars_per_page=300)).paginate()
        MarkerInjector(container).inject_markers(pages)
        return container, trees, pages

    def test_tagged_plugin_markers_ignored(self):
        container, _, pages = self._synthetic_book()
        self.assertGreater(len(pages), MIN_ID_PATTERN_MARKERS)
        self.assertFalse(ExistingMarkerDetector(container).detect().found)

    def test_untagged_legacy_plugin_markers_ignored(self):
        container, trees, _ = self._synthetic_book()
        for tree in trees.values():
            for span in tree.iter(f'{{{XHTML_NS}}}span'):
                del span.attrib[PLUGIN_MARKER_ATTR]
        self.assertFalse(ExistingMarkerDetector(container).detect().found)

    def test_retail_markers_survive_synthetic_cleanup_and_rerun(self):
        """Re-running on a retail book removes nothing and rebuilds the same page-list."""
        body = ''.join(
            f'<p>Text<span epub:type="pagebreak" role="doc-pagebreak" id="page_{n}" aria-label="{n}"/></p>'
            for n in range(5, 15))
        nav = (f'<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_OPS_NS}"><head><title>Nav</title></head>'
               f'<body><nav epub:type="toc"><ol/></nav></body></html>')
        container, trees = make_container(
            {'ch1.xhtml': body}, extra_files={'nav.xhtml': nav},
            manifest_extra='<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        )

        def run():
            self.assertEqual(MarkerInjector(container).remove_existing_markers(), 0)
            result = ExistingMarkerDetector(container).detect()
            NavBuilder(container).build_page_list(result.markers, overwrite=True, synthetic=False)
            links = trees['nav.xhtml'].xpath(
                '//x:nav[@epub:type="page-list"]//x:a', namespaces={'x': XHTML_NS, 'epub': EPUB_OPS_NS})
            return result.method, [(a.get('href'), a.text) for a in links]

        first = run()
        self.assertEqual(first[0], METHOD_SEMANTIC)
        self.assertEqual(first[1][0], ('ch1.xhtml#page_5', '5'))
        second = run()
        self.assertEqual(second[0], METHOD_PAGE_LIST)
        self.assertEqual(first[1], second[1])
        spans = trees['ch1.xhtml'].xpath('//x:span', namespaces={'x': XHTML_NS})
        self.assertEqual(len(spans), 10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
