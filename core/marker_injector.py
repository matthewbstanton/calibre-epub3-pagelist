"""
Marker injector for EPUB3 page break elements.

Inserts ``<span role="doc-pagebreak" epub:type="pagebreak">`` elements
into EPUB XHTML content documents at positions determined by the Paginator.

Every marker the plugin injects carries ``data-epub3-pagelist="synthetic"``,
so the plugin can tell its own markers apart from the print page markers
that retail EPUBs already contain, and leaves the latter alone. Untagged
markers from older plugin versions are removed only if they match the legacy
form and numbering exactly (see ``find_plugin_markers``).
"""
from collections import defaultdict
from lxml import etree

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_OPS_NS = "http://www.idpf.org/2007/ops"

# Attribute that tags the markers the plugin injects
PLUGIN_MARKER_ATTR = "data-epub3-pagelist"
PLUGIN_MARKER_VALUE = "synthetic"

# Exact attribute set of the markers injected by plugin versions that did
# not yet tag them with PLUGIN_MARKER_ATTR
_LEGACY_MARKER_ATTRS = frozenset({'id', 'role', f'{{{EPUB_OPS_NS}}}type', 'aria-label'})


def spine_document_names(container) -> list[str]:
    """
    Return the names of all spine documents in reading order.
    """
    spine = getattr(container, 'spine_names', None) or getattr(container, 'spine_items', [])
    return [item[0] if isinstance(item, tuple) else item for item in spine]


def find_plugin_markers(container) -> dict[str, list]:
    """
    Find the page break markers the plugin itself injected, by spine document.

    Markers tagged with ``data-epub3-pagelist`` always count. Markers from
    older plugin versions carry no tag, so a ``<span>`` counts as one of
    them only if all of these hold, which retail print page markers
    practically never do together:

    * it has exactly the attributes ``id``, ``role="doc-pagebreak"``,
      ``epub:type="pagebreak"`` and ``aria-label``, no ``title``, no
      text and no children;
    * its id is ``page_<aria-label>`` and the label is a number;
    * across the book these spans are numbered 1, 2, 3 … in reading order;
    * in every document that has them, the first one is a direct child
      of ``<body>`` (the plugin always starts a section with a marker
      before the first element).

    :return: Mapping of spine name to the list of marker elements.
    """
    tagged: dict[str, list] = defaultdict(list)
    legacy: list[tuple[str, etree._Element]] = []

    for name in spine_document_names(container):
        try:
            tree = container.parsed(name)
        except Exception:
            continue
        if tree is None:
            continue
        root = tree.getroot() if hasattr(tree, 'getroot') else tree
        for span in root.iter(f'{{{XHTML_NS}}}span'):
            if span.get(PLUGIN_MARKER_ATTR) == PLUGIN_MARKER_VALUE:
                tagged[name].append(span)
            elif _looks_like_legacy_marker(span):
                legacy.append((name, span))

    found = dict(tagged)
    if legacy and _is_legacy_marker_sequence(legacy):
        for name, span in legacy:
            found.setdefault(name, []).append(span)
    return found


def _looks_like_legacy_marker(span: etree._Element) -> bool:
    """
    Whether *span* has exactly the shape of an untagged plugin marker.
    """
    if set(span.attrib.keys()) != _LEGACY_MARKER_ATTRS:
        return False
    if span.get('role') != 'doc-pagebreak' or span.get(f'{{{EPUB_OPS_NS}}}type') != 'pagebreak':
        return False
    label = span.get('aria-label') or ''
    if not label.isdigit() or span.get('id') != f'page_{label}':
        return False
    return len(span) == 0 and not (span.text or '').strip()


def _is_legacy_marker_sequence(markers: list) -> bool:
    """
    Whether the legacy-shaped spans of a book are numbered 1..N in reading
    order and each document's first one sits directly in ``<body>``.
    """
    labels = [int(span.get('aria-label')) for _, span in markers]
    if labels != list(range(1, len(labels) + 1)):
        return False
    seen_docs = set()
    for name, span in markers:
        if name in seen_docs:
            continue
        seen_docs.add(name)
        parent = span.getparent()
        if parent is None or parent.tag != f'{{{XHTML_NS}}}body':
            return False
    return True


