"""
Synthetic pagination engine for EPUB3 documents.

Calculates page break positions by counting visible text characters
and optionally snapping to paragraph boundaries.
"""
from dataclasses import dataclass, field
from lxml import etree

# Translation table for fast whitespace removal
_WS_REMOVER = str.maketrans('', '', ' \t\n\r\x0b\x0c')

# XHTML namespace constant
XHTML_NS = "http://www.w3.org/1999/xhtml"

# Block-level elements that represent valid snap points
_BLOCK_TAGS = frozenset({
    'p', 'div', 'section', 'article', 'aside', 'blockquote',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'dd', 'dt', 'figcaption',
})


def get_localname(elem: etree._Element) -> str:
    """
    Safely get the local tag name without XML namespace.
    Returns an empty string for comments, processing instructions, or invalid tags.
    """
    tag = getattr(elem, 'tag', None)
    if not isinstance(tag, str):
        return ''
    if tag.startswith('{'):
        return tag.split('}', 1)[1]
    return tag


@dataclass
class PageBreak:
    """Represents a synthetic page break position within an EPUB document."""
    spine_name: str
    anchor_id: str
    page_label: str
    insert_element: etree._Element
    insert_position: str  # 'after' — insert as next sibling of the element


@dataclass
class PaginationConfig:
    """Configuration for the pagination engine."""
    chars_per_page: int = 1850  # Kindle-standard ~1850 characters per page
    snap_to_paragraph: bool = True
    snap_threshold: int = 200
    skip_elements: frozenset = field(
        default_factory=lambda: frozenset({'pre', 'code', 'table', 'svg', 'math', 'script', 'style'})
    )


