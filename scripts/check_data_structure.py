#!/usr/bin/env python3
"""Check processed data structure"""
import json

with open('e:/数据可视化/G6/MC2/data/processed_data_v2.json','r') as f:
    d = json.load(f)

print('Top-level keys:', list(d.keys()))
print('vessels count:', len(d.get('vessels',[])))
print('delivery_vessel_links count:', len(d.get('delivery_vessel_links',[])))
print('delivery_reports count:', len(d.get('delivery_reports',[])))
print('similar_vessels count:', len(d.get('similar_vessels',[])))
print('tsne_mapping keys:', len(d.get('tsne_mapping',{})))
print('southseafood_vessels count:', len(d.get('southseafood_vessels',[])))
print('protected_areas:', d.get('protected_areas',[]))
print('fishing_grounds:', d.get('fishing_grounds',[]))
print('fish_types:', d.get('fish_types',[]))
print('locations:', d.get('locations',[]))

if d['vessels']:
    v = d['vessels'][0]
    print('Sample vessel keys:', list(v.keys()))
    print('  vessel_id:', v.get('vessel_id'))
    print('  vessel_name:', v.get('vessel_name'))
    print('  night_ratio:', v.get('night_ratio'))
    print('  protected_area_visits:', v.get('protected_area_visits'))
    print('  entropy:', v.get('entropy'))
    print('  region_visits:', list(v.get('region_visits',{}).keys())[:5])
    print('  transitions:', list(v.get('transitions',{}).keys())[:5])

if d['delivery_vessel_links']:
    dl = d['delivery_vessel_links'][0]
    print('Sample delivery link keys:', list(dl.keys()))
    print('  best_match_vessel:', dl.get('best_match_vessel'))
