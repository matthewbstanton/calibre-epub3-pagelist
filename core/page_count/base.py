"""
The page count source interface and its result type.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class PageCount:
    """
    A source's answer for one book.

    pages: target page count, or None to split by characters per page.
    skip_reason: set when the book can't be paginated; the book is skipped.
    details: optional longer text for the "Show details" section.
    """
    pages: Optional[int] = None
    skip_reason: Optional[str] = None
    details: Optional[str] = None

    @property
    def skipped(self) -> bool:
        return self.skip_reason is not None


class PageCountSource:
    """
    Base class for page count sources.

    label: short name shown to the user as where a page count came from.
    """
    label = 'page count source'

    def get_page_count(self, db, book_id) -> PageCount:
        raise NotImplementedError

    def summary(self) -> Optional[tuple]:
        """
        Optional (title, message) to show after the run, or None.
        """
        return None
