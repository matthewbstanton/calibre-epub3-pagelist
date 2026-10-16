"""
Unit tests for the page count sources.

Uses a fake Calibre db and a fake fetch function; no network access.
"""
import os
import sys
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.page_count import (
    CharsPerPageSource, CustomColumnSource, GoodreadsSource, AmazonSource, FetchResult,
    create_page_count_source, describe_fetch,
    SOURCE_CHARS_PER_PAGE, SOURCE_CUSTOM_COLUMN, SOURCE_GOODREADS_ID, SOURCE_AMAZON_ID,
)


class FakeDb:
    """
    Stands in for Calibre's db.new_api: field_for(field, book_id).
    """
    def __init__(self, books):
        self.books = books

    def field_for(self, field, book_id):
        return self.books[book_id].get(field)


class FakeFetch:
    """
    Records requested URLs and returns a fixed FetchResult.
    """
    def __init__(self, result):
        self.result = result
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return self.result


GOODREADS_PAGE = b'<html><p data-testid="pagesFormat">317 pages, Hardcover</p></html>'
AMAZON_PAGE = (b'<html><div id="rpi-attribute-book_details-ebook_pages">'
               b'<span>Print length</span><span>352 pages</span></div></html>')


class TestCharsPerPageSource(unittest.TestCase):

    def test_returns_no_target(self):
        page_count = CharsPerPageSource().get_page_count(FakeDb({1: {}}), 1)
        self.assertIsNone(page_count.pages)
        self.assertFalse(page_count.skipped)


class TestCustomColumnSource(unittest.TestCase):

    def test_reads_column_value(self):
        source = CustomColumnSource('pages')
        db = FakeDb({1: {'title': 'Book', '#pages': 250}})
        page_count = source.get_page_count(db, 1)
        self.assertEqual(page_count.pages, 250)
        self.assertEqual(source.summary(), ('Custom column values',
                                            "Values read from custom column '#pages':\n\nBook: 250"))

    def test_leading_hash_is_optional(self):
        self.assertEqual(CustomColumnSource('#pages').column, '#pages')
        self.assertEqual(CustomColumnSource(' pages ').column, '#pages')

    def test_empty_or_invalid_value_skips(self):
        source = CustomColumnSource('#pages')
        for value in (None, 0, -3, 'abc', True):
            page_count = source.get_page_count(FakeDb({1: {'title': 'Book', '#pages': value}}), 1)
            self.assertTrue(page_count.skipped, value)
            self.assertEqual(page_count.skip_reason, 'no page count in #pages')
        self.assertIsNone(source.summary())


class TestGoodreadsSource(unittest.TestCase):

    def test_fetches_and_parses_page_count(self):
        fetch = FakeFetch(FetchResult(status=200, body=GOODREADS_PAGE))
        db = FakeDb({1: {'title': 'Book', 'identifiers': {'goodreads': '1410104'}}})
        page_count = GoodreadsSource(fetch).get_page_count(db, 1)
        self.assertEqual(page_count.pages, 317)
        self.assertEqual(fetch.urls, ['https://www.goodreads.com/book/show/1410104'])

    def test_missing_id_skips_without_fetching(self):
        fetch = FakeFetch(FetchResult(body=GOODREADS_PAGE))
        for identifiers in (None, {}, {'isbn': '123'}):
            db = FakeDb({1: {'identifiers': identifiers}})
            page_count = GoodreadsSource(fetch).get_page_count(db, 1)
            self.assertEqual(page_count.skip_reason, 'no Goodreads ID in its identifiers')
        self.assertEqual(fetch.urls, [])

    def test_invalid_id_skips_without_fetching(self):
        fetch = FakeFetch(FetchResult(body=GOODREADS_PAGE))
        db = FakeDb({1: {'identifiers': {'goodreads': 'abc'}}})
        page_count = GoodreadsSource(fetch).get_page_count(db, 1)
        self.assertEqual(page_count.skip_reason, 'invalid Goodreads ID "abc"')
        self.assertEqual(fetch.urls, [])

    def test_fetch_error_skips_with_details(self):
        fetch = FakeFetch(FetchResult(user_agent='UA', status=503, error=OSError('down')))
        db = FakeDb({1: {'identifiers': {'goodreads': '5907'}}})
        page_count = GoodreadsSource(fetch).get_page_count(db, 1)
        self.assertEqual(page_count.skip_reason,
                         'could not fetch https://www.goodreads.com/book/show/5907 (down)')
        self.assertIn('Status: 503', page_count.details)
        self.assertIn('User agent: UA', page_count.details)

    def test_no_count_on_page_skips_with_details(self):
        fetch = FakeFetch(FetchResult(status=202, headers='Server: CloudFront', body=b'<html></html>'))
        db = FakeDb({1: {'identifiers': {'goodreads': '5907'}}})
        page_count = GoodreadsSource(fetch).get_page_count(db, 1)
        self.assertEqual(page_count.skip_reason,
                         'no page count found on https://www.goodreads.com/book/show/5907')
        self.assertIn('Status: 202', page_count.details)
        self.assertIn('    Server: CloudFront', page_count.details)
        self.assertIn('<html></html>', page_count.details)


