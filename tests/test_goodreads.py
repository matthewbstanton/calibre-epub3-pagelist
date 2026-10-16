"""
Unit tests for the Goodreads page count parser.

Uses small HTML fixtures; no network access.
"""
import os
import sys
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.page_count.goodreads.parser import parse_page_count, book_url, normalize_goodreads_id


JSON_LD_PAGE = """<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Book",
"name":"Test Book","bookFormat":"Paperback","numberOfPages":320,"inLanguage":"English"}</script>
</head><body>
<p data-testid="pagesFormat">999 pages, Paperback</p>
</body></html>"""

PAGES_FORMAT_PAGE = """<html><body>
<div class="FeaturedDetails"><p data-testid="pagesFormat">1,024 pages, Hardcover</p>
<p data-testid="publicationInfo">First published January 1, 2000</p></div>
</body></html>"""

LEGACY_PAGE = """<html><body>
<div id="details"><span itemprop="bookFormat">Paperback</span>,
<span itemprop="numberOfPages">288 pages</span></div>
</body></html>"""

NEXT_DATA_PAGE = """<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"apolloState":{"Book:kca://book/1":{"details":{"numPages":416,"format":"Kindle"}}}}}}
</script></body></html>"""


class TestParsePageCount(unittest.TestCase):
    """Tests for parse_page_count."""

    def test_json_ld_number_of_pages(self):
        self.assertEqual(parse_page_count(JSON_LD_PAGE), 320)

    def test_json_ld_string_value(self):
        html = '<script type="application/ld+json">{"@type":"Book","numberOfPages":"256"}</script>'
        self.assertEqual(parse_page_count(html), 256)

    def test_json_ld_in_graph(self):
        html = ('<script type="application/ld+json">{"@graph":[{"@type":"WebPage"},'
                '{"@type":"Book","numberOfPages":512}]}</script>')
        self.assertEqual(parse_page_count(html), 512)

    def test_invalid_json_ld_falls_through(self):
        html = ('<script type="application/ld+json">{not json</script>'
                '<p data-testid="pagesFormat">200 pages, ebook</p>')
        self.assertEqual(parse_page_count(html), 200)

    def test_pages_format_text_with_thousands_separator(self):
        self.assertEqual(parse_page_count(PAGES_FORMAT_PAGE), 1024)

    def test_pages_format_with_nested_tags(self):
        html = '<p data-testid="pagesFormat"><span>150</span> pages, Paperback</p>'
        self.assertEqual(parse_page_count(html), 150)

    def test_legacy_itemprop(self):
        self.assertEqual(parse_page_count(LEGACY_PAGE), 288)

    def test_embedded_num_pages(self):
        self.assertEqual(parse_page_count(NEXT_DATA_PAGE), 416)

    def test_bytes_input(self):
        self.assertEqual(parse_page_count(JSON_LD_PAGE.encode('utf-8')), 320)

    def test_no_page_count(self):
        html = '<html><body><p data-testid="pagesFormat">Kindle Edition</p></body></html>'
        self.assertIsNone(parse_page_count(html))

    def test_zero_pages_is_ignored(self):
        html = '<script type="application/ld+json">{"@type":"Book","numberOfPages":0}</script>'
        self.assertIsNone(parse_page_count(html))

    def test_empty_input(self):
        self.assertIsNone(parse_page_count(''))
        self.assertIsNone(parse_page_count(None))


class TestBookUrl(unittest.TestCase):
    """Tests for Goodreads ID handling."""

    def test_numeric_id(self):
        self.assertEqual(book_url('12345'), 'https://www.goodreads.com/book/show/12345')

    def test_id_with_slug(self):
        self.assertEqual(normalize_goodreads_id('12345.The_Title'), '12345')
        self.assertEqual(normalize_goodreads_id('12345-the-title'), '12345')

    def test_id_with_whitespace(self):
        self.assertEqual(normalize_goodreads_id(' 678 '), '678')

    def test_invalid_id(self):
        self.assertIsNone(book_url('abc'))
        self.assertIsNone(book_url('12/../x'))
        self.assertIsNone(book_url(''))
        self.assertIsNone(book_url(None))


if __name__ == '__main__':
    unittest.main()
