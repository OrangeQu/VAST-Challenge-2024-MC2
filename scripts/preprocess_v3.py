#!/usr/bin/env python3
"""
VAST Challenge 2024 MC2 - Advanced Data Preprocessing v3
- MinMaxScaler normalization (better for visualization)
- True t-SNE dimensionality reduction (not PCA approximation)
- Enhanced feature extraction for similarity detection
"""

import json
import math
import numpy as np
from collections import defaultdict, Counter
from sklearn.preprocessing import MinMaxScaler
from sklearn.manifold import TSNE
from sklearn.decomposition import PCA
import os
import sys
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# CONFIG - 根据你的目录结构设置路径
# ============================================================
# 获取脚本所在目录 (scripts/)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 项目根目录 (MC2/)
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
# 数据输出目录 (MC2/data/)
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'data')
# 原始数据文件路径
RAW_DATA_PATH = os.path.join(PROJECT_DIR, 'mc2.json')
# GeoJSON 文件路径
GEOJSON_PATH = os.path.join(PROJECT_DIR, 'Oceanus Information', 'Oceanus Geography.geojson')

# 创建输出目录
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 60)
print("VAST 2024 MC2 - Advanced Preprocessing v3")
print("(MinMaxScaler + True t-SNE)")
print("=" * 60)
print(f"\n脚本目录: {SCRIPT_DIR}")
print(f"项目目录: {PROJECT_DIR}")
print(f"输出目录: {OUTPUT_DIR}")
print(f"原始数据: {RAW_DATA_PATH}")
print(f"GeoJSON: {GEOJSON_PATH}")

# ============================================================
# 1. LOAD DATA
# ============================================================
print("\n[1] Loading mc2.json...")
if not os.path.exists(RAW_DATA_PATH):
    print(f"  错误: 找不到文件 {RAW_DATA_PATH}")
    print("  请确认原始数据文件位置")
    sys.exit(1)

with open(RAW_DATA_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)
nodes = data['nodes']
links = data['links']
node_by_id = {n['id']: n for n in nodes}
print(f"  Nodes: {len(nodes)}, Links: {len(links)}")

# Load GeoJSON
print("\n[2] Loading GeoJSON geography...")
if not os.path.exists(GEOJSON_PATH):
    print(f"  警告: 找不到文件 {GEOJSON_PATH}")
    print("  将使用空的地理数据")
    geojson = {'features': []}
else:
    with open(GEOJSON_PATH, 'r', encoding='utf-8') as f:
        geojson = json.load(f)

# Build location -> coordinates mapping
location_coords = {}
location_polygons = {}
for feat in geojson.get('features', []):
    name = feat['properties'].get('Name', '')
    geom = feat['geometry']
    if geom['type'] == 'Point':
        location_coords[name] = geom['coordinates']
    elif geom['type'] == 'Polygon':
        coords = geom['coordinates'][0]
        lats = [c[1] for c in coords]
        lons = [c[0] for c in coords]
        location_coords[name] = [sum(lons)/len(lons), sum(lats)/len(lats)]
        location_polygons[name] = coords

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

        # Night detection (6pm-6am)
        try:
            time_str = p['time']
            if 'T' in time_str:
                hour = int(time_str.split('T')[1].split(':')[0])
                if hour < 6 or hour >= 18:
                    night_visits += 1
        except:
            pass

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
    # 1. Entropy of location distribution
    loc_probs = [c/total_visits for c in location_counts.values()]
    entropy = -sum(p * math.log2(p) for p in loc_probs if p > 0)

    # 2. Transit speed estimate
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

    # 4. Night fishing ratio
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

    # 6. Periodic behavior
    location_times = defaultdict(list)
    for p in pings:
        location_times[p['location']].append(p['time'])

    periodic_scores = {}
    for loc, loc_times in location_times.items():
        if len(loc_times) >= 3:
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
                        periodic_scores[loc] = 1 / (1 + std_interval) if mean_interval > 0 else 0
            except:
                pass

    avg_periodicity = np.mean(list(periodic_scores.values())) if periodic_scores else 0

    # 7. Fishing intensity (number of fishing ground visits per day)
    fishing_intensity = fishing_ground_visits / days_span if days_span > 0 else 0

    # 8. Protected area intrusion frequency
    intrusion_frequency = protected_area_visits / days_span if days_span > 0 else 0

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
        'fishing_intensity': round(fishing_intensity, 4),
        'intrusion_frequency': round(intrusion_frequency, 4),
        'region_visits': dict(region_visits),
        'city_visits': dict(city_visits),
        'transitions': dict(transitions),
        'location_sequence': location_sequence,
    }

