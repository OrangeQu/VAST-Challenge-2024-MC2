#!/usr/bin/env python3
"""
VAST Challenge 2024 MC2 - Data Preprocessing Script
Transforms the knowledge graph JSON into visualization-friendly formats.
"""

import json
from collections import defaultdict, Counter
import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)  # Go up from scripts/ to MC2/

# ============================================================
# 1. LOAD RAW DATA
# ============================================================
print("Loading mc2.json...")
raw_data_path = os.path.join(PROJECT_DIR, 'mc2.json')
with open(raw_data_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

nodes = data['nodes']
links = data['links']

# Build lookup dictionaries
node_by_id = {}
for n in nodes:
    node_by_id[n['id']] = n

# ============================================================
# 2. EXTRACT VESSELS
# ============================================================
print("Extracting vessels...")
vessels = []
vessel_ids = set()
for n in nodes:
    if 'Vessel' in n.get('type', ''):
        vessels.append(n)
        vessel_ids.add(n['id'])

print(f"  Found {len(vessels)} vessels")

# ============================================================
# 3. EXTRACT LOCATIONS
# ============================================================
print("Extracting locations...")
locations = {}
for n in nodes:
    if 'Location' in n.get('type', ''):
        locations[n['id']] = n

# City names mapping
city_names = {
    'City of Haacklee': 'Haacklee',
    'City of Lomark': 'Lomark',
    'City of Himark': 'Himark',
    'City of Paackland': 'Paackland',
    'City of South Paackland': 'South Paackland',
    'City of Port Grove': 'Port Grove'
}

# ============================================================
# 4. EXTRACT FISH TYPES
# ============================================================
print("Extracting fish types...")
fish_types = {}
for n in nodes:
    if 'Commodity.Fish' in n.get('type', ''):
        fish_types[n['id']] = n
        print(f"  Fish: {n.get('name', n['id'])} -> id: {n['id']}")

# ============================================================
# 5. EXTRACT DELIVERY REPORTS
# ============================================================
print("Extracting delivery reports...")
delivery_reports = []
for n in nodes:
    if 'DeliveryReport' in n.get('type', ''):
        delivery_reports.append(n)
print(f"  Found {len(delivery_reports)} delivery reports")

# ============================================================
# 6. BUILD VESSEL MOVEMENT DATA (from TransponderPings)
# ============================================================
print("Building vessel movement data...")
vessel_movements = defaultdict(list)  # vessel_id -> list of pings
for l in links:
    if 'TransponderPing' in l.get('type', ''):
        vessel_id = l['target']
        location_name = l['source']
        ping = {
            'time': l['time'],
            'dwell': l.get('dwell', 0),
            'location': location_name,
            'source': l.get('_raw_source', ''),
            'date_added': l.get('_date_added', '')
        }
        vessel_movements[vessel_id].append(ping)

print(f"  Built movement data for {len(vessel_movements)} vessels")

# ============================================================
# 7. BUILD HARBOR REPORT DATA
# ============================================================
print("Building harbor report data...")
harbor_reports = defaultdict(list)  # vessel_id -> list of reports
for l in links:
    if 'HarborReport' in l.get('type', ''):
        vessel_id = l['source']
        report = {
            'date': l['date'],
            'location': l['target'],
            'data_author': l.get('data_author', ''),
            'aphorism': l.get('aphorism', ''),
            'holiday_greeting': l.get('holiday_greeting', ''),
            'wisdom': l.get('wisdom', ''),
            'saying_of_the_sea': l.get('saying of the sea', '')
        }
        harbor_reports[vessel_id].append(report)

print(f"  Built harbor report data for {len(harbor_reports)} vessels")

# ============================================================
# 8. BUILD TRANSACTION DATA (linking delivery reports to fish)
# ============================================================
print("Building transaction data...")
transactions = []
for l in links:
    if 'Transaction' in l.get('type', ''):
        transactions.append({
            'date': l['date'],
            'delivery_report_id': l['source'],
            'fish_id': l['target'],
            'source': l.get('_raw_source', '')
        })
print(f"  Found {len(transactions)} transactions")

# Link delivery reports to fish via transactions
delivery_to_fish = {}
for t in transactions:
    delivery_to_fish[t['delivery_report_id']] = t['fish_id']

# ============================================================
# 9. COMPUTE VESSEL BEHAVIOR FEATURES
# ============================================================
print("Computing vessel behavior features...")

# Identify protected areas
protected_areas = {'Ghoti Preserve', 'Nemo Reef', 'Don Limpet Preserve'}
fishing_grounds = {'Cod Table', 'Wrasse Beds', 'Tuna Shelf'}
all_regions = protected_areas | fishing_grounds

# Identify cities
cities = {'City of Haacklee', 'City of Lomark', 'City of Himark', 
          'City of Paackland', 'City of South Paackland', 'City of Port Grove'}

vessel_features = {}
for v in vessels:
    vid = v['id']
    pings = vessel_movements.get(vid, [])
    
    if not pings:
        continue
    
    # Parse times
    times = []
    for p in pings:
        try:
            t = p['time']
            times.append(t)
        except:
            pass
    
    if not times:
        continue
    
    # Count visits to different location types
    location_counts = Counter()
    region_visits = Counter()
    city_visits = Counter()
    night_visits = 0
    total_visits = len(pings)
    
    for p in pings:
        loc = p['location']
        location_counts[loc] += 1
        
        if loc in all_regions:
            region_visits[loc] += 1
        
        if loc in cities:
            city_visits[loc] += 1
        
        # Check if it's night time (rough heuristic: between 18:00 and 06:00)
        try:
            time_str = p['time']
            if 'T' in time_str:
                hour = int(time_str.split('T')[1].split(':')[0])
                if hour < 6 or hour >= 18:
                    night_visits += 1
        except:
            pass
    
    # Compute features
    protected_area_visits = sum(region_visits.get(pa, 0) for pa in protected_areas)
    fishing_ground_visits = sum(region_visits.get(fg, 0) for fg in fishing_grounds)
    night_ratio = night_visits / total_visits if total_visits > 0 else 0
    
    # Time span
    times_sorted = sorted(times)
    first_time = times_sorted[0]
    last_time = times_sorted[-1]
    
    # Unique locations visited
    unique_locations = len(location_counts)
    
    # Average dwell time
    dwells = [p['dwell'] for p in pings if p['dwell']]
    avg_dwell = sum(dwells) / len(dwells) if dwells else 0
    
    vessel_features[vid] = {
        'vessel_id': vid,
        'vessel_name': v.get('Name', vid),
        'company': v.get('company', 'Unknown'),
        'vessel_type': v.get('type', 'Unknown'),
        'flag_country': v.get('flag_country', 'Unknown'),
        'length_overall': v.get('length_overall', 0),
        'tonnage': v.get('tonnage', 0),
        'total_pings': total_visits,
        'unique_locations': unique_locations,
        'protected_area_visits': protected_area_visits,
        'fishing_ground_visits': fishing_ground_visits,
        'night_visits': night_visits,
        'night_ratio': round(night_ratio, 4),
        'avg_dwell_hours': round(avg_dwell / 3600, 2) if avg_dwell else 0,
        'first_seen': first_time,
        'last_seen': last_time,
        'region_visits': dict(region_visits),
        'city_visits': dict(city_visits)
    }

print(f"  Computed features for {len(vessel_features)} vessels")

# ============================================================
# 10. LINK DELIVERY REPORTS TO POSSIBLE VESSELS
# ============================================================
print("Linking delivery reports to possible vessels...")

# For each delivery report, find which vessels were at the same port around the same time
# First, build a mapping from location to vessels at different times
location_vessel_times = defaultdict(list)  # location -> [(time, vessel_id)]
for vid, pings in vessel_movements.items():
    for p in pings:
        loc = p['location']
        if loc in cities:
            location_vessel_times[loc].append({
                'time': p['time'],
                'vessel_id': vid,
                'vessel_name': node_by_id.get(vid, {}).get('Name', vid),
                'company': node_by_id.get(vid, {}).get('company', 'Unknown')
            })

# For each delivery report, find the source location
# Delivery reports have _raw_source like "Tuna Shelf/egress report"
# We need to figure out which port they came from
# The transaction links delivery report -> fish, but we need location info
# Let's look at the _raw_source field

delivery_locations = {}
for dr in delivery_reports:
    raw_source = dr.get('_raw_source', '')
    # Extract location from raw_source
    loc = None
    for city in ['Haacklee', 'Lomark', 'Himark', 'Paackland', 'South Paackland', 'Port Grove']:
        if city in raw_source:
            loc = f'City of {city}'
            break
    # Also check for fishing grounds
    for fg in fishing_grounds:
        if fg in raw_source:
            loc = fg
            break
    delivery_locations[dr['id']] = {
        'raw_source': raw_source,
        'inferred_location': loc,
        'date': dr.get('date', ''),
        'qty_tons': dr.get('qty_tons', 0)
    }

# ============================================================
# 11. FIND SOUTHSEAFOOD VESSEL DATA
# ============================================================
print("Extracting SouthSeafood specific data...")
southseafood_vessels = []
for v in vessels:
    if v.get('company') == 'SouthSeafood Express Corp':
        southseafood_vessels.append(v)
        print(f"  {v.get('Name')} ({v['id']})")

# Get SouthSeafood movement data
southseafood_movements = {}
for sv in southseafood_vessels:
    vid = sv['id']
    southseafood_movements[vid] = {
        'vessel_info': sv,
        'pings': vessel_movements.get(vid, []),
        'features': vessel_features.get(vid, {})
    }

# ============================================================
# 12. COMPUTE SIMILARITY TO SOUTHSEAFOOD
# ============================================================
print("Computing vessel similarity to SouthSeafood...")

# Get SouthSeafood vessel IDs
ss_ids = [sv['id'] for sv in southseafood_vessels]

# Compute similarity based on behavior features
similarity_scores = []
for vid, feat in vessel_features.items():
    if vid in ss_ids:
        continue
    
    # Compare with each SouthSeafood vessel
    for ss_id in ss_ids:
        ss_feat = vessel_features.get(ss_id, {})
        if not ss_feat:
            continue
        
        # Simple similarity based on key features
        score = 0
        # Protected area visits similarity
        pa_diff = abs(feat.get('protected_area_visits', 0) - ss_feat.get('protected_area_visits', 0))
        score += max(0, 1 - pa_diff / 100) * 0.3
        
        # Night ratio similarity
        nr_diff = abs(feat.get('night_ratio', 0) - ss_feat.get('night_ratio', 0))
        score += max(0, 1 - nr_diff) * 0.3
        
        # Fishing ground visits similarity
        fg_diff = abs(feat.get('fishing_ground_visits', 0) - ss_feat.get('fishing_ground_visits', 0))
        score += max(0, 1 - fg_diff / 100) * 0.2
        
        # Dwell time similarity
        dwell_diff = abs(feat.get('avg_dwell_hours', 0) - ss_feat.get('avg_dwell_hours', 0))
        score += max(0, 1 - dwell_diff / 24) * 0.2
        
        similarity_scores.append({
            'vessel_id': vid,
            'vessel_name': feat.get('vessel_name', vid),
            'company': feat.get('company', 'Unknown'),
            'similar_to': ss_id,
            'similar_to_name': ss_feat.get('vessel_name', ss_id),
            'similarity_score': round(score, 4),
            'features': feat
        })

# Sort by similarity score (descending)
similarity_scores.sort(key=lambda x: x['similarity_score'], reverse=True)

print(f"  Computed similarity for {len(similarity_scores)} vessel pairs")

# ============================================================
# 13. EXPORT PROCESSED DATA
# ============================================================
print("\nExporting processed data...")

output_dir = os.path.join(PROJECT_DIR, 'data')
os.makedirs(output_dir, exist_ok=True)

# Export vessel features
output = {
    'vessels': list(vessel_features.values()),
    'southseafood_vessels': [
        {
            'vessel_info': {
                'id': sv['id'],
                'name': sv.get('Name', ''),
                'type': sv.get('type', ''),
                'company': sv.get('company', ''),
                'flag_country': sv.get('flag_country', ''),
                'length_overall': sv.get('length_overall', 0),
                'tonnage': sv.get('tonnage', 0)
            },
            'pings': vessel_movements.get(sv['id'], []),
            'features': vessel_features.get(sv['id'], {})
        }
        for sv in southseafood_vessels
    ],
    'similar_vessels': similarity_scores[:50],  # Top 50 similar vessels
    'locations': [
        {
            'id': lid,
            'name': loc.get('Name', lid),
            'type': loc.get('type', ''),
            'kind': loc.get('*Kind', ''),
            'activities': loc.get('Activities', []),
            'fish_species_present': loc.get('fish_species_present', [])
        }
        for lid, loc in locations.items()
    ],
    'fish_types': [
        {
            'id': fid,
            'name': f.get('name', fid)
        }
        for fid, f in fish_types.items()
    ],
    'delivery_reports': [
        {
            'id': dr['id'],
            'date': dr.get('date', ''),
            'qty_tons': dr.get('qty_tons', 0),
            'raw_source': dr.get('_raw_source', ''),
            'fish_id': delivery_to_fish.get(dr['id'], ''),
            'fish_name': fish_types.get(delivery_to_fish.get(dr['id'], ''), {}).get('name', 'Unknown')
        }
        for dr in delivery_reports
    ],
    'harbor_reports': {
        vid: reports
        for vid, reports in harbor_reports.items()
    },
    'protected_areas': list(protected_areas),
    'fishing_grounds': list(fishing_grounds),
    'cities': list(cities)
}

with open(f'{output_dir}/processed_data.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"  Exported to {output_dir}/processed_data.json")

# Export vessel movements for specific vessels (for map visualization)
# Limit to vessels with significant movement data
significant_vessels = [vid for vid, pings in vessel_movements.items() if len(pings) > 50]
movement_export = {}
for vid in significant_vessels[:100]:  # Top 100 vessels by movement count
    v = node_by_id.get(vid, {})
    movement_export[vid] = {
        'name': v.get('Name', vid),
        'company': v.get('company', 'Unknown'),
        'type': v.get('type', 'Unknown'),
        'pings': vessel_movements[vid]
    }

with open(f'{output_dir}/vessel_movements.json', 'w', encoding='utf-8') as f:
    json.dump(movement_export, f, indent=2, ensure_ascii=False)

print(f"  Exported movements for {len(movement_export)} vessels")

# Export delivery-location mapping
with open(f'{output_dir}/delivery_locations.json', 'w', encoding='utf-8') as f:
    json.dump(delivery_locations, f, indent=2, ensure_ascii=False)

print(f"  Exported delivery location mapping")

print("\nPreprocessing complete!")
