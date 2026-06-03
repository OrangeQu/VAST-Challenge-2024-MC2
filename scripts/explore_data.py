#!/usr/bin/env python3
"""Explore the mc2.json data structure"""
import json
from collections import Counter

with open('e:/数据可视化/G6/MC2/mc2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

nodes = data['nodes']
links = data['links']

print(f"Total nodes: {len(nodes)}")
print(f"Total links: {len(links)}")
print()

# Node types
node_types = Counter()
for n in nodes:
    node_types[n.get('type', 'unknown')] += 1
print("=== NODE TYPES ===")
for t, c in node_types.most_common():
    print(f"  {t}: {c}")

print()

# Link types
link_types = Counter()
for l in links:
    link_types[l.get('type', 'unknown')] += 1
print("=== LINK TYPES ===")
for t, c in link_types.most_common():
    print(f"  {t}: {c}")

print()

# Sample a vessel node
print("=== SAMPLE VESSEL NODE ===")
for n in nodes:
    if 'Vessel' in n.get('type', ''):
        print(json.dumps(n, indent=2, ensure_ascii=False)[:500])
        break

print()

# Sample a location node
print("=== SAMPLE LOCATION NODE ===")
for n in nodes:
    if 'Location' in n.get('type', ''):
        print(json.dumps(n, indent=2, ensure_ascii=False)[:500])
        break

print()

# Sample a link
print("=== SAMPLE LINK (TransponderPing) ===")
for l in links:
    if 'TransponderPing' in l.get('type', ''):
        print(json.dumps(l, indent=2, ensure_ascii=False)[:500])
        break

print()

# Sample a HarborReport link
print("=== SAMPLE LINK (HarborReport) ===")
for l in links:
    if 'HarborReport' in l.get('type', ''):
        print(json.dumps(l, indent=2, ensure_ascii=False)[:500])
        break

print()

# Check for location coordinates
print("=== LOCATIONS WITH COORDINATES ===")
for n in nodes:
    if 'Location' in n.get('type', ''):
        if 'lat' in n or 'lon' in n or 'latitude' in n or 'longitude' in n or 'coordinates' in n:
            print(f"  {n.get('Name', n['id'])}: lat={n.get('lat', n.get('latitude', 'N/A'))}, lon={n.get('lon', n.get('longitude', 'N/A'))}")
        else:
            # Print all keys
            print(f"  {n.get('Name', n['id'])} keys: {list(n.keys())}")

print()

# Check time range
print("=== TIME RANGE ===")
times = []
for l in links:
    t = l.get('time', l.get('date', ''))
    if t:
        times.append(t)
times.sort()
if times:
    print(f"  First: {times[0]}")
    print(f"  Last: {times[-1]}")
    print(f"  Sample times: {times[:5]}")

print()

# Check companies
print("=== COMPANIES ===")
companies = Counter()
for n in nodes:
    if 'Vessel' in n.get('type', ''):
        companies[n.get('company', 'Unknown')] += 1
for c, cnt in companies.most_common():
    print(f"  {c}: {cnt}")

print()

# Check SouthSeafood vessels
print("=== SOUTHSEAFOOD VESSELS ===")
for n in nodes:
    if 'Vessel' in n.get('type', '') and n.get('company') == 'SouthSeafood Express Corp':
        print(json.dumps(n, indent=2, ensure_ascii=False))
