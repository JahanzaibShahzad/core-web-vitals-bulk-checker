#!/usr/bin/env python3
"""Tests for check_vitals.py. Run with: python -m unittest test_check_vitals -v"""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import check_vitals


def load_fixture(name):
    path = os.path.join(os.path.dirname(__file__), "fixtures", name)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class TestExtractMetrics(unittest.TestCase):
    def test_good_page_passes(self):
        data = load_fixture("psi_response_good.json")
        metrics = check_vitals.extract_metrics(data)
        self.assertEqual(metrics["lcp_ms"], 1800)
        self.assertEqual(metrics["inp_ms"], 120)
        self.assertAlmostEqual(metrics["cls"], 0.05)
        self.assertEqual(metrics["overall"], "pass")
        self.assertEqual(metrics["lcp_verdict"], "pass")
        self.assertEqual(metrics["inp_verdict"], "pass")
        self.assertEqual(metrics["cls_verdict"], "pass")
        self.assertEqual(metrics["performance_score"], 0.95)

    def test_slow_page_fails(self):
        data = load_fixture("psi_response_slow.json")
        metrics = check_vitals.extract_metrics(data)
        self.assertEqual(metrics["lcp_ms"], 4200)
        self.assertEqual(metrics["overall"], "fail")
        self.assertEqual(metrics["lcp_verdict"], "fail")
        self.assertEqual(metrics["inp_verdict"], "pass")
        self.assertEqual(metrics["cls_verdict"], "pass")

    def test_missing_metrics_are_unknown_not_invented(self):
        metrics = check_vitals.extract_metrics({})
        self.assertIsNone(metrics["lcp_ms"])
        self.assertIsNone(metrics["inp_ms"])
        self.assertIsNone(metrics["cls"])
        self.assertEqual(metrics["overall"], "unknown")
        self.assertEqual(metrics["lcp_verdict"], "unknown")


class TestReadUrls(unittest.TestCase):
    def test_skips_blanks_and_comments(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
            handle.write("# comment line\n\nhttps://example.com\n  https://example.org  \n")
            path = handle.name
        try:
            urls = check_vitals.read_urls(path)
        finally:
            os.unlink(path)
        self.assertEqual(urls, ["https://example.com", "https://example.org"])

    def test_missing_file_raises(self):
        with self.assertRaises(OSError):
            check_vitals.read_urls("/nonexistent/urls.txt")


class TestThresholds(unittest.TestCase):
    def test_thresholds_match_google_good_values(self):
        self.assertEqual(check_vitals.THRESHOLDS["lcp_ms"], 2500)
        self.assertEqual(check_vitals.THRESHOLDS["inp_ms"], 200)
        self.assertAlmostEqual(check_vitals.THRESHOLDS["cls"], 0.1)


def _http_error(code):
    body = io.BytesIO(json.dumps({"error": {"message": "error {}".format(code)}}).encode("utf-8"))
    return urllib.error.HTTPError("https://example.com", code, "error", {}, body)


class TestRetries(unittest.TestCase):
    def _ok_response(self):
        body = io.StringIO(json.dumps(load_fixture("psi_response_good.json")))
        response = mock.MagicMock()
        response.__enter__.return_value = body
        response.__exit__.return_value = False
        return response

    @mock.patch("check_vitals.time.sleep")
    @mock.patch("check_vitals.urllib.request.urlopen")
    def test_retries_after_rate_limit_then_succeeds(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = [
            _http_error(429),
            _http_error(429),
            self._ok_response(),
        ]
        data = check_vitals.fetch_psi_result("https://example.com", "mobile", None, retries=2)
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(data["lighthouseResult"]["audits"]["largest-contentful-paint"]["numericValue"], 1800)
        self.assertEqual(mock_sleep.call_count, 2)

    @mock.patch("check_vitals.time.sleep")
    @mock.patch("check_vitals.urllib.request.urlopen")
    def test_no_retry_on_client_error(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = _http_error(400)
        with self.assertRaises(urllib.error.HTTPError):
            check_vitals.fetch_psi_result("https://example.com", "mobile", None, retries=2)
        self.assertEqual(mock_urlopen.call_count, 1)
        mock_sleep.assert_not_called()

    @mock.patch("check_vitals.time.sleep")
    @mock.patch("check_vitals.urllib.request.urlopen")
    def test_retries_exhausted_raises(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = _http_error(500)
        with self.assertRaises(urllib.error.HTTPError):
            check_vitals.fetch_psi_result("https://example.com", "mobile", None, retries=2)
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    def test_is_retryable_status(self):
        self.assertTrue(check_vitals.is_retryable_status(429))
        self.assertTrue(check_vitals.is_retryable_status(500))
        self.assertTrue(check_vitals.is_retryable_status(503))
        self.assertFalse(check_vitals.is_retryable_status(400))
        self.assertFalse(check_vitals.is_retryable_status(404))


if __name__ == "__main__":
    unittest.main()
