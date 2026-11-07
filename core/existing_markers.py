"""
Detection of the print page markers that retail EPUBs already contain.

Many retail EPUBs mark where each printed page starts but lack a complete
page-list (or have only one of the nav page-list, NCX pageList and
page-map.xml). ``ExistingMarkerDetector`` finds those markers so the
page-list can be built from the real print pages instead of synthetic ones.

Sources:

1. ``page-list``: an existing nav page-list, NCX pageList or page-map.xml
   whose targets resolve to elements in the spine documents.
2. ``semantic``: elements with ``epub:type="pagebreak"`` or
   ``role="doc-pagebreak"``. The label comes from ``aria-label``, ``title``
   or the text content.
3. ``id-pattern``: empty ``<a>``/``<span>`` elements whose id looks like a
   page id (``page12``, ``page_12``, ``p12``, ``pg12``, ``Page_xii``…).
   Used only if there are at least ``MIN_ID_PATTERN_MARKERS`` of them and
   their numbers mostly ascend.

Sources 2 and 3 are combined in reading order, because some publishers mark
only the front and back matter semantically and the body with bare page-id
anchors. The existing page-list is used unless those in-text markers cover
more pages: publishers' page-lists are often partial too.

Markers the plugin injected itself (see
``core.marker_injector.find_plugin_markers``) are never reported.
"""
import re
from dataclasses import dataclass, field, replace
from urllib.parse import unquote

from lxml import etree

from .marker_injector import XHTML_NS, EPUB_OPS_NS, find_plugin_markers, spine_document_names

NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
OPF_NS = "http://www.idpf.org/2007/opf"

# Detection methods reported in DetectionResult.method
METHOD_PAGE_LIST = 'page-list'
METHOD_SEMANTIC = 'semantic'
METHOD_ID_PATTERN = 'id-pattern'

# Fewer id-pattern matches than this are treated as coincidence
MIN_ID_PATTERN_MARKERS = 10
# Share of consecutive id-pattern numbers that must go up
MIN_ASCENDING_RATIO = 0.9
# Share of an existing page-list's targets that must resolve for it to be used
MIN_RESOLVED_RATIO = 0.9
# Longest run of out-of-order pages at the end of the book that is dropped
MAX_RELOCATED_PAGES = 10

# page12, page_12, page-12, pg12, p12, Page_xii, pagexii …
_PAGE_ID_RE = re.compile(r'^(?:page|pg|p)[-_]?(?P<num>\d+|[ivxlcdm]+)$', re.IGNORECASE)
_ROMAN_RE = re.compile(r'^m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$')
_ROMAN_VALUES = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}
_ID_UNSAFE_RE = re.compile(r'[^A-Za-z0-9_-]+')
# Page 12, page 12., p. xii, pg 7 …
_WORDY_LABEL_RE = re.compile(r'^(?:(?:page|pg|p)\.?\s*)?(?P<num>[0-9a-z]+)\.?$', re.IGNORECASE)


@dataclass
class PageMarker:
    """
    A print page marker found in the book.

    Has the same ``spine_name``/``anchor_id``/``page_label`` fields as
    ``PageBreak``, so ``NavBuilder`` accepts it in place of one. An empty
    ``anchor_id`` targets the start of the document.
    """
    spine_name: str
    anchor_id: str
    page_label: str


@dataclass
class DetectionResult:
    """
    markers: the markers found, in page-list order; empty if none.
    method: METHOD_PAGE_LIST, METHOD_SEMANTIC, METHOD_ID_PATTERN, or None.
    """
    markers: list = field(default_factory=list)
    method: str | None = None

    @property
    def found(self) -> bool:
        return bool(self.markers)


def roman_to_int(text: str) -> int | None:
    """
    Return the value of a lower- or upper-case roman numeral, or None if
    *text* is not a valid one.
    """
    text = text.lower()
    if not text or not _ROMAN_RE.match(text):
        return None
    total = 0
    for i, ch in enumerate(text):
        value = _ROMAN_VALUES[ch]
        if i + 1 < len(text) and _ROMAN_VALUES[text[i + 1]] > value:
            total -= value
        else:
            total += value
    return total


def parse_page_id(element_id: str) -> tuple[str, int, bool] | None:
    """
    Parse an id such as ``page_12`` or ``pagexii``.

    :return: (label, numeric value, is_roman), or None if the id does not
        look like a page id.
    """
    match = _PAGE_ID_RE.match(element_id or '')
    if not match:
        return None
    num = match.group('num')
    if num.isdigit():
        return str(int(num)), int(num), False
    value = roman_to_int(num)
    if value is None:
        return None
    return num.lower(), value, True


