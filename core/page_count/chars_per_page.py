"""
Characters per page: no target count, the paginator splits by size.
"""
from .base import PageCount, PageCountSource


class CharsPerPageSource(PageCountSource):
    """
    No target count: the paginator splits by the characters-per-page setting.
    """
    label = 'characters per page'

    def get_page_count(self, db, book_id) -> PageCount:
        return PageCount()
