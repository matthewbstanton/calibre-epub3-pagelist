"""
Deciding which pages a book gets, without writing them.

``plan_pages()`` runs the same steps for every book that action.py processes:
keep an existing page-list, use the book's own print page markers, or ask the
page count source and paginate. It returns a ``PagePlan``. "Generate Page List"
then injects the markers and builds the page-list from the plan; "Save page
count to column" only reads ``PagePlan.page_count`` and never commits the
container, so the book is left unchanged.
"""
from dataclasses import dataclass, field
from typing import Optional

from .existing_markers import ExistingMarkerDetector
from .marker_injector import MarkerInjector
from .nav_builder import NavBuilder
from .page_count.base import PageCount
from .paginator import Paginator, PaginationConfig

# PagePlan outcomes
PLAN_EXISTING = 'existing'          # already has a page-list and overwrite is off
PLAN_MARKERS = 'markers'            # pages are the book's own print page markers
PLAN_GENERATED = 'generated'        # pages were computed by the paginator
PLAN_NO_MARKERS = 'no_markers'      # skipped: markers are required and there are none
PLAN_NO_PAGE_COUNT = 'no_page_count'  # skipped: the page count source had no count
PLAN_EMPTY = 'empty'                # the paginator produced no pages


@dataclass
class PagePlan:
    """
    What to do with one book.

    outcome: one of the PLAN_* constants.
    pages: the PageBreak/PageMarker list for PLAN_MARKERS and PLAN_GENERATED.
    existing_count: entries in the existing page-list, for PLAN_EXISTING (may be None).
    target_pages: the source's target count, if it gave one.
    source_result: the page count source's answer, if it was asked.
    source_label: the page count source's label, if it was asked.
    """
    outcome: str
    pages: list = field(default_factory=list)
    existing_count: Optional[int] = None
    target_pages: Optional[int] = None
    source_result: Optional[PageCount] = None
    source_label: Optional[str] = None

    @property
    def origin(self) -> Optional[str]:
        """
        Where the page count came from, in words for the user.
        """
        if self.outcome == PLAN_EXISTING:
            return 'existing page list'
        if self.outcome == PLAN_MARKERS:
            return "the book's page markers"
        return self.source_label

    @property
    def from_markers(self) -> bool:
        return self.outcome == PLAN_MARKERS

    @property
    def page_count(self) -> Optional[int]:
        """
        The book's final page count, or None if it has none.
        """
        if self.outcome == PLAN_EXISTING:
            return self.existing_count or None
        if self.outcome in (PLAN_MARKERS, PLAN_GENERATED):
            return len(self.pages) or None
        return None


def plan_pages(container, page_count_source, db, book_id, config: PaginationConfig,
               overwrite: bool, use_markers: bool = True, markers_only: bool = False) -> PagePlan:
    """
    Work out the pages for one EPUB 3 book.

    With ``overwrite`` set, the plugin's own markers are removed from the
    container first, so they are neither detected nor counted. The container
    is changed in memory only; the caller decides whether to commit it.

    :param container: Calibre Polish Container.
    :param page_count_source: a PageCountSource, asked only when needed.
    :param db: Calibre's new_api, passed to the page count source.
    :param use_markers: use the book's own print page markers if it has them.
    :param markers_only: skip books without print page markers.
    """
    nav_builder = NavBuilder(container)
    if not overwrite and nav_builder.has_existing_page_list():
        return PagePlan(PLAN_EXISTING, existing_count=nav_builder.existing_page_count())

    # Only plugin markers are targeted; the book's own print markers are meant to be left alone (best-effort)
    if overwrite:
        MarkerInjector(container).remove_existing_markers()

    if use_markers:
        detection = ExistingMarkerDetector(container).detect()
        if detection.found:
            return PagePlan(PLAN_MARKERS, pages=detection.markers)
        if markers_only:
            return PagePlan(PLAN_NO_MARKERS)

    # Asked after the overwrite check so skipped books cost no web request
    result = page_count_source.get_page_count(db, book_id)
    label = page_count_source.label
    if result.skipped:
        return PagePlan(PLAN_NO_PAGE_COUNT, source_result=result, source_label=label)

    target_pages = result.pages
    paginator = Paginator(container, config)
    pages = paginator.fit_to_page_count(target_pages) if target_pages else paginator.paginate()
    if not pages:
        return PagePlan(PLAN_EMPTY, target_pages=target_pages, source_result=result, source_label=label)
    return PagePlan(PLAN_GENERATED, pages=pages, target_pages=target_pages, source_result=result,
                    source_label=label)
