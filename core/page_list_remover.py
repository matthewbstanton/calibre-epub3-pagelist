"""
Removes what the plugin added to a book: its synthetic page break markers,
the nav page-list, the NCX pageList, page-map.xml and the accessibility
metadata.

A book is only touched if it carries the plugin's footprint: markers the
plugin injected, or the ``pageBreakSource: none`` metadata it writes. That
is meant to keep a retail book's own page-list and print page markers intact.
That is best-effort, not a guarantee: untagged legacy markers are recognised
heuristically.
"""
from dataclasses import dataclass

from .marker_injector import MarkerInjector, find_plugin_markers
from .nav_builder import NavBuilder, EPUB_OPS_NS, XHTML_NS, NCX_NS, OPF_NS

ACCESSIBILITY_FEATURES = ("pageBreakMarkers", "pageNavigation")


@dataclass
class RemovalResult:
    """What was removed from one book."""
    markers: int = 0
    nav: bool = False
    ncx: bool = False
    page_maps: int = 0
    metadata: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.markers or self.nav or self.ncx or self.page_maps or self.metadata)


class PageListRemover:
    """Strips the plugin's page-list from a container."""

    def __init__(self, container):
        """
        :param container: Calibre Polish Container.
        """
        self.container = container
        self._nav = NavBuilder(container)

    def has_plugin_footprint(self) -> bool:
        """
        Whether the plugin added anything to this book: markers it injected
        or the ``pageBreakSource: none`` metadata.
        """
        if find_plugin_markers(self.container):
            return True
        return bool(self._page_break_sources_none())

    def remove(self) -> RemovalResult:
        """
        Remove everything the plugin added. Does nothing, and returns an
        empty result, if the book has no plugin footprint.
        """
        result = RemovalResult()
        if not self.has_plugin_footprint():
            return result

        result.markers = MarkerInjector(self.container).remove_existing_markers()
        result.nav = self._remove_nav_page_list()
        result.ncx = self._remove_ncx_page_list()
        result.page_maps = self._remove_page_maps()
        result.metadata = self._remove_metadata()
        return result

    def _remove_nav_page_list(self) -> bool:
        nav_name = self._nav._find_nav_document()
        if not nav_name:
            return False
        nav_tree = self.container.parsed(nav_name)
        page_lists = nav_tree.xpath('//xhtml:nav[@epub:type="page-list"]',
                                    namespaces={'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS})
        for page_list in page_lists:
            page_list.getparent().remove(page_list)
        if page_lists:
            self.container.dirty(nav_name)
        return bool(page_lists)

    def _remove_ncx_page_list(self) -> bool:
        items = self.container.opf_xpath('//opf:item[@media-type="application/x-dtbncx+xml"]')
        if not items:
            return False
        ncx_name = self.container.href_to_name(items[0].get('href'), base=self.container.opf_name)
        if not self.container.has_name(ncx_name):
            return False
        ncx_tree = self.container.parsed(ncx_name)
        page_lists = ncx_tree.xpath('//ncx:pageList', namespaces={'ncx': NCX_NS})
        for page_list in page_lists:
            page_list.getparent().remove(page_list)
        if page_lists:
            self.container.dirty(ncx_name)
        return bool(page_lists)

    def _remove_page_maps(self) -> int:
        names = self._nav._find_page_maps()
        for name in names:
            self.container.remove_item(name)
        # Drop the references that pointed at the page-map
        opf = self.container.opf
        spine = opf.find(f'.//{{{OPF_NS}}}spine')
        if spine is not None and 'page-map' in spine.attrib:
            del spine.attrib['page-map']
            names = names or ['']
        if 'page-map' in opf.attrib:
            del opf.attrib['page-map']
            names = names or ['']
        if names:
            self.container.dirty(self.container.opf_name)
        return len([n for n in names if n])

    def _page_break_sources_none(self) -> list:
        return [meta for meta in self.container.opf_xpath(
                    '//*[local-name()="meta"][@property="pageBreakSource"]')
                if (meta.text or '').strip() == 'none']

    def _remove_metadata(self) -> int:
        metas = self._page_break_sources_none()
        for feature in ACCESSIBILITY_FEATURES:
            metas += self.container.opf_xpath(
                f'//*[local-name()="meta"][@property="schema:accessibilityFeature"][normalize-space(text())="{feature}"]')
        for meta in metas:
            meta.getparent().remove(meta)
        if metas:
            self.container.dirty(self.container.opf_name)
        return len(metas)
