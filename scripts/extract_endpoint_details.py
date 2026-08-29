"""Extract all documentation endpoints and details from the bundle."""

import json
import re

with open("data/docs_dump/main.108dec8185160983.js", "r", encoding="utf-8") as f:
    text = f.read()

# Find the endpoints array / objects
# Look for id:"heat-intelligence" or id:"heatmap"
pos = text.find('id:"heat-intelligence"')
if pos != -1:
    print("Found heat-intelligence at pos", pos)
    snippet = text[pos-100:pos+3000]
    print("--- SNIPPET ---")
    print(snippet)

# Also let's extract all endpoint definitions
matches = re.findall(r'\{id:"([^"]+)",title:"([^"]+)",method:"([^"]+)",planAvailability:\{tier:"([^"]+)"\}', text)
print("\n--- ALL DOCUMENTED ENDPOINTS ---")
for m in matches:
    print(f"ID: {m[0]} | Title: {m[1]} | Method: {m[2]} | Tier: {m[3]}")
