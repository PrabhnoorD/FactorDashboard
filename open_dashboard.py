"""
Run this to (re)build and open the ForgeAlpha dashboard with whatever data
is currently in forgealpha_dashboard_data.xlsx / All_NIFTY_Indices.xlsx.

    python "open_dashboard.py"

This does NOT re-download market data — run "fetch index data directly.py"
first (e.g. monthly) if you want fresh prices. This script just rebuilds the
dashboard HTML from whatever Excel data already exists, and opens it.
"""

import json
import os
import sys
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import prep_dashboard  # noqa: E402

TEMPLATE_FILE = os.path.join(HERE, "dashboard_template.html")
OUTPUT_FILE = os.path.join(HERE, "forgealpha_dashboard.html")
PUBLISH_FILE = os.path.join(HERE, "index.html")  # what GitHub Pages actually serves


def main():
    print("Rebuilding dashboard data from current Excel files...")
    payload = prep_dashboard.build_payload()
    data_json = json.dumps(payload, separators=(",", ":"))

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        template = f.read()
    if "__DATA_JSON__" not in template:
        raise RuntimeError("dashboard_template.html is missing the __DATA_JSON__ placeholder.")
    html = template.replace("__DATA_JSON__", data_json)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    with open(PUBLISH_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Sample: {payload['meta']['sampleStart']} -> {payload['meta']['sampleEnd']}")
    print(f"Dashboard written -> {OUTPUT_FILE}")
    print(f"Publish copy written -> {PUBLISH_FILE} (commit + push this to update the live site)")
    webbrowser.open("file:///" + OUTPUT_FILE.replace("\\", "/"))
    print("Opened in default browser.")


if __name__ == "__main__":
    main()
