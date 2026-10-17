"""
Tests for the Adobe page-map.xml written by NavBuilder, in particular that
re-running with overwrite enabled replaces an existing page-map instead of
keeping the old one or adding a second.

The container below keeps real files and manifest entries, like Calibre's
Polish container, so that add_file() and remove_item() have visible effects.
"""
import os
import sys
import unittest
from lxml import etree

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.existing_markers import ExistingMarkerDetector, METHOD_PAGE_LIST
from core.nav_builder import NavBuilder
from core.paginator import PageBreak

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_OPS_NS = "http://www.idpf.org/2007/ops"
OPF_NS = "http://www.idpf.org/2007/opf"
PAGE_MAP_TYPE = 'application/oebps-page-map+xml'

NAV = (f'<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_OPS_NS}"><head><title>Nav</title></head>'
       f'<body><nav epub:type="toc"><ol/></nav></body></html>')


def page_map_xml(pages) -> str:
    entries = ''.join(f'<page name="{label}" href="{href}"/>' for label, href in pages)
    return f'<?xml version="1.0" encoding="utf-8"?><page-map xmlns="{OPF_NS}">{entries}</page-map>'


class FakeContainer:
    """
    Minimal stand-in for Calibre's Polish container. Names are relative to
    the OPF directory, which is the root here, so hrefs equal names. It has
    only the methods the real container has: no ``set_raw_data``.
    """

    def __init__(self, files: dict, manifest: str, spine_attrs: str = ''):
        self.opf_name = 'content.opf'
        self.raw = {name: data.encode('utf-8') for name, data in files.items()}
        self.trees = {}
        opf_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="{OPF_NS}" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test</dc:title></metadata>
  <manifest>{manifest}</manifest>
  <spine{spine_attrs}><itemref idref="ch1"/></spine>
