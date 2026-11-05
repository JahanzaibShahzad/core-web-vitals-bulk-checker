# Core Web Vitals Bulk Checker

Check Core Web Vitals for a whole list of URLs at once, using the free
Google PageSpeed Insights API. Results go to a CSV file you can open in
Excel or Google Sheets.

Built by Jahanzaib Shahzad, Local SEO and Digital Marketing Specialist.

## What it checks

For every URL (mobile and/or desktop), the script reports:

- **LCP** (Largest Contentful Paint) in ms
- **INP** (Interaction to Next Paint) in ms
- **CLS** (Cumulative Layout Shift)
- **FCP** (First Contentful Paint), **TBT** (Total Blocking Time), **Speed Index**
- **Performance score** (Lighthouse 0-1)
- **Pass / fail** verdict per metric and an overall verdict

Verdicts use Google's "good" thresholds: LCP 2.5s or less, INP 200ms or
less, CLS 0.1 or less.

## Setup

Python 3.8 or newer. No third-party packages needed, only the standard
library.

1. Clone the repo and enter the folder.
2. Get a free PageSpeed Insights API key:
   - Open the Google Cloud Console.
   - Create a project (or use an existing one).
   - Enable the **PageSpeed Insights API**.
   - Create an API key under **APIs and Services > Credentials**.
   - The API has a free quota; check the current limits in the Cloud Console.
3. Put your key in the environment or pass it on the command line:

```bash
export PSI_API_KEY="your-key-here"
```

The script also works without a key, but the API quota is much lower
then, so a key is strongly recommended for bulk runs.

## Usage

1. Create a text file with one URL per line (see `urls.example.txt`).
   Lines starting with `#` and blank lines are ignored.
2. Run the checker:

```bash
python check_vitals.py --input urls.txt --output results.csv
```

Useful options:

```bash
# Desktop results instead of mobile
python check_vitals.py --input urls.txt --output results.csv --strategy desktop

# Both mobile and desktop in one run (two rows per URL)
python check_vitals.py --input urls.txt --output results.csv --strategy both

# Pass the key directly instead of using the environment variable
python check_vitals.py --input urls.txt --output results.csv --api-key YOUR_KEY

# Wait 5 seconds between calls (helps stay inside the API rate limit)
python check_vitals.py --input urls.txt --output results.csv --delay 5
```

## Output

`results.csv` has one row per URL per strategy:

| Column | Meaning |
| --- | --- |
| url | The URL that was checked |
| strategy | mobile or desktop |
| overall | pass, fail, or unknown |
| performance_score | Lighthouse performance score (0-1) |
| lcp_ms / lcp_display / lcp_verdict | Largest Contentful Paint |
| inp_ms / inp_display / inp_verdict | Interaction to Next Paint |
| cls / cls_verdict | Cumulative Layout Shift |
| fcp_ms | First Contentful Paint |
| tbt_ms | Total Blocking Time |
| speed_index_ms | Speed Index |
| error | Error message if the check failed for this URL |

URLs that fail (bad URL, site down, API error) still get a row, with the
error column filled in, so no URL silently disappears from the results.

## Honest notes

- These are **lab** results from a single PageSpeed Insights run, not
  real-user field data. A page can pass in the lab and still fail for real
  visitors, and the other way round. For field data, look at the Chrome
  UX Report (CrUX) or your own analytics.
- Results vary between runs. If a URL is borderline, run it twice before
  deciding it needs fixing.
- PageSpeed Insights scores are a diagnostic tool, not a ranking
  guarantee. Good Core Web Vitals help user experience and are a small
  ranking signal, but they do not replace content, relevance, and links.

## Tests

```bash
python -m unittest test_check_vitals -v
```

## License

MIT. See `LICENSE`.