print(f"  Features computed for {len(vessel_features)} vessels")

# ============================================================
# 8. MinMaxScaler + True t-SNE
# ============================================================
print("\n[8] Computing MinMaxScaler normalization and true t-SNE...")

# Feature matrix for t-SNE (12 features for richer behavioral fingerprint)
feature_names = [
    'total_pings', 'unique_locations', 'protected_area_visits',
    'fishing_ground_visits', 'night_ratio', 'avg_dwell_hours',
    'entropy', 'locations_per_day', 'protected_dwell_ratio',
    'night_fishing_ratio', 'avg_periodicity', 'fishing_intensity'
]

vessel_ids_list = sorted(vessel_features.keys())
n_vessels = len(vessel_ids_list)
print(f"  Encoding {n_vessels} vessels with {len(feature_names)} features")

feature_matrix = []
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
        feat.get('fishing_intensity', 0),
    ]
    feature_matrix.append(row)

feature_matrix = np.array(feature_matrix)

# MinMaxScaler normalization (better for visualization)
print("  Applying MinMaxScaler normalization...")
scaler = MinMaxScaler()
feature_matrix_norm = scaler.fit_transform(feature_matrix)

# Save scaler params for reference
scaler_params = {
    'min': scaler.min_.tolist(),
    'scale': scaler.scale_.tolist(),
    'feature_names': feature_names
}

# True t-SNE (not PCA approximation)
print(f"  Running true t-SNE on {n_vessels} vessels...")
print("  perplexity=15, n_iter=1000 (optimized for vessel behavior clustering)")
tsne = TSNE(n_components=2, perplexity=15, random_state=42, max_iter=1000, init='pca')
tsne_results = tsne.fit_transform(feature_matrix_norm)

# Store t-SNE coordinates in vessel features
for i, vid in enumerate(vessel_ids_list):
    vessel_features[vid]['tsne_x'] = float(tsne_results[i, 0])
    vessel_features[vid]['tsne_y'] = float(tsne_results[i, 1])

print(f"  t-SNE complete. Output range: x=[{tsne_results[:,0].min():.2f}, {tsne_results[:,0].max():.2f}], y=[{tsne_results[:,1].min():.2f}, {tsne_results[:,1].max():.2f}]")

# Also compute PCA for comparison (optional)
print("  Computing PCA for reference...")
pca = PCA(n_components=2)
pca_results = pca.fit_transform(feature_matrix_norm)
for i, vid in enumerate(vessel_ids_list):
    vessel_features[vid]['pca_x'] = float(pca_results[i, 0])
    vessel_features[vid]['pca_y'] = float(pca_results[i, 1])

# ============================================================
# 9. COMPUTE ENHANCED SIMILARITY MATRIX
# ============================================================
print("\n[9] Computing enhanced vessel similarity matrix...")

# Find SouthSeafood vessels
ss_vessel_ids = [v['id'] for v in vessels if v.get('company') == 'SouthSeafood Express Corp']
print(f"  SouthSeafood vessels: {ss_vessel_ids}")

# Enhanced weights for similarity calculation
similarity_weights = {
    'protected_area_visits': 0.15,
    'night_ratio': 0.15,
    'fishing_ground_visits': 0.10,
    'avg_dwell_hours': 0.10,
    'entropy': 0.08,
    'protected_dwell_ratio': 0.12,
    'night_fishing_ratio': 0.12,
    'avg_periodicity': 0.06,
    'fishing_intensity': 0.06,
    'intrusion_frequency': 0.06,
}

# Compute similarity scores using normalized values
similarity_scores = []
for vid in vessel_ids_list:
    if vid in ss_vessel_ids:
        continue

    feat = vessel_features[vid]
    for ss_id in ss_vessel_ids:
        ss_feat = vessel_features.get(ss_id, {})
        if not ss_feat:
            continue

        # Use normalized feature values for similarity calculation
        score = 0.0
        for feat_name, weight in similarity_weights.items():
            v1 = feat.get(feat_name, 0)
            v2 = ss_feat.get(feat_name, 0)
            
            # Get min/max for this feature across all vessels for normalization
            all_vals = [vessel_features[v].get(feat_name, 0) for v in vessel_ids_list]
            v_min = min(all_vals)
            v_max = max(all_vals)
            v_range = v_max - v_min if v_max > v_min else 1
            
            # Normalize to [0, 1]
            v1_norm = (v1 - v_min) / v_range
            v2_norm = (v2 - v_min) / v_range
            
            # Similarity = 1 - normalized distance
            diff = abs(v1_norm - v2_norm)
            sim = max(0, 1 - diff)
            score += sim * weight

        similarity_scores.append({
            'vessel_id': vid,
            'vessel_name': feat.get('vessel_name', vid),
            'company': feat.get('company', 'Unknown'),
            'similar_to': ss_id,
            'similar_to_name': ss_feat.get('vessel_name', ss_id),
            'similarity_score': round(score, 4),
            'feature_contributions': {
                name: round(weight * (1 - min(1, abs(feat.get(name, 0) - ss_feat.get(name, 0)) / max(1, ss_feat.get(name, 1)))), 4)
                for name, weight in similarity_weights.items()
            }
        })

