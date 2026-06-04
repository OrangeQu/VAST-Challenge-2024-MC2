#!/usr/bin/env python3
"""Check processed data output"""
import json

with open('e:/数据可视化/G6/MC2/data/processed_data_v2.json','r') as f:
    d = json.load(f)

print('Keys:', list(d.keys()))
print('Vessels:', len(d['vessels']))
print('t-SNE mappings:', len(d['tsne_mapping']))
print('Similar vessels:', len(d['similar_vessels']))
print('SouthSeafood vessels:', len(d['southseafood_vessels']))
print('Locations:', len(d['locations']))
print('Fish types:', len(d['fish_types']))
print('Delivery reports:', len(d['delivery_reports']))
print('Delivery-vessel links:', len(d['delivery_vessel_links']))
print()

if d['delivery_vessel_links']:
    print('Sample delivery-vessel link:')
    print(json.dumps(d['delivery_vessel_links'][0], indent=2, ensure_ascii=False)[:500])
else:
    print('No delivery-vessel links found!')
print()

if d['similar_vessels']:
    print('Top 5 similar vessels:')
    for s in d['similar_vessels'][:5]:
        print(f'  {s["vessel_name"]} ({s["company"]}) -> {s["similar_to_name"]}: {s["similarity_score"]}')

print()
print('SouthSeafood vessels:')
for sv in d['southseafood_vessels']:
    info = sv['vessel_info']
    print(f'  {info["name"]} ({info["id"]}) - {info["length_overall"]}m, {info["tonnage"]}t')
    feat = sv['features']
    print(f'  Pings: {feat.get("total_pings",0)}, Protected: {feat.get("protected_area_visits",0)}, Night ratio: {feat.get("night_ratio",0)}')
    print(f'  Night fishing ratio: {feat.get("night_fishing_ratio",0)}, Protected dwell: {feat.get("protected_dwell_ratio",0)}')
    print()
