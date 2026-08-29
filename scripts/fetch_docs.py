"""Script to fetch and analyze the JS bundle of the FortyGuard documentation site."""

import re
import urllib.request
from pathlib import Path

urls = [
    "https://docs-api.fortyguard.com/main.108dec8185160983.js",
    "https://docs-api.fortyguard.com/runtime.14d21fb1c977a9df.js",
    "https://docs-api.fortyguard.com/polyfills.63e92453d311f74b.js",
]

out_dir = Path("data/docs_dump")
out_dir.mkdir(parents=True, exist_ok=True)

for url in urls:
    filename = url.split("/")[-1]
    out_file = out_dir / filename
    print(f"Fetching {url} -> {out_file}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(content)
        print(f"  Saved {len(content):,} chars")
    except Exception as e:
        print(f"  Error: {e}")

# Search for endpoints in main.js
main_file = out_dir / "main.108dec8185160983.js"
if main_file.exists():
    with open(main_file, "r", encoding="utf-8") as f:
        text = f.read()

    # Search for all strings matching /v1/ or endpoints or paths
    print("\n--- Search for /v1/ or /api/ patterns ---")
    matches = set(re.findall(r'["\'`](/(?:v1|v2|api)[^"\'`\s]+)["\'`]', text))
    for m in sorted(matches):
        print("Endpoint match:", m)

    # Search for occurrences of heat, intelligence, segmentation, environmental
    print("\n--- Search for intelligence occurrences ---")
    intel_matches = re.findall(r'.{0,100}(?:heat-intelligence|heat_intelligence|Heat Intelligence|heatintelligence).{0,100}', text, re.IGNORECASE)
    for m in intel_matches[:20]:
        print("Intel context:", m.strip())

    # Search for route paths in documentation sidebar
    print("\n--- Search for doc routes / paths ---")
    doc_paths = set(re.findall(r'path:\s*["\']([^"\']+)["\']', text))
    for p in sorted(doc_paths):
        print("Doc route path:", p)