# Sort by similarity score
similarity_scores.sort(key=lambda x: x['similarity_score'], reverse=True)
print(f"  Computed {len(similarity_scores)} similarity pairs")
if similarity_scores:
    print(f"  Top similar vessel: {similarity_scores[0]['vessel_name']} ({similarity_scores[0]['similarity_score']*100:.1f}%)")

# ============================================================
# 10. BUILD DELIVERY-VESSEL LINKAGE
# ============================================================
print("\n[10] Building delivery-vessel linkage...")

port_visits = defaultdict(list)
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

delivery_vessel_links = []
for dr in delivery_reports:
    dr_id = dr['id']
    dr_date = dr.get('date', '')[:10] if dr.get('date') else ''
    dr_fish_id = delivery_to_fish.get(dr_id, '')
    dr_fish_name = fish_types.get(dr_fish_id, {}).get('name', 'Unknown')
    dr_location = delivery_to_city.get(dr_id, None)

    if dr_location and dr_date:
        candidates = []
        for visit in port_visits.get(dr_location, []):
            try:
                visit_date = visit['date'][:10] if 'T' in visit['date'] else visit['date']
                date_diff = abs((np.datetime64(dr_date) - np.datetime64(visit_date)).astype(int))
                if date_diff <= 3:
                    candidates.append({**visit, 'date_diff': date_diff})
            except:
                pass

        candidates.sort(key=lambda x: x['date_diff'])

        delivery_vessel_links.append({
            'delivery_id': dr_id,
            'date': dr_date,
            'location': dr_location,
            'fish_id': dr_fish_id,
            'fish_name': dr_fish_name,
            'qty_tons': dr.get('qty_tons', 0),
            'candidate_vessels': candidates[:5],
            'best_match_vessel': candidates[0] if candidates else None
        })

print(f"  Linked {len(delivery_vessel_links)} deliveries to vessels")

# ============================================================
# 11. COMPUTE CLUSTER DENSITY (for contour visualization)
# ============================================================
print("\n[11] Computing cluster density for visualization...")

contour_data = None
try:
    from scipy.stats import gaussian_kde
    
    # Compute kernel density estimate for t-SNE coordinates
    tsne_coords = np.array([[vessel_features[vid]['tsne_x'], vessel_features[vid]['tsne_y']] for vid in vessel_ids_list])
    kde = gaussian_kde(tsne_coords.T)
    
    # Generate grid for contour
    x_min, x_max = tsne_coords[:, 0].min() - 1, tsne_coords[:, 0].max() + 1
    y_min, y_max = tsne_coords[:, 1].min() - 1, tsne_coords[:, 1].max() + 1
    grid_x, grid_y = np.mgrid[x_min:x_max:50j, y_min:y_max:50j]
    grid_coords = np.vstack([grid_x.ravel(), grid_y.ravel()])
    density = kde(grid_coords).reshape(grid_x.shape)
    
    contour_data = {
        'x': grid_x.tolist(),
        'y': grid_y.tolist(),
        'density': density.tolist(),
        'levels': np.percentile(density, [10, 25, 50, 75, 90]).tolist()
    }
    print("  Density contour computed successfully")
except Exception as e:
    print(f"  Warning: Could not compute density: {e}")

# ============================================================
# 12. EXPORT ALL DATA
# ============================================================
print("\n[12] Exporting processed data v3...")

# Helper to convert numpy types
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
    return obj