def _label_value(label: str) -> tuple[int, bool] | None:
    """
    Return (numeric value, is_roman) of a page label such as ``12`` or
    ``xii``, or None for labels like ``Cover Page``.
    """
    label = (label or '').strip()
    if label.isdigit():
        return int(label), False
    value = roman_to_int(label)
    return (value, True) if value is not None else None


def number_page_labels(markers: list) -> list:
    """
    Keep only markers whose label is an arabic or roman page number.

    Send to Kindle ignores the whole page-list if any label is not a
    number, so ``Page 12.`` becomes ``12`` and labels such as
    ``Cover Page`` or ``Contents`` are dropped.
    """
    numbered = []
    for marker in markers:
        label = _page_number(marker.page_label)
        if label:
            numbered.append(replace(marker, page_label=label))
    return numbered


def print_page_count(labels: list) -> int | None:
    """
    Return the page count of a page-list with these labels, or None if none
    of them is a page number.

    Print pages don't all have markers (blank pages, unmarked front matter),
    so the count is the number of the last page, as Kindle shows it, after
    dropping relocated front matter (see ``drop_relocated_pages``). If the
    page-list has more numbered entries than that, for example roman pages
    only or an omnibus that restarts at 1, the number of entries is used.
    """
    markers = number_page_labels([PageMarker('', '', label) for label in labels])
    if not markers:
        return None
    kept = drop_relocated_pages(markers) or markers
    last = _label_value(kept[-1].page_label)
    last_page = last[0] if last and not last[1] else 0
    return max(last_page, len(markers))


def _page_number(label: str) -> str | None:
    """
    Return the page number in a label such as ``Page 12.`` (``12``), or
    None if the label is not a page number.
    """
    label = (label or '').strip()
    match = _WORDY_LABEL_RE.match(label)
    if match:
        label = match.group('num')
    return label if _label_value(label) else None


def drop_relocated_pages(markers: list) -> list:
    """
    Drop the front matter pages that the ebook moved after the last page.

    Publishers often move front matter such as the praise, ad card or
    copyright page to the back of the spine, so the page-list ends
    ``… 446, 2, 1, 447, 4``. Kindle reads the last entry as the book's
    page count and would show "of 4".

    The trailing run of roman pages, and of arabic pages lower than half
    the highest earlier arabic page, is dropped if it has at most
    ``MAX_RELOCATED_PAGES`` entries. A longer run is a real section (an
    omnibus whose second book restarts at 1) and is kept. Pages before the
    run, and runs ending in another label such as ``Back Cover``, are
    never changed.
    """
    highest_before = []
    highest = 0
    for marker in markers:
        highest_before.append(highest)
        parsed = _label_value(marker.page_label)
        if parsed and not parsed[1]:
            highest = max(highest, parsed[0])

    start = len(markers)
    while start > 0:
        parsed = _label_value(markers[start - 1].page_label)
        before = highest_before[start - 1]
        # Relocated front matter has low page numbers; a high one is the book's own ending
        if not parsed or not before or (not parsed[1] and parsed[0] * 2 >= before):
            break
        start -= 1
    if len(markers) - start > MAX_RELOCATED_PAGES:
        return markers
    return markers[:start]


def _localname(elem) -> str:
    tag = getattr(elem, 'tag', None)
    if not isinstance(tag, str):
        return ''
    return tag.split('}', 1)[1] if tag.startswith('{') else tag


def _text_of(elem) -> str:
    return ' '.join(''.join(elem.itertext()).split())


