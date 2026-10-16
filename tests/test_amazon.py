"""
Unit tests for the Amazon page count parser.

Uses small HTML fixtures; no network access.
"""
import os
import sys
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.page_count.amazon.parser import parse_page_count, product_url, normalize_asin


CAROUSEL_PAGE = """<html><body>
<div id="rpi-attribute-book_details-ebook_pages" class="a-section a-spacing-none a-padding-base rpi-attribute-content">
<div class="a-section a-spacing-small a-text-center rpi-attribute-label"><span>Print length</span></div>
<div class="a-section a-spacing-none a-text-center rpi-icon"><img alt="" src="pages.png"></div>
<div class="a-section a-spacing-none a-text-center rpi-attribute-value"><span>352 pages</span></div>
</div>
<div id="detailBullets_feature_div"><ul><li><span class="a-list-item">
<span class="a-text-bold">Print length &rlm; : &lrm;</span> <span>999 pages</span></span></li></ul></div>
</body></html>"""

FIONA_CAROUSEL_PAGE = """<div id="rpi-attribute-book_details-fiona_pages">
<div class="rpi-attribute-label"><span>Print length</span></div>
<div class="rpi-attribute-value"><span><a href="#">1,024 pages</a></span></div></div>"""

DETAIL_BULLETS_PAGE = """<html><body>
<div id="detailBullets_feature_div"><ul class="a-unordered-list a-nostyle a-vertical">
<li><span class="a-list-item"><span class="a-text-bold">Publisher &rlm; : &lrm;</span> <span>Tor Books</span></span></li>
<li><span class="a-list-item"><span class="a-text-bold">Language &rlm; : &lrm;</span> <span>English</span></span></li>
<li><span class="a-list-item"><span class="a-text-bold">Print length &rlm; : &lrm;</span> <span>288 pages</span></span></li>
</ul></div></body></html>"""

DETAIL_BULLETS_RAW_MARKS_PAGE = ('<li><span class="a-text-bold">Print length ‏ : ‎</span>'
                                 ' <span>416 pages</span></li>')

DETAILS_TABLE_PAGE = """<table id="productDetailsTable"><tr>
<th class="a-color-secondary a-size-base prodDetSectionEntry">Print Length</th>
<td class="a-size-base prodDetAttrValue">512 pages</td></tr></table>"""

LEGACY_BULLETS_PAGE = """<table id="productDetailsTable"><tr><td class="bucket"><div class="content"><ul>
<li><b>Paperback:</b> 240 pages</li>
<li><b>Publisher:</b> Penguin (May 1, 2005)</li>
</ul></div></td></tr></table>"""

HARDCOVER_BULLETS_PAGE = ('<div id="detailBullets_feature_div"><span class="a-text-bold">Hardcover &rlm; : &lrm;</span>'
                          ' <span>400 pages</span></div>')

SCRIPT_ONLY_PAGE = """<html><head><script>var x = "Print length: 777 pages";</script></head>
<body><p>Kindle Edition</p></body></html>"""


class TestParsePageCount(unittest.TestCase):
    """Tests for parse_page_count."""

    def test_print_length_carousel(self):
        self.assertEqual(parse_page_count(CAROUSEL_PAGE), 352)

    def test_carousel_with_nested_link_and_thousands_separator(self):
        self.assertEqual(parse_page_count(FIONA_CAROUSEL_PAGE), 1024)

    def test_detail_bullets_print_length(self):
        self.assertEqual(parse_page_count(DETAIL_BULLETS_PAGE), 288)

    def test_detail_bullets_with_raw_direction_marks(self):
        self.assertEqual(parse_page_count(DETAIL_BULLETS_RAW_MARKS_PAGE), 416)

    def test_details_table(self):
        self.assertEqual(parse_page_count(DETAILS_TABLE_PAGE), 512)

    def test_legacy_binding_bullet(self):
        self.assertEqual(parse_page_count(LEGACY_BULLETS_PAGE), 240)

    def test_hardcover_detail_bullet(self):
        self.assertEqual(parse_page_count(HARDCOVER_BULLETS_PAGE), 400)

    def test_print_length_preferred_over_binding(self):
        html = ('<li><b>Paperback:</b> 300 pages</li>'
                '<li><b>Print Length:</b> 320 pages</li>')
        self.assertEqual(parse_page_count(html), 320)

    def test_scripts_are_ignored(self):
        self.assertIsNone(parse_page_count(SCRIPT_ONLY_PAGE))

    def test_bytes_input(self):
        self.assertEqual(parse_page_count(CAROUSEL_PAGE.encode('utf-8')), 352)

    def test_no_page_count(self):
        html = '<html><body><span class="a-text-bold">Language : </span><span>English</span></body></html>'
        self.assertIsNone(parse_page_count(html))

    def test_zero_pages_is_ignored(self):
        self.assertIsNone(parse_page_count('<li><b>Print Length:</b> 0 pages</li>'))

    def test_empty_input(self):
        self.assertIsNone(parse_page_count(''))
        self.assertIsNone(parse_page_count(None))


class TestProductUrl(unittest.TestCase):
    """Tests for ASIN handling."""

    def test_asin(self):
        self.assertEqual(product_url('B00ABCDEFG'), 'https://www.amazon.com/dp/B00ABCDEFG')

    def test_isbn10_asin(self):
        self.assertEqual(product_url('076532637X'), 'https://www.amazon.com/dp/076532637X')

    def test_lowercase_and_whitespace(self):
        self.assertEqual(normalize_asin(' b00abcdefg '), 'B00ABCDEFG')

    def test_invalid_asin(self):
        self.assertIsNone(product_url('B00ABC'))
        self.assertIsNone(product_url('B00ABCDEFGH'))
        self.assertIsNone(product_url('../B00ABCD'))
        self.assertIsNone(product_url(''))
        self.assertIsNone(product_url(None))


if __name__ == '__main__':
    unittest.main()
