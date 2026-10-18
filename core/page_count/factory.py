"""
Maps the 'page_count_source' pref to a page count source.
"""
from typing import Callable

from .base import PageCountSource
from .fetch import FetchResult
from .chars_per_page import CharsPerPageSource
from .custom_column import CustomColumnSource
from .goodreads import GoodreadsSource
from .amazon import AmazonSource

# Values for the 'page_count_source' pref
SOURCE_CHARS_PER_PAGE = 'chars_per_page'
SOURCE_CUSTOM_COLUMN = 'custom_column'
SOURCE_GOODREADS_ID = 'goodreads_id'
SOURCE_AMAZON_ID = 'amazon_id'
SOURCE_MOBI_ASIN = 'mobi_asin'
PAGE_COUNT_SOURCES = (SOURCE_CHARS_PER_PAGE, SOURCE_CUSTOM_COLUMN, SOURCE_GOODREADS_ID, SOURCE_AMAZON_ID,
                      SOURCE_MOBI_ASIN)


def create_page_count_source(source: str, prefs, fetch: Callable[[str], FetchResult]) -> PageCountSource:
    """
    Return the source for a 'page_count_source' pref value.
    prefs supplies 'custom_column_name'; fetch is used by the Goodreads, Amazon and mobi-asin sources.
    """
    if source == SOURCE_CUSTOM_COLUMN:
        return CustomColumnSource(prefs['custom_column_name'])
    if source == SOURCE_GOODREADS_ID:
        return GoodreadsSource(fetch)
    if source == SOURCE_AMAZON_ID:
        return AmazonSource(fetch)
    if source == SOURCE_MOBI_ASIN:
        return AmazonSource(fetch, identifier='mobi-asin', label='mobi-asin')
    return CharsPerPageSource()
