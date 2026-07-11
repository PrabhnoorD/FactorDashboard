# ForgeAlpha — Relative Factor Performance and Sector Regime

A live-in-the-browser dashboard tracking NIFTY smart-beta factor performance, Fama-French style
factors, and sector regime signals. No backend — every regression, correlation, and rolling
statistic is computed client-side in vanilla JS from a single embedded data payload.

**Live site:** served from `index.html` via GitHub Pages.

## Updating the data (monthly)

1. Refresh the source Excel/CSV files this pipeline reads (see `prep_dashboard.py` for the exact
   paths — they live outside this repo, since they're the raw private data sources).
2. From this folder, run:
   ```
   python open_dashboard.py
   ```
   This rebuilds `index.html` (the published copy) and `forgealpha_dashboard.html` (a local copy
   opened automatically in your browser to sanity-check before publishing).
3. Commit and push `index.html` — GitHub Pages redeploys automatically.
   ```
   git add index.html
   git commit -m "Monthly data refresh: <month>"
   git push
   ```

## Files

- `dashboard_template.html` — the actual dashboard: HTML/CSS + all JS (OLS regression with
  Newey-West HAC standard errors, correlations, rolling stats, all charts). Contains a
  `__DATA_JSON__` placeholder that `open_dashboard.py` fills in.
- `prep_dashboard.py` — reads the source Excel/CSV files and builds the JSON data payload
  (monthly + daily price series, no precomputed statistics — everything downstream is computed
  live in the browser).
- `open_dashboard.py` — stitches the template + data payload together, writes `index.html` +
  `forgealpha_dashboard.html`, opens the local copy in a browser.

## Adding features

Edit `dashboard_template.html` directly, then re-run `python open_dashboard.py` to regenerate
`index.html` before committing.
