#!/usr/bin/env python3
"""Verify processed data output"""
import json

with open('e:/数据可视化/G6/MC2/data/processed_data_v2.json','r') as f:
    d = json.load(f)

print('Delivery-vessel links:', len(d['delivery_vessel_links']))
if d['delivery_vessel_links']:
    print('Sample:', json.dumps(d['delivery_vessel_links'][0], indent=2, ensure_ascii=False)[:400])
print('t-SNE mappings:', len(d['tsne_mapping']))
print('Similar vessels:', len(d['similar_vessels']))
print('Top 3 similar:')
for s in d['similar_vessels'][:3]:
    print(f'  {s["vessel_name"]} -> {s["similar_to_name"]}: {s["similarity_score"]}')
