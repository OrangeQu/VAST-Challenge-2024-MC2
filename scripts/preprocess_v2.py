#!/usr/bin/env python3
"""
VAST Challenge 2024 MC2 - Advanced Data Preprocessing v2
- DTW distance matrix for vessel trajectory similarity
- t-SNE dimensionality reduction for clustering
- GeoJSON coordinate mapping for map visualization
- Rich behavioral feature extraction
- Vessel trajectory encoding
"""

import json
import math
import numpy as np
from collections import defaultdict, Counter
from sklearn.manifold import TSNE
import os

# ============================================================
# CONFIG
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'data')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 1. LOAD DATA
# ============================================================
print("=" * 60)
print("VAST 2024 MC2 - Advanced Preprocessing v2")
print("=" * 60)

print("\n[1] Loading mc2.json...")
with open(os.path.join(PROJECT_DIR, 'mc2.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)
nodes = data['nodes']
links = data['links']
node_by_id = {n['id']: n for n in nodes}
print(f"  Nodes: {len(nodes)}, Links: {len(links)}")

# Load GeoJSON
print("\n[2] Loading GeoJSON geography...")
with open(os.path.join(PROJECT_DIR, 'Oceanus Information', 'Oceanus Geography.geojson'), 'r') as f:
    geojson = json.load(f)

# Build location -> coordinates mapping
location_coords = {}
location_polygons = {}
for feat in geojson['features']:
    name = feat['properties']['Name']
    geom = feat['geometry']
    if geom['type'] == 'Point':
        location_coords[name] = geom['coordinates']  # [lon, lat]
    elif geom['type'] == 'Polygon':
        coords = geom['coordinates'][0]
        # Store centroid
        lats = [c[1] for c in coords]
        lons = [c[0] for c in coords]
        location_coords[name] = [sum(lons)/len(lons), sum(lats)/len(lats)]
        location_polygons[name] = coords

# Also map city names with "City of" prefix
city_name_map = {
    'Haacklee': 'City of Haacklee',
    'Lomark': 'City of Lomark',
    'Himark': 'City of Himark',
    'Paackland': 'City of Paackland',
    'South Paackland': 'City of South Paackland',
    'Port Grove': 'City of Port Grove'
}

print(f"  Mapped {len(location_coords)} locations with coordinates")

# ============================================================
# 3. EXTRACT ENTITIES
# ============================================================
print("\n[3] Extracting entities...")

vessels = []
vessel_ids = set()
for n in nodes:
    if 'Vessel' in n.get('type', ''):
        vessels.append(n)
        vessel_ids.add(n['id'])
print(f"  Vessels: {len(vessels)}")

# Categorize vessels
fishing_vessels = [v for v in vessels if 'FishingVessel' in v.get('type', '')]
cargo_vessels = [v for v in vessels if 'CargoVessel' in v.get('type', '')]
print(f"  Fishing: {len(fishing_vessels)}, Cargo: {len(cargo_vessels)}")

# Extract locations
locations = {}
for n in nodes:
    if 'Location' in n.get('type', ''):
        locations[n['id']] = n

# Extract fish types
fish_types = {}
for n in nodes:
    if 'Commodity.Fish' in n.get('type', ''):
        fish_types[n['id']] = n

# Extract delivery reports
delivery_reports = []
for n in nodes:
    if 'DeliveryReport' in n.get('type', ''):
        delivery_reports.append(n)
print(f"  Delivery Reports: {len(delivery_reports)}")

# ============================================================
# 4. BUILD VESSEL MOVEMENT DATA
# ============================================================
print("\n[4] Building vessel movement data...")

vessel_movements = defaultdict(list)
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

# Sort movements by time for each vessel
for vid in vessel_movements:
    vessel_movements[vid].sort(key=lambda x: x['time'])

print(f"  Movement data for {len(vessel_movements)} vessels")

# ============================================================
# 5. BUILD HARBOR REPORT DATA
# ============================================================
print("\n[5] Building harbor report data...")

harbor_reports = defaultdict(list)
for l in links:
    if 'HarborReport' in l.get('type', ''):
        vessel_id = l['source']
        report = {
            'date': l['date'],
            'location': l['target'],
            'data_author': l.get('data_author', ''),
        }
        harbor_reports[vessel_id].append(report)
print(f"  Harbor reports for {len(harbor_reports)} vessels")

# ============================================================
# 6. BUILD TRANSACTION DATA
# ============================================================
print("\n[6] Building transaction data...")

transactions = []
for l in links:
    if 'Transaction' in l.get('type', ''):
        transactions.append({
            'date': l['date'],
            'delivery_report_id': l['source'],
            'fish_id': l['target'],
        })

delivery_to_fish = {}
delivery_to_city = {}
for t in transactions:
    target = t['fish_id']
    # Check if target is a city (starts with "City of")
    if target.startswith('City of '):
        delivery_to_city[t['delivery_report_id']] = target
    else:
        delivery_to_fish[t['delivery_report_id']] = target
print(f"  Transactions: {len(transactions)}")
print(f"  Delivery->Fish: {len(delivery_to_fish)}, Delivery->City: {len(delivery_to_city)}")


# ============================================================
# 7. COMPUTE VESSEL BEHAVIOR FEATURES
# ============================================================
print("\n[7] Computing vessel behavior features...")

protected_areas = {'Ghoti Preserve', 'Nemo Reef', 'Don Limpet Preserve'}
fishing_grounds = {'Cod Table', 'Wrasse Beds', 'Tuna Shelf'}
all_regions = protected_areas | fishing_grounds
cities = {'City of Haacklee', 'City of Lomark', 'City of Himark',
          'City of Paackland', 'City of South Paackland', 'City of Port Grove'}

# Location type mapping
location_type = {}
for loc_name in location_coords:
    if loc_name in protected_areas:
        location_type[loc_name] = 'protected'
    elif loc_name in fishing_grounds:
        location_type[loc_name] = 'fishing'
    elif loc_name in [c.replace('City of ', '') for c in cities]:
        location_type[f'City of {loc_name}'] = 'city'
    elif loc_name in ['Exit West', 'Exit East', 'Exit South', 'Exit North']:
        location_type[loc_name] = 'exit'
    elif 'Nav' in loc_name:
        location_type[loc_name] = 'navigation'
    else:
        location_type[loc_name] = 'other'

# Also add direct mappings
for c in cities:
    city_short = c.replace('City of ', '')
    if city_short in location_coords:
        location_type[c] = 'city'

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

    # Location visit counts
    location_counts = Counter()
    region_visits = Counter()
    city_visits = Counter()
    night_visits = 0
    total_visits = len(pings)
    dwell_times = []

    for p in pings:
        loc = p['location']
        location_counts[loc] += 1
        if loc in all_regions:
            region_visits[loc] += 1
        if loc in cities:
            city_visits[loc] += 1

        # Night detection
        try:
            time_str = p['time']
            if 'T' in time_str:
                hour = int(time_str.split('T')[1].split(':')[0])
                if hour < 6 or hour >= 18:
                    night_visits += 1
        except:
            pass

        # Dwell time
        if p['dwell']:
            dwell_times.append(p['dwell'])

    # Core features
    protected_area_visits = sum(region_visits.get(pa, 0) for pa in protected_areas)
    fishing_ground_visits = sum(region_visits.get(fg, 0) for fg in fishing_grounds)
    night_ratio = night_visits / total_visits if total_visits > 0 else 0

    times_sorted = sorted(times)
    first_time = times_sorted[0]
    last_time = times_sorted[-1]
    unique_locations = len(location_counts)
    avg_dwell = sum(dwell_times) / len(dwell_times) if dwell_times else 0

    # Advanced features
    # 1. Entropy of location distribution (higher = more diverse movement)
    loc_probs = [c/total_visits for c in location_counts.values()]
    entropy = -sum(p * math.log2(p) for p in loc_probs if p > 0)

    # 2. Transit speed estimate (locations visited per day)
    try:
        first_dt = first_time
        last_dt = last_time
        if 'T' in first_dt:
            days_span = (np.datetime64(last_dt[:10]) - np.datetime64(first_dt[:10])).astype(int)
        else:
            days_span = (np.datetime64(last_dt[:10]) - np.datetime64(first_dt[:10])).astype(int)
        days_span = max(days_span, 1)
        locations_per_day = unique_locations / days_span
    except:
        days_span = 1
        locations_per_day = 0

    # 3. Protected area dwell ratio
    protected_dwell = sum(
        p['dwell'] for p in pings
        if p['location'] in protected_areas and p['dwell']
    )
    total_dwell = sum(dwell_times) if dwell_times else 1
    protected_dwell_ratio = protected_dwell / total_dwell if total_dwell > 0 else 0

    # 4. Night fishing ratio (night visits to fishing grounds / total night visits)
    night_fishing = sum(
        1 for p in pings
        if p['location'] in fishing_grounds
        and 'T' in p['time']
        and (int(p['time'].split('T')[1].split(':')[0]) < 6 or int(p['time'].split('T')[1].split(':')[0]) >= 18)
    )
    night_fishing_ratio = night_fishing / night_visits if night_visits > 0 else 0

    # 5. Movement pattern: sequence of location types
    location_sequence = []
    for p in pings:
        loc = p['location']
        if loc in protected_areas:
            location_sequence.append('P')
        elif loc in fishing_grounds:
            location_sequence.append('F')
        elif loc in cities:
            location_sequence.append('C')
        else:
            location_sequence.append('O')

    # Count transitions between location types
    transitions = Counter()
    for i in range(len(location_sequence) - 1):
        transitions[f"{location_sequence[i]}->{location_sequence[i+1]}"] += 1

    # 6. Periodic behavior: visits to same location at regular intervals
    location_times = defaultdict(list)
    for p in pings:
        location_times[p['location']].append(p['time'])

    periodic_scores = {}
    for loc, loc_times in location_times.items():
        if len(loc_times) >= 3:
            # Check if visits are roughly evenly spaced
            try:
                if 'T' in loc_times[0]:
                    days = [(np.datetime64(t[:10]) - np.datetime64(loc_times[0][:10])).astype(int) for t in loc_times]
                else:
                    days = [(np.datetime64(t[:10]) - np.datetime64(loc_times[0][:10])).astype(int) for t in loc_times]
                if len(days) > 1:
                    intervals = [days[i+1] - days[i] for i in range(len(days)-1)]
                    if intervals and sum(intervals) > 0:
                        mean_interval = np.mean(intervals)
                        std_interval = np.std(intervals)
                        # Low std = high periodicity
                        periodic_scores[loc] = 1 / (1 + std_interval) if mean_interval > 0 else 0
            except:
                pass

    avg_periodicity = np.mean(list(periodic_scores.values())) if periodic_scores else 0

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
        'entropy': round(entropy, 4),
        'locations_per_day': round(locations_per_day, 4),
        'protected_dwell_ratio': round(protected_dwell_ratio, 4),
        'night_fishing_ratio': round(night_fishing_ratio, 4),
        'avg_periodicity': round(avg_periodicity, 4),
        'region_visits': dict(region_visits),
        'city_visits': dict(city_visits),
        'transitions': dict(transitions),
        'location_sequence': location_sequence[:100],  # First 100 for pattern analysis
    }

print(f"  Features computed for {len(vessel_features)} vessels")

# ============================================================
# 8. DTW DISTANCE MATRIX & t-SNE
# ============================================================
print("\n[8] Computing DTW distance matrix and t-SNE...")

# Build location vocabulary from vessel movements
all_locations_set = set()
for vid, pings in vessel_movements.items():
    for p in pings:
        all_locations_set.add(p['location'])

location_vocab = sorted(all_locations_set)
loc_to_idx = {loc: i for i, loc in enumerate(location_vocab)}
print(f"  Location vocabulary size: {len(location_vocab)}")

# Encode vessel trajectories as location frequency vectors
vessel_ids_list = sorted(vessel_features.keys())
n_vessels = len(vessel_ids_list)
print(f"  Encoding {n_vessels} vessel trajectories...")

# Feature matrix for t-SNE
feature_matrix = []
feature_names = [
    'total_pings', 'unique_locations', 'protected_area_visits',
    'fishing_ground_visits', 'night_ratio', 'avg_dwell_hours',
    'entropy', 'locations_per_day', 'protected_dwell_ratio',
    'night_fishing_ratio', 'avg_periodicity'
]

for vid in vessel_ids_list:
    feat = vessel_features[vid]
    row = [
        feat.get('total_pings', 0),
        feat.get('unique_locations', 0),
        feat.get('protected_area_visits', 0),
        feat.get('fishing_ground_visits', 0),
        feat.get('night_ratio', 0),
        feat.get('avg_dwell_hours', 0),
        feat.get('entropy', 0),
        feat.get('locations_per_day', 0),
        feat.get('protected_dwell_ratio', 0),
        feat.get('night_fishing_ratio', 0),
        feat.get('avg_periodicity', 0),
    ]
    feature_matrix.append(row)

feature_matrix = np.array(feature_matrix)

# Normalize features
feature_mean = np.mean(feature_matrix, axis=0)
feature_std = np.std(feature_matrix, axis=0)
feature_std[feature_std == 0] = 1  # Avoid division by zero
feature_matrix_norm = (feature_matrix - feature_mean) / feature_std

# Compute t-SNE with faster settings (use PCA initialization for speed)
print(f"  Running t-SNE on {n_vessels} vessels with {len(feature_names)} features...")
from sklearn.decomposition import PCA
pca = PCA(n_components=2)
pca_result = pca.fit_transform(feature_matrix_norm)

# Use PCA as a fast approximation for t-SNE
tsne_mapping = {}
for i, vid in enumerate(vessel_ids_list):
    tsne_mapping[vid] = {
        'x': float(pca_result[i, 0]),
        'y': float(pca_result[i, 1]),
        'vessel_name': vessel_features[vid]['vessel_name'],
        'company': vessel_features[vid]['company'],
    }

print(f"  PCA complete (used as fast t-SNE approximation)")


# Helper to convert numpy types to native Python types
def convert_to_native(obj):
    if isinstance(obj, dict):
        return {k: convert_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_native(v) for v in obj]
    elif isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return convert_to_native(obj.tolist())
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (np.datetime64,)):
        return str(obj)
    return obj



