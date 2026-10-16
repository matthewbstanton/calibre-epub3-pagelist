"""
Amazon helpers that need no network or Calibre.

Builds the product page URL from an ASIN and parses the page count
out of the fetched HTML. The fetch function itself is supplied by main.py.
"""
import html as html_lib
import re

PRODUCT_URL = 'https://www.amazon.com/dp/{}'

# An ASIN (or the ISBN-10 Amazon uses as a book's ASIN) is 10 letters and digits
_ASIN_RE = re.compile(r'^\s*([A-Za-z0-9]{10})\s*$')

_SCRIPT_STYLE_RE = re.compile(r'<(script|style)\b[^>]*>.*?</\1\s*>', re.IGNORECASE | re.DOTALL)
# The "Print length" carousel card, e.g. id="rpi-attribute-book_details-ebook_pages".
# Captures a short window after the opening tag, so nested tags don't cut the text off
_CAROUSEL_RE = re.compile(
    r'<[^>]*id\s*=\s*["\']rpi-attribute-book_details-\w*pages["\'][^>]*>(.{0,1000})',
    re.IGNORECASE | re.DOTALL,
)
_PAGES_TEXT_RE = re.compile(r'(\d[\d,]*)\s*pages?\b', re.IGNORECASE)
# Product details text once tags are stripped: "Print length : 352 pages",
# "Print Length: 352 pages" or a binding such as "Paperback : 352 pages"
_LABEL_SEP = r'[\s:]{0,20}'
_PRINT_LENGTH_RE = re.compile(r'\bPrint\s+length' + _LABEL_SEP + r'(\d[\d,]*)\s*pages?\b', re.IGNORECASE)
_BINDING_RE = re.compile(
    r'\b(?:Paperback|Hardcover|Mass\s+Market\s+Paperback|Board\s+book|Spiral-bound|Library\s+Binding)'
    + _LABEL_SEP + r'(\d[\d,]*)\s*pages?\b',
    re.IGNORECASE,
)
# Invisible direction marks Amazon puts around the ":" in its detail bullets
_DIRECTION_MARKS_RE = re.compile('[‎‏​ ]')


def normalize_asin(asin) -> str | None:
    """
    Return an ASIN in upper case, or None if it isn't one.
    """
    if asin is None:
        return None
    match = _ASIN_RE.match(str(asin))
    return match.group(1).upper() if match else None


def product_url(asin) -> str | None:
    """
    Return the Amazon product page URL for an ASIN, or None if the ASIN is invalid.
    """
    normalized = normalize_asin(asin)
    return PRODUCT_URL.format(normalized) if normalized else None


def _to_page_count(value: str) -> int | None:
    """
    Convert a page count string ("352", "1,024") to a positive int.
    """
    digits = value.replace(',', '')
    if not digits.isdigit():
        return None
    count = int(digits)
    return count if count > 0 else None


def _to_text(fragment: str) -> str:
    """
    Remove tags from an HTML fragment, unescape entities and drop direction marks.
    """
    text = html_lib.unescape(re.sub(r'<[^>]+>', ' ', fragment))
    return _DIRECTION_MARKS_RE.sub(' ', text)


def parse_page_count(html) -> int | None:
    """
    Parse the page count from an Amazon product page.

    Tries, in order:
    1. The "Print length" carousel card (``id="rpi-attribute-book_details-...pages"``).
    2. A "Print length" entry in the product details, e.g. "Print length : 352 pages".
    3. A binding entry in the product details, e.g. "Paperback : 352 pages".

    Returns None if no positive page count is found.
    """
    if not html:
        return None
    if isinstance(html, bytes):
        html = html.decode('utf-8', errors='replace')
    html = _SCRIPT_STYLE_RE.sub(' ', html)

    for fragment in _CAROUSEL_RE.findall(html):
        match = _PAGES_TEXT_RE.search(_to_text(fragment))
        if match:
            count = _to_page_count(match.group(1))
            if count:
                return count

    text = _to_text(html)
    for pattern in (_PRINT_LENGTH_RE, _BINDING_RE):
        for value in pattern.findall(text):
            count = _to_page_count(value)
            if count:
                return count

    return None