# Build SouthSeafood vessels data
southseafood_vessels = []
for sv in vessels:
    if sv.get('company') == 'SouthSeafood Express Corp':
        vid = sv['id']
        southseafood_vessels.append({
            'vessel_info': {
                'id': sv['id'],
                'name': sv.get('Name', ''),
                'type': sv.get('type', ''),
                'company': sv.get('company', ''),
                'flag_country': sv.get('flag_country', ''),
                'length_overall': sv.get('length_overall', 0),
                'tonnage': sv.get('tonnage', 0)
            },
            'pings': vessel_movements.get(vid, []),
            'features': vessel_features.get(vid, {})
        })

# Build main output
output = {
    'version': 'v3',
    'description': 'MinMaxScaler + True t-SNE. Enhanced features for behavioral similarity.',
    'vessels': list(vessel_features.values()),
    'southseafood_vessels': southseafood_vessels,
    'similar_vessels': similarity_scores[:150],
    'similarity_weights': similarity_weights,
    'feature_names': feature_names,
    'scaler_params': scaler_params,
    'tsne_contour': contour_data,
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
        {'id': fid, 'name': f.get('name', fid)}
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
    'location_coords': location_coords,
    'location_polygons': {k: v for k, v in location_polygons.items()},
}

# Convert numpy types
output = convert_to_native(output)

# Save to new file (independent from v2)
output_path = os.path.join(OUTPUT_DIR, 'processed_data_v3.json')
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"  Exported to {output_path}")
if os.path.exists(output_path):
    print(f"  File size: {os.path.getsize(output_path) / 1024 / 1024:.2f} MB")

# ============================================================
# 13. EXPORT VESSEL MOVEMENTS FOR MAP
# ============================================================
print("\n[13] Exporting vessel movements for map...")

vessel_ping_counts = [(vid, len(pings)) for vid, pings in vessel_movements.items()]
vessel_ping_counts.sort(key=lambda x: -x[1])

movement_export = {}
for vid, _ in vessel_ping_counts[:100]:
    v = node_by_id.get(vid, {})
    pings = vessel_movements[vid]
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
    
    vessel_info = vessel_features.get(vid, {})
    
    movement_export[vid] = {
        'name': v.get('Name', vid),
        'company': v.get('company', 'Unknown'),
        'type': v.get('type', 'Unknown'),
        'tsne_x': vessel_info.get('tsne_x', None),
        'tsne_y': vessel_info.get('tsne_y', None),
        'pings': ping_coords
    }

movement_path = os.path.join(OUTPUT_DIR, 'vessel_movements_v3.json')
with open(movement_path, 'w', encoding='utf-8') as f:
    json.dump(movement_export, f, indent=2, ensure_ascii=False)
print(f"  Exported movements for {len(movement_export)} vessels to {movement_path}")

# ============================================================
# 14. EXPORT GEOGRAPHY DATA
# ============================================================
print("\n[14] Exporting geography data...")

geography_export = {
    'islands': [],
    'fishing_grounds': [],
    'protected_areas': [],
    'cities': [],
    'buoys': []
}

for feat in geojson.get('features', []):
    name = feat['properties'].get('Name', '')
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

geo_path = os.path.join(OUTPUT_DIR, 'geography_v3.json')
with open(geo_path, 'w', encoding='utf-8') as f:
    json.dump(geography_export, f, indent=2, ensure_ascii=False)
print(f"  Exported geography data to {geo_path}")

# ============================================================
# 15. SUMMARY STATISTICS
# ============================================================
print("\n[15] Summary Statistics")
print("=" * 60)

# Calculate summary for SouthSeafood vessels
ss_vessels_data = [vessel_features[vid] for vid in ss_vessel_ids if vid in vessel_features]
if ss_vessels_data:
    print("\nSouthSeafood Vessel Summary:")
    for v in ss_vessels_data:
        print(f"  - {v['vessel_name']}: night_ratio={v['night_ratio']*100:.1f}%, "
              f"night_fishing_ratio={v['night_fishing_ratio']*100:.1f}%, "
              f"avg_dwell={v['avg_dwell_hours']:.1f}h, "
              f"entropy={v['entropy']:.2f}")

# Top similar vessels
print("\nTop 10 Similar Vessels to SouthSeafood:")
for i, sim in enumerate(similarity_scores[:10]):
    print(f"  {i+1}. {sim['vessel_name']} ({sim['company']}) - {sim['similarity_score']*100:.1f}%")

print("\n" + "=" * 60)
print("Preprocessing v3 complete!")
print(f"Data files saved to: {OUTPUT_DIR}")
print("  - processed_data_v3.json (main data with t-SNE)")
print("  - vessel_movements_v3.json (movement data for maps)")
print("  - geography_v3.json (geography for maps)")
print("=" * 60)