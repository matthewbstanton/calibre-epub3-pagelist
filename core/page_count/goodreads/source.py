"""
Goodreads page count source.
"""
from typing import Callable

from ..base import PageCount, PageCountSource
from ..fetch import FetchResult, describe_fetch
from .parser import book_url, parse_page_count


class GoodreadsSource(PageCountSource):
    """
    Fetches the page count from the Goodreads book page for the book's
    ``goodreads`` identifier.
    """
    label = 'Goodreads ID'

    def __init__(self, fetch: Callable[[str], FetchResult]):
        self.fetch = fetch

    def get_page_count(self, db, book_id) -> PageCount:
        identifiers = db.field_for('identifiers', book_id) or {}
        goodreads_id = identifiers.get('goodreads')
        if not goodreads_id:
            return PageCount(skip_reason='no Goodreads ID in its identifiers')
        url = book_url(goodreads_id)
        if not url:
            return PageCount(skip_reason=f'invalid Goodreads ID "{goodreads_id}"')

        result = self.fetch(url)
        if result.error is not None:
            return PageCount(skip_reason=f'could not fetch {url} ({result.error})',
                             details=describe_fetch(url, result))
        pages = parse_page_count(result.body)
        if not pages:
            return PageCount(skip_reason=f'no page count found on {url}',
                             details=describe_fetch(url, result))
        return PageCount(pages=pages)