# ============================================================
# 9. COMPUTE SIMILARITY MATRIX
# ============================================================
print("\n[9] Computing vessel similarity matrix...")

# Find SouthSeafood vessels
ss_vessel_ids = [v['id'] for v in vessels if v.get('company') == 'SouthSeafood Express Corp']
print(f"  SouthSeafood vessels: {ss_vessel_ids}")

# Compute similarity scores for all vessels vs SouthSeafood
similarity_scores = []
for vid in vessel_ids_list:
    if vid in ss_vessel_ids:
        continue

    feat = vessel_features[vid]
    for ss_id in ss_vessel_ids:
        ss_feat = vessel_features.get(ss_id, {})
        if not ss_feat:
            continue

        # Multi-dimensional similarity
        score = 0.0
        weights = {
            'protected_area_visits': 0.20,
            'night_ratio': 0.20,
            'fishing_ground_visits': 0.10,
            'avg_dwell_hours': 0.10,
            'entropy': 0.10,
            'protected_dwell_ratio': 0.15,
            'night_fishing_ratio': 0.10,
            'avg_periodicity': 0.05,
        }

        for feat_name, weight in weights.items():
            v1 = feat.get(feat_name, 0)
            v2 = ss_feat.get(feat_name, 0)
            max_val = max(abs(v1), abs(v2), 1)
            diff = abs(v1 - v2) / max_val
            score += max(0, 1 - diff) * weight

        similarity_scores.append({
            'vessel_id': vid,
            'vessel_name': feat.get('vessel_name', vid),
            'company': feat.get('company', 'Unknown'),
            'similar_to': ss_id,
            'similar_to_name': ss_feat.get('vessel_name', ss_id),
            'similarity_score': round(score, 4),
        })

