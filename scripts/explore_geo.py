#!/usr/bin/env python3
"""Explore GeoJSON data"""
import json

with open('e:/数据可视化/G6/MC2/Oceanus Information/Oceanus Geography.geojson', 'r') as f:
    geojson = json.load(f)

print(f"Total features: {len(geojson['features'])}")
print()

for feat in geojson['features']:
    props = feat['properties']
    name = props.get('Name','')
    kind = props.get('*Kind','')
    geom_type = feat['geometry']['type']
    if geom_type == 'Point':
        coords = feat['geometry']['coordinates']
        print(f"{name} ({kind}): POINT ({coords[0]:.4f}, {coords[1]:.4f})")
    elif geom_type == 'Polygon':
        coords = feat['geometry']['coordinates'][0]
        lats = [c[1] for c in coords]
        lons = [c[0] for c in coords]
        print(f"{name} ({kind}): POLYGON centroid=({sum(lats)/len(lats):.4f}, {sum(lons)/len(lons):.4f}), {len(coords)} vertices")
    elif geom_type == 'MultiPolygon':
        print(f"{name} ({kind}): MULTIPOLYGON with {len(feat['geometry']['coordinates'])} parts")
    else:
        print(f"{name} ({kind}): {geom_type}")