class ExistingMarkerDetector:
    """
    Finds the print page markers already present in a book's spine documents.
    """

    def __init__(self, container):
        """
        :param container: Calibre Polish Container.
        """
        self.container = container
        self._trees = {}
        self.names = []
        self._plugin_marker_elems = []
        self.plugin_markers = set()
        self._used_ids = {}

    def detect(self) -> DetectionResult:
        """
        Scan the book and return the numbered pages of the existing page-list,
        or of the in-text markers if those have more, less any pages the ebook
        moved out of reading order (see ``number_page_labels`` and
        ``drop_relocated_pages``). On a tie the page-list is used.

        If the in-text markers are used, semantic markers without an id are
        given one (``page-<label>``) and their document is marked dirty.
        """
        nav_names = self._nav_names()
        self.names = [n for n in spine_document_names(self.container) if n not in nav_names]
        # Hold the elements so their proxies, and so their id()s, stay stable
        self._plugin_marker_elems = [el for els in find_plugin_markers(self.container).values() for el in els]
        self.plugin_markers = {id(el) for el in self._plugin_marker_elems}

        page_list = number_page_labels(self._from_existing_page_list(nav_names))
        in_text = self._from_in_text_markers()

        if page_list and len(page_list) >= len(in_text):
            return DetectionResult(drop_relocated_pages(page_list), METHOD_PAGE_LIST)
        if not in_text:
            return DetectionResult()

        markers = [PageMarker(name, self._anchor_id(name, elem, label), label)
                   for name, elem, label, _ in in_text]
        method = METHOD_SEMANTIC if any(semantic for *_, semantic in in_text) else METHOD_ID_PATTERN
        return DetectionResult(drop_relocated_pages(markers), method)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _root(self, name: str):
        if name not in self._trees:
            try:
                tree = self.container.parsed(name)
            except Exception:
                tree = None
            if tree is not None and hasattr(tree, 'getroot'):
                tree = tree.getroot()
            self._trees[name] = tree
        return self._trees[name]

    def _body_elements(self, name: str):
        """
        Yield the elements inside ``<body>`` of a spine document, in document order.
        """
        root = self._root(name)
        if root is None:
            return
        for body in root.iter(f'{{{XHTML_NS}}}body'):
            for elem in body.iter():
                if isinstance(elem.tag, str) and id(elem) not in self.plugin_markers:
                    yield elem
            return

    def _nav_names(self) -> set:
        names = set()
        try:
            names.update(self.container.manifest_items_with_property('nav'))
        except Exception:
            pass
        try:
            for item in self.container.opf_xpath('//opf:item[contains(@properties, "nav")]'):
                names.add(self.container.href_to_name(item.get('href'), base=self.container.opf_name))
        except Exception:
            pass
        return {n for n in names if isinstance(n, str)}

    def _manifest_names(self, media_type: str) -> list:
        try:
            items = self.container.opf_xpath(f'//opf:item[@media-type="{media_type}"]')
            return [self.container.href_to_name(item.get('href'), base=self.container.opf_name)
                    for item in items]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 1. Existing page-list
    # ------------------------------------------------------------------

    def _from_existing_page_list(self, nav_names: set) -> list:
        """
        Use the first existing page-list (nav, then NCX, then page-map.xml)
        whose targets resolve to elements in the spine documents.
        """
        for entries in (self._nav_entries(nav_names), self._ncx_entries(), self._page_map_entries()):
            if not entries:
                continue
            markers = [m for m in (self._resolve(label, href, base) for label, href, base in entries) if m]
            if markers and len(markers) >= MIN_RESOLVED_RATIO * len(entries):
                return markers
        return []

    def _nav_entries(self, nav_names: set) -> list:
        entries = []
        ns = {'epub': EPUB_OPS_NS, 'xhtml': XHTML_NS}
        for nav_name in sorted(nav_names):
            root = self._root(nav_name)
            if root is None:
                continue
            for a in root.xpath('//xhtml:nav[@epub:type="page-list"]//xhtml:a[@href]', namespaces=ns):
                entries.append((_text_of(a), a.get('href'), nav_name))
            if entries:
                break
        return entries

    def _ncx_entries(self) -> list:
        entries = []
        ns = {'ncx': NCX_NS}
        for ncx_name in self._manifest_names('application/x-dtbncx+xml'):
            root = self._root(ncx_name)
            if root is None:
                continue
            for target in root.xpath('//ncx:pageList/ncx:pageTarget', namespaces=ns):
                content = target.find(f'{{{NCX_NS}}}content')
                if content is None or not content.get('src'):
                    continue
                text = target.find(f'{{{NCX_NS}}}navLabel/{{{NCX_NS}}}text')
                label = _text_of(text) if text is not None else ''
                entries.append((label or target.get('value') or '', content.get('src'), ncx_name))
            if entries:
                break
        return entries

    def _page_map_entries(self) -> list:
        entries = []
        for pm_name in self._manifest_names('application/oebps-page-map+xml'):
            root = self._root(pm_name)
            if root is None:
                continue
            for page in root.iter(f'{{{OPF_NS}}}page', 'page'):
                if page.get('href'):
                    entries.append((page.get('name') or '', page.get('href'), pm_name))
            if entries:
                break
        return entries

    def _resolve(self, label: str, href: str, base: str) -> PageMarker | None:
        """
        Turn a page-list entry into a PageMarker, or None if its target is
        not an element of a spine document (or is one of the plugin's markers).
        """
        label = (label or '').strip()
        if not label:
            return None
        path, _, fragment = href.partition('#')
        try:
            name = self.container.href_to_name(path, base=base) if path else base
        except Exception:
            return None
        if name not in self.names:
            return None
        fragment = unquote(fragment)
        if fragment:
            root = self._root(name)
            if root is None:
                return None
            matches = [el for el in root.iter() if isinstance(el.tag, str) and el.get('id') == fragment]
            if not matches or id(matches[0]) in self.plugin_markers:
                return None
        return PageMarker(name, fragment, label)

    # ------------------------------------------------------------------
    # 2 and 3. Markers in the text
    # ------------------------------------------------------------------

    def _from_in_text_markers(self) -> list:
        """
        Find the semantic markers and the page-id anchors with a numbered
        label, in reading order. Page-id anchors are dropped as a whole if
        they fail the ``_valid_id_pattern`` checks, and one by one if their
        page already has a semantic marker.

        :return: List of (spine name, element, page label, is_semantic).
        """
        semantic, anchors = [], []
        position = 0
        for name in self.names:
            for elem in self._body_elements(name):
                position += 1
                if self._is_semantic_marker(elem):
                    label = _page_number(self._semantic_label(elem))
                    if label:
                        semantic.append((position, name, elem, label, True))
                    continue
                parsed = self._page_id_anchor(elem)
                if parsed:
                    anchors.append((position, name, elem, parsed))

        if not self._valid_id_pattern([parsed for *_, parsed in anchors]):
            anchors = []
        semantic_labels = {label for _, _, _, label, _ in semantic}
        found = semantic + [(position, name, elem, parsed[0], False)
                            for position, name, elem, parsed in anchors if parsed[0] not in semantic_labels]
        found.sort(key=lambda item: item[0])
        return [item[1:] for item in found]

    def _anchor_id(self, name: str, elem, label: str) -> str:
        """
        Return the id of a marker element, giving it one first if it has none.
        """
        anchor_id = elem.get('id')
        if not anchor_id:
            if name not in self._used_ids:
                self._used_ids[name] = {el.get('id') for el in self._root(name).iter()
                                        if isinstance(el.tag, str) and el.get('id')}
            anchor_id = self._new_id(label, self._used_ids[name])
            elem.set('id', anchor_id)
            self.container.dirty(name)
        return anchor_id

    @staticmethod
    def _is_semantic_marker(elem) -> bool:
        types = (elem.get(f'{{{EPUB_OPS_NS}}}type') or '').split()
        roles = (elem.get('role') or '').split()
        return 'pagebreak' in types or 'doc-pagebreak' in roles

    @staticmethod
    def _semantic_label(elem) -> str:
        for label in (elem.get('aria-label'), elem.get('title'), _text_of(elem)):
            if label and label.strip():
                return ' '.join(label.split())
        parsed = parse_page_id(elem.get('id'))
        return parsed[0] if parsed else ''

    @staticmethod
    def _new_id(label: str, used_ids: set) -> str:
        base = 'page-' + (_ID_UNSAFE_RE.sub('-', label).strip('-') or 'break')
        candidate, n = base, 2
        while candidate in used_ids:
            candidate = f'{base}-{n}'
            n += 1
        used_ids.add(candidate)
        return candidate

    @staticmethod
    def _page_id_anchor(elem) -> tuple[str, int, bool] | None:
        """
        Parse an empty ``<a>``/``<span>`` element with a page-like id.

        :return: (label, numeric value, is_roman), or None if the element is
            not a page-id anchor.
        """
        if _localname(elem) not in ('a', 'span') or len(elem):
            return None
        parsed = parse_page_id(elem.get('id'))
        if not parsed:
            return None
        label, value, is_roman = parsed
        text = _text_of(elem)
        # Visible page numbers are fine; anything else is not a page anchor
        if text and text.lower() != label:
            return None
        return text or label, value, is_roman

    @staticmethod
    def _valid_id_pattern(anchors: list) -> bool:
        """
        Accept page-id anchors, given as ``_page_id_anchor`` results in
        reading order, only if there are enough of them and their numbers
        mostly ascend (arabic and roman numbers are checked separately).
        """
        if len(anchors) < MIN_ID_PATTERN_MARKERS:
            return False

        pairs = ascending = 0
        for roman in (False, True):
            values = [value for _, value, is_roman in anchors if is_roman == roman]
            for prev, cur in zip(values, values[1:]):
                pairs += 1
                ascending += cur > prev
        return bool(pairs) and ascending >= MIN_ASCENDING_RATIO * pairs