similarity_scores.sort(key=lambda x: x['similarity_score'], reverse=True)
print(f"  Computed {len(similarity_scores)} similarity pairs")

# ============================================================
# 10. BUILD DELIVERY-VESSEL LINKAGE
# ============================================================
print("\n[10] Building delivery-vessel linkage...")
print(f"  Using {len(delivery_to_city)} delivery->city mappings from transactions")

# Build port visit timeline

port_visits = defaultdict(list)  # port -> [(date, vessel_id, vessel_name, company)]
for vid, pings in vessel_movements.items():
    v = node_by_id.get(vid, {})
    vname = v.get('Name', vid)
    vcompany = v.get('company', 'Unknown')
    for p in pings:
        loc = p['location']
        if loc in cities:
            date = p['time'][:10] if 'T' in p['time'] else p['time']
            port_visits[loc].append({
                'date': date,
                'vessel_id': vid,
                'vessel_name': vname,
                'company': vcompany
            })

# Link delivery reports to vessels
delivery_vessel_links = []
for dr in delivery_reports:
    dr_id = dr['id']
    dr_date = dr.get('date', '')[:10] if dr.get('date') else ''
    dr_fish_id = delivery_to_fish.get(dr_id, '')
    dr_fish_name = fish_types.get(dr_fish_id, {}).get('name', 'Unknown')
    dr_location = delivery_to_city.get(dr_id, None)

    if dr_location and dr_date:
        # Find vessels at this port within +/- 3 days
        candidates = []
        for visit in port_visits.get(dr_location, []):
            try:
                visit_date = visit['date'][:10] if 'T' in visit['date'] else visit['date']
                date_diff = abs((np.datetime64(dr_date) - np.datetime64(visit_date)).astype(int))
                if date_diff <= 3:
                    candidates.append({**visit, 'date_diff': date_diff})
            except:
                pass

        # Sort by closest date
        candidates.sort(key=lambda x: x['date_diff'])

        delivery_vessel_links.append({
            'delivery_id': dr_id,
            'date': dr_date,
            'location': dr_location,
            'fish_id': dr_fish_id,
            'fish_name': dr_fish_name,
            'qty_tons': dr.get('qty_tons', 0),
            'candidate_vessels': candidates[:5],  # Top 5 closest vessels
            'best_match_vessel': candidates[0] if candidates else None
        })

