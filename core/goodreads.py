"""
Goodreads helpers that need no network or Calibre.

Builds the book page URL from a Goodreads ID and parses the page count
out of the fetched HTML. The fetch itself lives in main.py.
"""
import html as html_lib
import json
import re

BOOK_URL = 'https://www.goodreads.com/book/show/{}'

# A Goodreads ID is numeric, optionally followed by a slug ("12345.Title" or "12345-title")
_ID_RE = re.compile(r'^\s*(\d+)(?:[.\-][\w.\-]*)?\s*$')

_JSON_LD_RE = re.compile(
    r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
# These capture a short window after the opening tag, so nested tags don't cut the text off
_PAGES_FORMAT_RE = re.compile(
    r'<[^>]*data-testid\s*=\s*["\']pagesFormat["\'][^>]*>(.{0,200})',
    re.IGNORECASE | re.DOTALL,
)
_ITEMPROP_PAGES_RE = re.compile(
    r'<[^>]*itemprop\s*=\s*["\']numberOfPages["\'][^>]*>(.{0,200})',
    re.IGNORECASE | re.DOTALL,
)
_PAGES_TEXT_RE = re.compile(r'(\d[\d,]*)\s*pages?\b', re.IGNORECASE)
# Embedded page data, e.g. Next.js state: "numPages":320 or "numberOfPages":"320"
_JSON_KEY_RE = re.compile(r'"(?:numberOfPages|numPages)"\s*:\s*"?(\d+)"?')


# Markers that show a response is a real book page rather than a bot check
_BOOK_DATA_MARKERS = ('application/ld+json', '__NEXT_DATA__', 'pagesFormat', 'numberOfPages')
# Real book pages are hundreds of KB; the AWS WAF challenge page is about 2-3 KB
_TINY_BODY_BYTES = 20000


def _header_names(headers) -> set[str]:
    """
    Return the lowercased header names from a dict, a list of pairs or an
    email.message-style object (as returned by mechanize's response.info()).
    """
    if not headers:
        return set()
    if hasattr(headers, 'keys'):
        names = headers.keys()
    elif hasattr(headers, 'items'):
        names = (name for name, _value in headers.items())
    else:
        names = (name for name, _value in headers)
    return {str(name).strip().lower() for name in names}


def has_waf_challenge_header(headers) -> bool:
    """
    Return True if the response headers carry AWS WAF's ``x-amzn-waf-action``.
    """
    return 'x-amzn-waf-action' in _header_names(headers)


def is_bot_challenge(status, headers, body) -> bool:
    """
    Return True if a Goodreads response is a bot check (the AWS WAF
    challenge) instead of a book page.

    Treated as a bot check:
    1. Any ``x-amzn-waf-action`` response header.
    2. HTTP status 202, which the challenge uses instead of 200.
    3. An empty or tiny body with none of the data a book page carries.
    """
    if has_waf_challenge_header(headers):
        return True
    if status == 202:
        return True
    if isinstance(body, bytes):
        body = body.decode('utf-8', errors='replace')
    body = body or ''
    if len(body) < _TINY_BODY_BYTES and not any(marker in body for marker in _BOOK_DATA_MARKERS):
        return True
    return False


def normalize_goodreads_id(goodreads_id) -> str | None:
    """
    Return the numeric part of a Goodreads ID, or None if it isn't one.
    Accepts IDs with a trailing slug such as "12345.Some_Title".
    """
    if goodreads_id is None:
        return None
    match = _ID_RE.match(str(goodreads_id))
    return match.group(1) if match else None


def book_url(goodreads_id) -> str | None:
    """
    Return the Goodreads book page URL for an ID, or None if the ID is invalid.
    """
    numeric_id = normalize_goodreads_id(goodreads_id)
    return BOOK_URL.format(numeric_id) if numeric_id else None


def _to_page_count(value) -> int | None:
    """
    Convert a page count value ("320", 320, "1,024 pages") to a positive int.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value >= 1 else None
    if isinstance(value, str):
        match = re.search(r'\d[\d,]*', value)
        if match:
            count = int(match.group(0).replace(',', ''))
            return count if count > 0 else None
    return None


def _find_number_of_pages(data) -> int | None:
    """
    Search parsed JSON-LD (dicts, lists, @graph) for the first usable numberOfPages.
    """
    if isinstance(data, dict):
        if 'numberOfPages' in data:
            count = _to_page_count(data['numberOfPages'])
            if count:
                return count
        for value in data.values():
            count = _find_number_of_pages(value)
            if count:
                return count
    elif isinstance(data, list):
        for item in data:
            count = _find_number_of_pages(item)
            if count:
                return count
    return None


def _strip_tags(fragment: str) -> str:
    """
    Remove tags from an HTML fragment and unescape entities.
    """
    return html_lib.unescape(re.sub(r'<[^>]+>', ' ', fragment))


def parse_page_count(html) -> int | None:
    """
    Parse the page count from a Goodreads book page.

    Tries, in order:
    1. JSON-LD ``numberOfPages``.
    2. The ``data-testid="pagesFormat"`` text, e.g. "320 pages, Paperback".
    3. A legacy ``itemprop="numberOfPages"`` element, e.g. "320 pages".
    4. A ``"numberOfPages"`` or ``"numPages"`` key anywhere in embedded JSON.

    Returns None if no positive page count is found.
    """
    if not html:
        return None
    if isinstance(html, bytes):
        html = html.decode('utf-8', errors='replace')

    for block in _JSON_LD_RE.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        count = _find_number_of_pages(data)
        if count:
            return count

    for pattern in (_PAGES_FORMAT_RE, _ITEMPROP_PAGES_RE):
        for fragment in pattern.findall(html):
            match = _PAGES_TEXT_RE.search(_strip_tags(fragment))
            if match:
                count = _to_page_count(match.group(1))
                if count:
                    return count

    for value in _JSON_KEY_RE.findall(html):
        count = _to_page_count(value)
        if count:
            return count

    return None
