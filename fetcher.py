from calibre_plugins.epub3_pagelist.core.page_count import FetchResult


class CalibreFetcher:
    """
    Fetches web pages with calibre's browser for page count sources that read
    a web page, such as Goodreads and Amazon. Pass fetch() as the fetch function.
    """
    # Seconds to wait for a web page before giving up on that book
    TIMEOUT = 30

    def fetch(self, url):
        """
        Fetch a URL and return a FetchResult.
        """
        from calibre import browser
        from calibre.utils.random_ua import random_common_chrome_user_agent
        # Same browser identity calibre's metadata sources and the Count Pages plugin use
        user_agent = random_common_chrome_user_agent()
        try:
            response = browser(user_agent=user_agent).open_novisit(url, timeout=self.TIMEOUT)
            return FetchResult(user_agent=user_agent, status=getattr(response, 'code', None),
                               headers=str(response.info()), body=response.read())
        except Exception as e:
            # HTTP errors carry their own status, headers and body
            info = getattr(e, 'info', None)
            try:
                body = e.read() if callable(getattr(e, 'read', None)) else None
            except Exception:
                body = None
            return FetchResult(user_agent=user_agent, status=getattr(e, 'code', None),
                               headers=str(info()) if callable(info) else None, body=body, error=e)
