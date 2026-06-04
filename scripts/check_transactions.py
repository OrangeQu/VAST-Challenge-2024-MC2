#!/usr/bin/env python3
"""Check transaction targets"""
import json

with open('e:/数据可视化/G6/MC2/mc2.json','r',encoding='utf-8') as f:
    data = json.load(f)

# Check all transaction targets
targets = set()
for l in data['links']:
    if 'Transaction' in l.get('type',''):
        targets.add(l['target'])
print('Transaction targets:')
for t in sorted(targets):
    print(f'  {t}')

# Check what cities are in the data
print('\nCities in data:')
cities = {'City of Haacklee', 'City of Lomark', 'City of Himark',
          'City of Paackland', 'City of South Paackland', 'City of Port Grove'}
for c in cities:
    print(f'  {c}: {"FOUND" if c in targets else "NOT FOUND"}')

# Check a few transaction links with their sources
print('\nSample transaction links:')
count = 0
for l in data['links']:
    if 'Transaction' in l.get('type',''):
        print(f'  {l["source"]} -> {l["target"]} (date: {l.get("date","")})')
        count += 1
        if count >= 10:
            break
