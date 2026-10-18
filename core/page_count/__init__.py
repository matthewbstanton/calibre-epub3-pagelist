"""
Page count sources: where each book's target page count comes from.

Every source implements PageCountSource.get_page_count(). action.py creates the
selected source once per run with create_page_count_source() and asks it for
each book's page count, so the batch loop doesn't need to know which source
is in use.

Nothing here imports Calibre. Sources read book fields through a ``db`` with
Calibre's ``field_for(field, book_id)`` signature, and the Goodreads and Amazon
sources are given a ``fetch(url) -> FetchResult`` function that makes the HTTP request.
"""
from .base import PageCount, PageCountSource
from .fetch import FetchResult, describe_fetch
from .chars_per_page import CharsPerPageSource
from .custom_column import CustomColumnSource
from .goodreads import GoodreadsSource
from .amazon import AmazonSource
from .factory import (SOURCE_CHARS_PER_PAGE, SOURCE_CUSTOM_COLUMN, SOURCE_GOODREADS_ID,
                      SOURCE_AMAZON_ID, PAGE_COUNT_SOURCES, create_page_count_source)
