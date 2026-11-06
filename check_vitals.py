#!/usr/bin/env python3
"""Bulk Core Web Vitals checker using the Google PageSpeed Insights API.

Reads a list of URLs, checks each one against the PageSpeed Insights API
for mobile and/or desktop, and writes the results to a CSV file.

Requires a free Google PageSpeed Insights API key. Get one from the
Google Cloud Console (enable the PageSpeed Insights API) and pass it with
--api-key or set the PSI_API_KEY environment variable.

Usage:
    python check_vitals.py --input urls.txt --output results.csv
    python check_vitals.py --input urls.txt --output results.csv --strategy desktop
    python check_vitals.py --input urls.txt --output results.csv --api-key YOUR_KEY

Only the Python standard library is used.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Core Web Vitals "good" thresholds (Google, 2024).
THRESHOLDS = {
    "lcp_ms": 2500,   # Largest Contentful Paint: good at 2.5s or less
    "inp_ms": 200,    # Interaction to Next Paint: good at 200ms or less
    "cls": 0.1,       # Cumulative Layout Shift: good at 0.1 or less
}


def is_retryable_status(code):
    """True for transient HTTP statuses worth retrying: rate limiting (429)
    and server errors (5xx). Client errors such as 400 or 404 are not
    retryable, retrying them would only burn quota."""
    return code == 429 or 500 <= code < 600


def fetch_psi_result(url, strategy, api_key, timeout=60, retries=2):
    """Call the PageSpeed Insights API for one URL and strategy.

    Returns the parsed JSON response dict. Transient failures (HTTP 429
    rate limits and 5xx server errors) are retried with exponential
    backoff, up to ``retries`` times. Other errors raise
    urllib.error.URLError / HTTPError as before.
    """
    params = {
        "url": url,
        "strategy": strategy,
        "category": "performance",
    }
    if api_key:
        params["key"] = api_key
    request_url = API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(request_url, headers={"User-Agent": "core-web-vitals-bulk-checker"})
    last_error = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if not is_retryable_status(exc.code) or attempt == retries:
                raise
            wait = 2 ** attempt
            print("HTTP {} for {} ({}), retrying in {}s...".format(
                exc.code, url, strategy, wait), file=sys.stderr)
            time.sleep(wait)
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print("Request failed for {} ({}), retrying in {}s: {}".format(
                url, strategy, wait, exc.reason), file=sys.stderr)
            time.sleep(wait)
    raise last_error  # pragma: no cover - loop always raises or returns


def extract_metrics(data):
    """Pull the metrics we care about out of a PageSpeed Insights response.

    Returns a dict with numeric values (or None when a metric is missing)
    plus a pass/fail verdict per metric against Google's thresholds.
    Missing metrics are reported as None rather than invented.
    """
    lighthouse = data.get("lighthouseResult", {})
    audits = lighthouse.get("audits", {})
    categories = lighthouse.get("categories", {})
    performance = categories.get("performance", {})

    def numeric_value(audit_id):
        audit = audits.get(audit_id, {})
        value = audit.get("numericValue")
        return value if isinstance(value, (int, float)) else None

    def display_value(audit_id):
        audit = audits.get(audit_id, {})
        return audit.get("displayValue")

    lcp = numeric_value("largest-contentful-paint")
    inp = numeric_value("interaction-to-next-paint")
    cls = numeric_value("cumulative-layout-shift")
    fcp = numeric_value("first-contentful-paint")
    tbt = numeric_value("total-blocking-time")
    speed_index = numeric_value("speed-index")

    def verdict(value, threshold):
        if value is None:
            return "unknown"
        return "pass" if value <= threshold else "fail"

    overall = "pass"
    for value, threshold in ((lcp, THRESHOLDS["lcp_ms"]),
                             (inp, THRESHOLDS["inp_ms"]),
                             (cls, THRESHOLDS["cls"])):
        if value is not None and value > threshold:
            overall = "fail"
    if lcp is None and inp is None and cls is None:
        overall = "unknown"

    return {
        "performance_score": performance.get("score"),
        "lcp_ms": lcp,
        "lcp_display": display_value("largest-contentful-paint"),
        "inp_ms": inp,
        "inp_display": display_value("interaction-to-next-paint"),
        "cls": cls,
        "fcp_ms": fcp,
        "tbt_ms": tbt,
        "speed_index_ms": speed_index,
        "lcp_verdict": verdict(lcp, THRESHOLDS["lcp_ms"]),
        "inp_verdict": verdict(inp, THRESHOLDS["inp_ms"]),
        "cls_verdict": verdict(cls, THRESHOLDS["cls"]),
        "overall": overall,
    }


def check_url(url, strategy, api_key, retries=2):
    """Check one URL and return a flat dict ready for CSV output."""
    row = {"url": url, "strategy": strategy, "error": ""}
    try:
        data = fetch_psi_result(url, strategy, api_key, retries=retries)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        row["error"] = "HTTP {} {}".format(exc.code, detail or exc.reason)
        return row
    except urllib.error.URLError as exc:
        row["error"] = "Request failed: {}".format(exc.reason)
        return row
    except (json.JSONDecodeError, TimeoutError) as exc:
        row["error"] = "Bad response: {}".format(exc)
        return row

    metrics = extract_metrics(data)
    row.update(metrics)
    return row


def read_urls(path):
    """Read URLs from a text file, one per line. Blank lines and lines
    starting with # are skipped."""
    urls = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    return urls


CSV_FIELDS = [
    "url",
    "strategy",
    "overall",
    "performance_score",
    "lcp_ms",
    "lcp_display",
    "lcp_verdict",
    "inp_ms",
    "inp_display",
    "inp_verdict",
    "cls",
    "cls_verdict",
    "fcp_ms",
    "tbt_ms",
    "speed_index_ms",
    "error",
]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Bulk Core Web Vitals checker via the PageSpeed Insights API."
    )
    parser.add_argument("--input", required=True,
                        help="Text file with one URL per line.")
    parser.add_argument("--output", required=True,
                        help="CSV file to write results to.")
    parser.add_argument("--strategy", choices=["mobile", "desktop", "both"],
                        default="mobile",
                        help="Device strategy to test (default: mobile).")
    parser.add_argument("--api-key", default=os.environ.get("PSI_API_KEY"),
                        help="PageSpeed Insights API key (or set PSI_API_KEY).")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds to wait between API calls (default: 2).")
    parser.add_argument("--retries", type=int, default=2,
                        help="Retries for transient errors such as HTTP 429 "
                        "rate limits and 5xx server errors (default: 2, "
                        "use 0 to disable).")
    args = parser.parse_args(argv)

    try:
        urls = read_urls(args.input)
    except OSError as exc:
        print("Cannot read input file: {}".format(exc), file=sys.stderr)
        return 1
    if not urls:
        print("No URLs found in {}.".format(args.input), file=sys.stderr)
        return 1

    strategies = ["mobile", "desktop"] if args.strategy == "both" else [args.strategy]
    total = len(urls) * len(strategies)
    done = 0

    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for url in urls:
            for strategy in strategies:
                done += 1
                print("[{}/{}] {} ({})".format(done, total, url, strategy))
                row = check_url(url, strategy, args.api_key, retries=args.retries)
                writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
                if done < total:
                    time.sleep(args.delay)

    print("Done. Results written to {}.".format(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
