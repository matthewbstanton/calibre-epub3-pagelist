"""
The result of a web request, as returned by the fetch function fetcher.py supplies.
"""
import time
from dataclasses import dataclass
from typing import Callable, Optional

# Characters of a fetched body shown in the "Show details" text
BODY_PREVIEW_CHARS = 3000

# Tries per book for a web page, and seconds to wait between failed tries
FETCH_ATTEMPTS = 5
FETCH_RETRY_DELAY = 5

# Statuses that a retry can't change
NO_RETRY_STATUSES = (404, 410)


@dataclass
class FetchResult:
    """
    What a fetch function returns: the response, or the error that stopped it.
    """
    user_agent: Optional[str] = None
    status: Optional[int] = None
    headers: Optional[str] = None
    body: Optional[bytes] = None
    error: Optional[Exception] = None


def describe_fetch(url: str, result: FetchResult) -> str:
    """
    Return a readable description of a request and its response.
    """
    lines = [f'URL: {url}']
    if result.user_agent:
        lines.append(f'User agent: {result.user_agent}')
    if result.error is not None:
        lines.append(f'Error: {result.error!r}')
    if result.status is not None:
        lines.append(f'Status: {result.status}')
    if result.headers:
        lines.append('Headers:')
        lines.extend(f'    {line}' for line in result.headers.strip().splitlines())
    if result.body is not None:
        body = result.body
        text = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else str(body)
        lines.append(f'Body ({len(text)} characters, first {min(len(text), BODY_PREVIEW_CHARS)} shown):')
        lines.append(text[:BODY_PREVIEW_CHARS])
    return '\n'.join(lines)


def fetch_with_retry(fetch: Callable[[str], FetchResult], url: str,
                     is_usable: Callable[[FetchResult], bool]) -> FetchResult:
    """
    Fetch a URL, trying up to FETCH_ATTEMPTS times with FETCH_RETRY_DELAY seconds
    between tries until the fetch has no error and is_usable accepts the result.
    Return the last result.
    """
    for attempt in range(FETCH_ATTEMPTS):
        result = fetch(url)
        if result.error is None and is_usable(result):
            return result
        if result.status in NO_RETRY_STATUSES or attempt == FETCH_ATTEMPTS - 1:
            return result
        time.sleep(FETCH_RETRY_DELAY)
    return result
