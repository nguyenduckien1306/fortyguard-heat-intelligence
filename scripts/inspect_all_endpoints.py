"""Extract all endpoint details from docs JS bundle."""

import json
import re

with open("data/docs_dump/main.108dec8185160983.js", "r", encoding="utf-8") as f:
    text = f.read()

# Find all occurrences of {id:"..."
endpoint_blocks = re.findall(r'\{id:"([^"]+)",title:"([^"]+)",method:"([^"]+)",planAvailability:\{tier:"([^"]+)"\}[^}]*?description:"([^"]+)"', text)
for b in endpoint_blocks:
    print(f"=== {b[1]} ({b[2]} {b[0]}) ===")
    print(f"Tier: {b[3]}")
    print(f"Desc: {b[4][:150]}...")
    print()

# Search for heatmap and check-status definitions
for ep_id in ["heatmap", "satellite-view-segmentation", "street-view-segmentation", "heat-intelligence", "environmental-parameters", "check-status"]:
    pos = text.find(f'id:"{ep_id}"')
    if pos != -1:
        print(f"\n==================== {ep_id} ====================")
        snippet = text[pos:pos+2500]
        # find the code example
        code_m = re.search(r'code:"([^"]+)"', snippet)
        if code_m:
            print("Code example:\n", code_m.group(1).encode().decode('unicode-escape'))
