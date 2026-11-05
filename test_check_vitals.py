#!/usr/bin/env python3
"""Tests for check_vitals.py. Run with: python -m unittest test_check_vitals -v"""

import json
import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
