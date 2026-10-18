"""
Amazon page count source.
"""
from typing import Callable

from ..base import PageCount, PageCountSource
from ..fetch import FetchResult, describe_fetch
from .parser import product_url, parse_page_count


class AmazonSource(PageCountSource):
    """
    Fetches the page count from the Amazon product page for the ASIN stored
    in one of the book's identifiers: ``amazon`` by default, or e.g.
    ``mobi-asin`` (the ASIN stored in MOBI/AZW files).
    """
    def __init__(self, fetch: Callable[[str], FetchResult],
                 identifier: str = 'amazon', label: str = 'Amazon'):
        self.fetch = fetch
        self.identifier = identifier
        self.label = label

    def get_page_count(self, db, book_id) -> PageCount:
        identifiers = db.field_for('identifiers', book_id) or {}
        asin = identifiers.get(self.identifier)
        if not asin:
            return PageCount(skip_reason=f'no {self.label} ID in its identifiers')
        url = product_url(asin)
        if not url:
            return PageCount(skip_reason=f'invalid {self.label} ID "{asin}"')

        result = self.fetch(url)
        if result.error is not None:
            return PageCount(skip_reason=f'could not fetch {url} ({result.error})',
                             details=describe_fetch(url, result))
        pages = parse_page_count(result.body)
        if not pages:
            return PageCount(skip_reason=f'no page count found on {url}',
                             details=describe_fetch(url, result))
        return PageCount(pages=pages)