</package>"""
        self.opf = etree.fromstring(opf_xml.encode('utf-8'))
        self.spine_names = [('ch1.xhtml', True)]
        self._next_id = 1

    def opf_xpath(self, expr):
        return self.opf.xpath(expr, namespaces={'opf': OPF_NS, 'dc': 'http://purl.org/dc/elements/1.1/'})

    def manifest_items_with_property(self, prop):
        return [i.get('href') for i in self.opf_xpath(f'//opf:item[contains(@properties, "{prop}")]')]

    def name_to_href(self, name, base=None):
        return name

    def href_to_name(self, href, base=None):
        return href

    def has_name(self, name):
        return name in self.raw or name in self.trees

    def parsed(self, name):
        if name not in self.trees:
            if name not in self.raw:
                return None
            self.trees[name] = etree.fromstring(self.raw[name])
        return self.trees[name]

    def dirty(self, name):
        pass

    def add_file(self, name, data, media_type=None):
        if self.has_name(name):
            raise ValueError(f'A file with the name {name} already exists')
        self.raw[name] = data
        item_id = f'id{self._next_id}'
        self._next_id += 1
        manifest = self.opf.find(f'{{{OPF_NS}}}manifest')
        etree.SubElement(manifest, f'{{{OPF_NS}}}item', id=item_id, href=name, **{'media-type': media_type})

    def remove_item(self, name):
        self.raw.pop(name, None)
        self.trees.pop(name, None)
        for item in self.opf_xpath(f'//opf:item[@href="{name}"]'):
            for ref in self.opf_xpath(f'//opf:itemref[@idref="{item.get("id")}"]'):
                ref.getparent().remove(ref)
            item.getparent().remove(item)

    def serialize(self, name):
        """Final bytes of *name*, as Calibre would write them on commit."""
        if name in self.trees:
            return etree.tostring(self.trees[name], encoding='utf-8')
        return self.raw[name]


def make_book(page_map_name=None, page_map_id='page-map', old_pages=(), spine_attr=True):
    body = ''.join(f'<p><span id="p{n}"/>Text {n}</p>' for n in range(1, 6))
    ch1 = f'<html xmlns="{XHTML_NS}"><head><title>Ch1</title></head><body>{body}</body></html>'
    files = {'ch1.xhtml': ch1, 'nav.xhtml': NAV}
    manifest = ('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
                '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>')
    spine_attrs = ''
    if page_map_name:
        files[page_map_name] = page_map_xml(old_pages)
        manifest += f'<item id="{page_map_id}" href="{page_map_name}" media-type="{PAGE_MAP_TYPE}"/>'
        if spine_attr:
            spine_attrs = f' page-map="{page_map_id}"'
    return FakeContainer(files, manifest, spine_attrs)


def breaks(labels):
    return [PageBreak('ch1.xhtml', f'p{label}', str(label), etree.Element('p'), 'after') for label in labels]


class TestPageMapOverwrite(unittest.TestCase):

    def assert_single_page_map(self, container, expected):
        """Exactly one page-map item, referenced by the spine, with *expected* pages."""
        items = container.opf_xpath(f'//opf:item[@media-type="{PAGE_MAP_TYPE}"]')
        self.assertEqual(len(items), 1, 'expected exactly one page-map manifest item')
        item = items[0]
        name = container.href_to_name(item.get('href'))
        self.assertTrue(container.has_name(name))

        spine = container.opf.find(f'{{{OPF_NS}}}spine')
        self.assertEqual(spine.get('page-map'), item.get('id'))

        root = etree.fromstring(container.serialize(name))
        pages = [(p.get('name'), p.get('href')) for p in root.iter(f'{{{OPF_NS}}}page')]
        self.assertEqual(pages, expected)
        return name

    def test_new_page_map_is_created(self):
        container = make_book()
        NavBuilder(container).build_page_list(breaks([1, 2]), overwrite=True)
        self.assert_single_page_map(container, [('1', 'ch1.xhtml#p1'), ('2', 'ch1.xhtml#p2')])

    def test_overwrite_replaces_plugin_page_map(self):
        """A page-map.xml from an earlier run is rewritten with the new pages."""
        container = make_book()
        NavBuilder(container).build_page_list(breaks([1, 2, 3, 4]), overwrite=True)
        NavBuilder(container).build_page_list(breaks([1, 2]), overwrite=True)
        self.assert_single_page_map(container, [('1', 'ch1.xhtml#p1'), ('2', 'ch1.xhtml#p2')])

    def test_overwrite_replaces_page_map_already_in_book(self):
        """An existing page-map.xml at the default path is rewritten, not kept."""
        container = make_book('page-map.xml', old_pages=[('i', 'ch1.xhtml#p1'), ('ii', 'ch1.xhtml#p2')])
        NavBuilder(container).build_page_list(breaks([1, 2, 3]), overwrite=True)
        self.assert_single_page_map(
            container, [('1', 'ch1.xhtml#p1'), ('2', 'ch1.xhtml#p2'), ('3', 'ch1.xhtml#p3')])

    def test_overwrite_replaces_retail_page_map_at_other_path(self):
        """A retail page-map under another name is replaced, not joined by a second one."""
        container = make_book('Misc/pagemap.xml', page_map_id='map',
                              old_pages=[('i', 'ch1.xhtml#p1'), ('ii', 'ch1.xhtml#p2')])
        NavBuilder(container).build_page_list(breaks([1, 2]), overwrite=True)
        self.assert_single_page_map(container, [('1', 'ch1.xhtml#p1'), ('2', 'ch1.xhtml#p2')])
        self.assertFalse(container.has_name('Misc/pagemap.xml'))

    def test_overwrite_replaces_page_map_parsed_earlier(self):
        """Rewriting works after the old page-map was parsed (as the marker detector does)."""
        container = make_book('page-map.xml', old_pages=[('9', 'ch1.xhtml#p1')])
        container.parsed('page-map.xml')
        NavBuilder(container).build_page_list(breaks([1]), overwrite=True)
        self.assert_single_page_map(container, [('1', 'ch1.xhtml#p1')])

    def test_overwrite_false_keeps_existing_page_map(self):
        container = make_book('Misc/pagemap.xml', page_map_id='map', old_pages=[('i', 'ch1.xhtml#p1')])
        NavBuilder(container).build_page_list(breaks([1, 2]), overwrite=False)
        name = self.assert_single_page_map(container, [('i', 'ch1.xhtml#p1')])
        self.assertEqual(name, 'Misc/pagemap.xml')

    def test_retail_page_map_markers_rerun(self):
        """Pages read from a retail page-map are written back to a single page-map, twice over."""
        container = make_book('Misc/pagemap.xml', page_map_id='map',
                              old_pages=[(str(n), f'ch1.xhtml#p{n}') for n in range(1, 6)])
        expected = [(str(n), f'ch1.xhtml#p{n}') for n in range(1, 6)]
        for _ in range(2):
            result = ExistingMarkerDetector(container).detect()
            self.assertEqual(result.method, METHOD_PAGE_LIST)
            NavBuilder(container).build_page_list(result.markers, overwrite=True, synthetic=False)
            self.assert_single_page_map(container, expected)



class TestExistingPageCount(unittest.TestCase):

    def test_no_page_list(self):
        self.assertIsNone(NavBuilder(make_book()).existing_page_count())

    def test_counts_page_map_only(self):
        container = make_book('Misc/pagemap.xml', page_map_id='map',
                              old_pages=[(str(n), f'ch1.xhtml#p{n}') for n in range(1, 4)])
        self.assertEqual(NavBuilder(container).existing_page_count(), 3)

    def test_counts_generated_page_list(self):
        container = make_book()
        NavBuilder(container).build_page_list(breaks([1, 2, 3, 4]), overwrite=True)
        self.assertEqual(NavBuilder(container).existing_page_count(), 4)

if __name__ == '__main__':
    unittest.main(verbosity=2)
