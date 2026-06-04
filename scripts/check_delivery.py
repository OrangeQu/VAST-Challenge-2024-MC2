#!/usr/bin/env python3
"""Check delivery report structure"""
import json

with open('e:/数据可视化/G6/MC2/mc2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Check delivery reports
count = 0
for n in data['nodes']:
    if 'DeliveryReport' in n.get('type', ''):
        print(json.dumps(n, indent=2, ensure_ascii=False))
        count += 1
        if count >= 3:
            break

print("\n--- Checking raw_source patterns ---")
sources = set()
for n in data['nodes']:
    if 'DeliveryReport' in n.get('type', ''):
        src = n.get('_raw_source', '')
        # Extract first part
        parts = src.split('/')
        if parts:
            sources.add(parts[0])
for s in sorted(sources):
    print(f"  {s}")

print("\n--- Checking transaction links ---")
count = 0
for l in data['links']:
    if 'Transaction' in l.get('type', ''):
        print(json.dumps(l, indent=2, ensure_ascii=False))
        count += 1
        if count >= 2:
            break
