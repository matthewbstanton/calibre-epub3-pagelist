"""
The result of a web request, as returned by the fetch function main.py supplies.
"""
from dataclasses import dataclass
from typing import Optional

# Characters of a fetched body shown in the "Show details" text
BODY_PREVIEW_CHARS = 3000


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