class TestAmazonSource(unittest.TestCase):

    def test_fetches_and_parses_page_count(self):
        fetch = FakeFetch(FetchResult(status=200, body=AMAZON_PAGE))
        db = FakeDb({1: {'title': 'Book', 'identifiers': {'amazon': 'B00ABCDEFG'}}})
        page_count = AmazonSource(fetch).get_page_count(db, 1)
        self.assertEqual(page_count.pages, 352)
        self.assertEqual(fetch.urls, ['https://www.amazon.com/dp/B00ABCDEFG'])

    def test_missing_id_skips_without_fetching(self):
        fetch = FakeFetch(FetchResult(body=AMAZON_PAGE))
        for identifiers in (None, {}, {'isbn': '123'}, {'amazon_uk': 'B00ABCDEFG'}):
            db = FakeDb({1: {'identifiers': identifiers}})
            page_count = AmazonSource(fetch).get_page_count(db, 1)
            self.assertEqual(page_count.skip_reason, 'no Amazon ID in its identifiers')
        self.assertEqual(fetch.urls, [])

    def test_invalid_id_skips_without_fetching(self):
        fetch = FakeFetch(FetchResult(body=AMAZON_PAGE))
        db = FakeDb({1: {'identifiers': {'amazon': 'abc'}}})
        page_count = AmazonSource(fetch).get_page_count(db, 1)
        self.assertEqual(page_count.skip_reason, 'invalid Amazon ID "abc"')
        self.assertEqual(fetch.urls, [])

    def test_fetch_error_skips_with_details(self):
        fetch = FakeFetch(FetchResult(user_agent='UA', status=503, error=OSError('down')))
        db = FakeDb({1: {'identifiers': {'amazon': 'B00ABCDEFG'}}})
        page_count = AmazonSource(fetch).get_page_count(db, 1)
        self.assertEqual(page_count.skip_reason,
                         'could not fetch https://www.amazon.com/dp/B00ABCDEFG (down)')
        self.assertIn('Status: 503', page_count.details)
        self.assertIn('User agent: UA', page_count.details)

    def test_no_count_on_page_skips_with_details(self):
        fetch = FakeFetch(FetchResult(status=200, headers='Server: Server', body=b'<html></html>'))
        db = FakeDb({1: {'identifiers': {'amazon': 'B00ABCDEFG'}}})
        page_count = AmazonSource(fetch).get_page_count(db, 1)
        self.assertEqual(page_count.skip_reason,
                         'no page count found on https://www.amazon.com/dp/B00ABCDEFG')
        self.assertIn('Status: 200', page_count.details)
        self.assertIn('    Server: Server', page_count.details)
        self.assertIn('<html></html>', page_count.details)


class TestDescribeFetch(unittest.TestCase):

    def test_body_is_truncated(self):
        text = describe_fetch('http://x', FetchResult(body=b'a' * 5000))
        self.assertIn('Body (5000 characters, first 3000 shown):', text)
        self.assertIn('a' * 3000, text)
        self.assertNotIn('a' * 3001, text)


class TestCreatePageCountSource(unittest.TestCase):

    def test_creates_matching_source(self):
        prefs = {'custom_column_name': '#pages'}
        self.assertIsInstance(create_page_count_source(SOURCE_CHARS_PER_PAGE, prefs, None),
                              CharsPerPageSource)
        self.assertIsInstance(create_page_count_source(SOURCE_CUSTOM_COLUMN, prefs, None),
                              CustomColumnSource)
        self.assertIsInstance(create_page_count_source(SOURCE_GOODREADS_ID, prefs, None),
                              GoodreadsSource)
        self.assertIsInstance(create_page_count_source(SOURCE_AMAZON_ID, prefs, None),
                              AmazonSource)

    def test_unknown_source_falls_back_to_chars_per_page(self):
        self.assertIsInstance(create_page_count_source('other', {}, None), CharsPerPageSource)


if __name__ == '__main__':
    unittest.main()