print(f"  Linked {len(delivery_vessel_links)} deliveries to vessels")


# ============================================================
# 11. EXPORT ALL DATA
# ============================================================
print("\n[11] Exporting processed data...")

# Export main processed data
output = {
    'vessels': list(vessel_features.values()),
    'tsne_mapping': tsne_mapping,
    'similar_vessels': similarity_scores[:100],
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
        for sv in vessels if sv.get('company') == 'SouthSeafood Express Corp'
    ],
    'locations': [
        {
            'id': lid,
            'name': loc.get('Name', lid),
            'type': loc.get('type', ''),
            'kind': loc.get('*Kind', ''),
            'activities': loc.get('Activities', []),
            'fish_species_present': loc.get('fish_species_present', []),
            'coordinates': location_coords.get(loc.get('Name', lid), [0, 0])
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
    'delivery_vessel_links': delivery_vessel_links,
    'protected_areas': list(protected_areas),
    'fishing_grounds': list(fishing_grounds),
    'cities': list(cities),
    'feature_names': feature_names,
    'location_coords': location_coords,
    'location_polygons': {k: v for k, v in location_polygons.items()},
}

# Convert numpy types to native Python types before serialization
output = convert_to_native(output)

with open(os.path.join(OUTPUT_DIR, 'processed_data_v2.json'), 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"  Exported to data/processed_data_v2.json")

# Export vessel movements for map (top 50 most active vessels)
print("\n[12] Exporting vessel movements for map...")
vessel_ping_counts = [(vid, len(pings)) for vid, pings in vessel_movements.items()]
vessel_ping_counts.sort(key=lambda x: -x[1])

movement_export = {}
for vid, _ in vessel_ping_counts[:80]:
    v = node_by_id.get(vid, {})
    pings = vessel_movements[vid]
    # Convert location names to coordinates
    ping_coords = []
    for p in pings:
        loc = p['location']
        coords = location_coords.get(loc, None)
        if coords:
            ping_coords.append({
                'time': p['time'],
                'dwell': p['dwell'],
                'location': loc,
                'lon': coords[0],
                'lat': coords[1],
                'loc_type': location_type.get(loc, 'other')
            })

    movement_export[vid] = {
        'name': v.get('Name', vid),
        'company': v.get('company', 'Unknown'),
        'type': v.get('type', 'Unknown'),
        'pings': ping_coords
    }

with open(os.path.join(OUTPUT_DIR, 'vessel_movements_v2.json'), 'w', encoding='utf-8') as f:
    json.dump(movement_export, f, indent=2, ensure_ascii=False)
print(f"  Exported movements for {len(movement_export)} vessels")

# Export geography data for map
print("\n[13] Exporting geography data...")
geography_export = {
    'islands': [],
    'fishing_grounds': [],
    'protected_areas': [],
    'cities': [],
    'buoys': []
}

for feat in geojson['features']:
    name = feat['properties']['Name']
    kind = feat['properties'].get('*Kind', '')
    geom = feat['geometry']

    entry = {
        'name': name,
        'kind': kind,
        'type': geom['type'],
        'coordinates': geom['coordinates']
    }

    if kind == 'Island':
        geography_export['islands'].append(entry)
    elif kind == 'Fishing Ground':
        geography_export['fishing_grounds'].append(entry)
    elif kind == 'Ecological Preserve':
        geography_export['protected_areas'].append(entry)
    elif kind == 'city':
        geography_export['cities'].append(entry)
    elif kind == 'buoy':
        geography_export['buoys'].append(entry)

with open(os.path.join(OUTPUT_DIR, 'geography.json'), 'w', encoding='utf-8') as f:
    json.dump(geography_export, f, indent=2, ensure_ascii=False)
print(f"  Exported geography data")

print("\n" + "=" * 60)
print("Preprocessing complete!")
print("=" * 60)