class MarkerInjector:
    """Injects page break marker ``<span>`` elements into EPUB content documents."""

    def __init__(self, container):
        """
        :param container: Calibre Polish Container.
        """
        self.container = container

    def inject_markers(self, page_breaks: list) -> int:
        """
        Inject page break markers for all PageBreak objects.

        Markers are inserted in reverse document order within each spine
        document so that earlier element indices remain valid.

        :param page_breaks: List of PageBreak objects from the Paginator.
        :return: Count of successfully injected markers.
        """
        count = 0

        # Group page breaks by spine document
        grouped: dict[str, list] = defaultdict(list)
        for pb in page_breaks:
            grouped[pb.spine_name].append(pb)

        for spine_name, pbs in grouped.items():
            # Parse the document (cached by the container)
            tree = self.container.parsed(spine_name)
            used_ids = self._document_ids(tree)

            # Process in reverse order to preserve element positions
            for pb in reversed(pbs):
                ref_element = pb.insert_element
                parent = ref_element.getparent()

                if parent is None:
                    continue

                # Retail books may already use ids such as "page_12"
                pb.anchor_id = self._unique_id(pb.anchor_id, used_ids)
                span = self._create_pagebreak_element(pb)
                insert_pos = getattr(pb, 'insert_position', 'after')
                if insert_pos == 'before':
                    self._insert_before_element(parent, ref_element, span)
                else:
                    self._insert_after_element(parent, ref_element, span)
                count += 1

            self.container.dirty(spine_name)

        return count

    @staticmethod
    def _document_ids(tree) -> set:
        """
        Return all ``id`` values in a parsed document.
        """
        if tree is None:
            return set()
        root = tree.getroot() if hasattr(tree, 'getroot') else tree
        return {elem.get('id') for elem in root.iter() if isinstance(elem.tag, str) and elem.get('id')}

    @staticmethod
    def _unique_id(anchor_id: str, used_ids: set) -> str:
        """
        Return *anchor_id*, or *anchor_id* with a numeric suffix if the
        document already uses it, and record the result in *used_ids*.
        """
        candidate, n = anchor_id, 2
        while candidate in used_ids:
            candidate = f"{anchor_id}_{n}"
            n += 1
        used_ids.add(candidate)
        return candidate

    def _create_pagebreak_element(self, page_break) -> etree._Element:
        """
        Create a properly namespaced XHTML ``<span>`` element for a page break.

        Produces::

            <span id="page_42"
                  role="doc-pagebreak"
                  epub:type="pagebreak"
                  aria-label="42"
                  data-epub3-pagelist="synthetic"/>
        """
        span = etree.Element(
            f"{{{XHTML_NS}}}span",
            nsmap={'epub': EPUB_OPS_NS},
        )
        span.set("id", page_break.anchor_id)
        span.set("role", "doc-pagebreak")
        span.set(f"{{{EPUB_OPS_NS}}}type", "pagebreak")
        span.set("aria-label", page_break.page_label)
        span.set(PLUGIN_MARKER_ATTR, PLUGIN_MARKER_VALUE)
        return span

    def _insert_after_element(
        self,
        parent: etree._Element,
        ref_element: etree._Element,
        new_element: etree._Element,
    ) -> None:
        """
        Insert *new_element* as the next sibling of *ref_element*
        under *parent*, preserving any tail text on *ref_element*.
        """
        # Transfer tail text so it stays in the correct position
        if ref_element.tail:
            new_element.tail = ref_element.tail
            ref_element.tail = None
        ref_element.addnext(new_element)

    def _insert_before_element(
        self,
        parent: etree._Element,
        ref_element: etree._Element,
        new_element: etree._Element,
    ) -> None:
        """
        Insert *new_element* immediately before *ref_element* under *parent*.
        """
        ref_element.addprevious(new_element)

    def remove_existing_markers(self, spine_name: str | None = None) -> int:
        """
        Remove the page break markers the plugin injected on an earlier run.

        Only the plugin's own markers are removed (see
        ``find_plugin_markers()``). Print page markers that came with the
        book, including ``epub:type="pagebreak"`` spans, are left alone.

        :param spine_name: If provided, only process this single document.
            Otherwise process all spine documents.
        :return: Number of markers removed.
        """
        markers = find_plugin_markers(self.container)
        if spine_name:
            markers = {spine_name: markers.get(spine_name, [])}

        removed = 0

        for name, spans in markers.items():
            modified = False

            for span in spans:
                parent = span.getparent()
                if parent is None:
                    continue
                # Preserve tail text by transferring it
                if span.tail:
                    prev = span.getprevious()
                    if prev is not None:
                        prev.tail = (prev.tail or '') + span.tail
                    else:
                        parent.text = (parent.text or '') + span.tail
                parent.remove(span)
                modified = True
                removed += 1

            if modified:
                self.container.dirty(name)

        return removed