class Paginator:
    """
    Calculates synthetic page break positions across EPUB spine documents
    using Kindle-standard character-count pagination:
    - Each section/spine document (e.g. Cover, TOC, Chapter) starts on a new page.
    - Long sections are partitioned into additional pages every chars_per_page characters.
    """

    def __init__(self, container, config: PaginationConfig | None = None):
        """
        :param container: Calibre Polish Container object.
        :param config: Optional PaginationConfig. Uses defaults if not provided.
        """
        self.container = container
        self.config = config or PaginationConfig()

    def paginate(self) -> list[PageBreak]:
        """
        Iterate through all linear spine documents and calculate
        synthetic page break positions matching the KFX Output algorithm.

        :return: Ordered list of PageBreak objects across the entire book.
        """
        page_breaks: list[PageBreak] = []
        current_page = 1

        # Determine nav document names to skip
        nav_names = set()
        try:
            items = self.container.opf_xpath('//opf:item[contains(@properties, "nav")]')
            for item in items:
                href = item.get('href')
                nav_names.add(self.container.href_to_name(href, base=self.container.opf_name))
        except Exception:
            pass

        spine = getattr(self.container, 'spine_names', None) or getattr(self.container, 'spine_items', [])

        for item in spine:
            if isinstance(item, tuple):
                name, linear = item[0], item[1]
            else:
                name, linear = item, True

            if not linear or name in nav_names:
                continue

            tree = self.container.parsed(name)
            doc_breaks, current_page = self._process_document(
                name, tree, current_page
            )
            page_breaks.extend(doc_breaks)

        return page_breaks

    def fit_to_page_count(self, target: int) -> list[PageBreak]:
        """
        Binary-search ``chars_per_page`` so that ``paginate()`` yields
        ``target`` pages, or the closest count reachable (every section
        starts a new page, so very low targets may not be attainable).
        """
        lo, hi = 1, 1_000_000
        best_pages: list[PageBreak] | None = None
        best_cpp = self.config.chars_per_page

        while lo <= hi:
            mid = (lo + hi) // 2
            self.config.chars_per_page = mid
            pages = self.paginate()
            if best_pages is None or abs(len(pages) - target) < abs(len(best_pages) - target):
                best_pages, best_cpp = pages, mid
            if len(pages) == target:
                break
            if len(pages) > target:
                lo = mid + 1
            else:
                hi = mid - 1

        self.config.chars_per_page = best_cpp
        return best_pages or []

    # ------------------------------------------------------------------
    # Document processing
    # ------------------------------------------------------------------

    def _process_document(
        self,
        spine_name: str,
        tree: etree._ElementTree,
        start_page: int,
    ) -> tuple[list[PageBreak], int]:
        """
        Process a single XHTML spine document to find page break positions.

        Algorithm:
        1. The section begins on a new page (start_page).
        2. Any additional content beyond chars_per_page generates subsequent page breaks.

        :param spine_name: Container-relative name of the document.
        :param tree: Parsed lxml ElementTree.
        :param start_page: Page number to start counting from for this section.
        :return: (list of PageBreaks found, next available page number).
        """
        root = tree.getroot() if hasattr(tree, 'getroot') else tree
        body = self._find_body(root)
        if body is None:
            return [], start_page

        # Find first element to place the section's start page break
        first_elem = None
        for child in body:
            if isinstance(getattr(child, 'tag', None), str):
                first_elem = child
                break

        if first_elem is None:
            return [], start_page

        breaks: list[PageBreak] = []
        current_page = start_page

        # Section starts on a new page
        breaks.append(PageBreak(
            spine_name=spine_name,
            anchor_id=f"page_{current_page}",
            page_label=str(current_page),
            insert_element=first_elem,
            insert_position='before',
        ))
        current_page += 1

        char_count = 0
        last_block_element: etree._Element | None = None
        chars_at_last_block = 0

        for text, elem, is_tail in self._walk_text_nodes(body, self.config.skip_elements):
            if not text:
                continue

            localname = get_localname(elem)
            if localname in _BLOCK_TAGS:
                last_block_element = elem
                chars_at_last_block = char_count

            # Fast character counting without list allocations
            count = len(text.translate(_WS_REMOVER))
            char_count += count

            if char_count >= self.config.chars_per_page:
                snap_elem = self._find_snap_point(
                    elem, is_tail, last_block_element,
                    char_count, chars_at_last_block,
                )

                breaks.append(PageBreak(
                    spine_name=spine_name,
                    anchor_id=f"page_{current_page}",
                    page_label=str(current_page),
                    insert_element=snap_elem,
                    insert_position='after',
                ))

                current_page += 1
                char_count = 0
                last_block_element = None
                chars_at_last_block = 0

        return breaks, current_page

    # ------------------------------------------------------------------
    # DOM helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_body(root: etree._Element) -> etree._Element | None:
        """Find the <body> element, handling XHTML namespaces."""
        for elem in root.iter():
            if get_localname(elem) == 'body':
                return elem
        return None

    def _walk_text_nodes(
        self,
        element: etree._Element,
        skip_tags: frozenset,
    ):
        """
        Depth-first generator yielding ``(text, element, is_tail)`` tuples.

        * ``text`` — the actual string content.
        * ``element`` — the lxml element that owns this text.
        * ``is_tail`` — True if the text comes from ``element.tail``
          (i.e. text *after* the element's closing tag).

        Elements whose local tag name appears in *skip_tags* are skipped
        entirely (but their tail text is still yielded).
        """
        localname = get_localname(element)

        if localname in skip_tags:
            if element.tail:
                yield (element.tail, element, True)
            return

        if element.text:
            yield (element.text, element, False)

        for child in element:
            yield from self._walk_text_nodes(child, skip_tags)

        if element.tail:
            yield (element.tail, element, True)

    # ------------------------------------------------------------------
    # Paragraph snapping
    # ------------------------------------------------------------------

    def _find_snap_point(
        self,
        current_elem: etree._Element,
        is_tail: bool,
        last_block: etree._Element | None,
        char_count: int,
        chars_at_last_block: int,
    ) -> etree._Element:
        """
        Find the best element to place a page break marker after.

        When ``snap_to_paragraph`` is enabled and there is a recent
        block-level element within ``snap_threshold`` characters, the
        page break is placed after that block element instead of at
        the exact overflow position. This yields cleaner page boundaries.

        :returns: The lxml Element after which to insert the page break.
        """
        if not self.config.snap_to_paragraph or last_block is None:
            return self._nearest_block_ancestor(current_elem)

        overshoot = char_count - chars_at_last_block
        if overshoot <= self.config.snap_threshold:
            return last_block

        return self._nearest_block_ancestor(current_elem)

    @staticmethod
    def _nearest_block_ancestor(elem: etree._Element) -> etree._Element:
        """
        Walk up the tree from *elem* and return the first ancestor that
        is a block-level element. Falls back to *elem* itself if no
        block ancestor is found before <body>.
        """
        current = elem
        while current is not None:
            localname = get_localname(current)
            if localname in _BLOCK_TAGS:
                return current
            if localname == 'body':
                break
            current = current.getparent()
        return elem
