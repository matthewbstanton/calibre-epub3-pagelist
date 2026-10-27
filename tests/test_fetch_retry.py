"""
Unit tests for fetch_with_retry; no network access and no real waiting.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.page_count import fetch as fetch_module
from core.page_count.fetch import FetchResult, fetch_with_retry


class FakeFetch:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def __call__(self, url):
        self.calls += 1
        return self.results.pop(0)


class TestFetchWithRetry(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(fetch_module.time, 'sleep')
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def test_success_first_try(self):
        fetch = FakeFetch([FetchResult(body=b'ok')])
        result = fetch_with_retry(fetch, 'u', lambda r: True)
        self.assertEqual(result.body, b'ok')
        self.assertEqual(fetch.calls, 1)
        self.sleep.assert_not_called()

    def test_retries_after_error_then_succeeds(self):
        fetch = FakeFetch([FetchResult(error=TimeoutError()), FetchResult(error=TimeoutError()),
                           FetchResult(body=b'ok')])
        result = fetch_with_retry(fetch, 'u', lambda r: True)
        self.assertEqual(result.body, b'ok')
        self.assertEqual(fetch.calls, 3)
        self.assertEqual(self.sleep.call_count, 2)
        self.sleep.assert_called_with(5)

    def test_retries_unusable_result(self):
        fetch = FakeFetch([FetchResult(body=b'bad'), FetchResult(body=b'good')])
        result = fetch_with_retry(fetch, 'u', lambda r: r.body == b'good')
        self.assertEqual(result.body, b'good')

    def test_gives_up_after_five_attempts(self):
        fetch = FakeFetch([FetchResult(error=TimeoutError()) for _ in range(5)])
        result = fetch_with_retry(fetch, 'u', lambda r: True)
        self.assertIsNotNone(result.error)
        self.assertEqual(fetch.calls, 5)
        self.assertEqual(self.sleep.call_count, 4)

    def test_no_retry_on_404(self):
        fetch = FakeFetch([FetchResult(status=404, error=Exception('nf'))])
        result = fetch_with_retry(fetch, 'u', lambda r: True)
        self.assertEqual(result.status, 404)
        self.assertEqual(fetch.calls, 1)


if __name__ == '__main__':
    unittest.main()
