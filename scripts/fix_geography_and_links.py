"""
修复 geography.json 和 delivery_vessel_links
1. geography.json: 从原始 GeoJSON 读取真实多边形坐标
2. processed_data.json: 基于时间相近性匹配 delivery_reports 与 harbor_reports
"""
import json
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# 1. 从原始 GeoJSON 读取真实多边形坐标
# ============================================================
geo_raw_path = os.path.join(BASE_DIR, 'data', 'raw', 'Oceanus Information', 'Oceanus Geography.geojson')
with open(geo_raw_path, 'r', encoding='utf-8') as f:
    geo_raw = json.load(f)

features = geo_raw.get('features', [])
print(f"原始 GeoJSON 共 {len(features)} 个要素")

protected_areas = []
fishing_grounds = []
cities = []
islands = []

for f in features:
    props = f.get('properties', {})
    name = props.get('Name', 'N/A')
    kind = props.get('*Kind', '')
    geometry = f.get('geometry', {})
    geom_type = geometry.get('type', '')
    coordinates = geometry.get('coordinates', [])
    
    entry = {
        'name': name,
        'coordinates': coordinates,
        'type': geom_type
    }
    
    kind_lower = kind.lower()
    
    if kind_lower == 'ecological preserve':
        protected_areas.append(entry)
        print(f"  保护区: {name} ({len(coordinates[0])} 个顶点)")
    elif kind_lower == 'fishing ground':
        fishing_grounds.append(entry)
        print(f"  渔场: {name} ({len(coordinates[0])} 个顶点)")
    elif kind_lower == 'island':
        islands.append(entry)
        print(f"  岛屿: {name} ({len(coordinates[0])} 个顶点)")
    elif kind_lower == 'city':
        if geom_type == 'Point':
            cities.append({'name': name, 'coordinates': coordinates})
        else:
            coords = coordinates[0] if coordinates else []
            if coords:
                lon = sum(c[0] for c in coords) / len(coords)
                lat = sum(c[1] for c in coords) / len(coords)
                cities.append({'name': name, 'coordinates': [lon, lat]})
        print(f"  城市: {name}")
    else:
        print(f"  其他: {name} (kind={kind})")

# 读取 processed_data.json
proc_path = os.path.join(BASE_DIR, 'data', 'processed', 'processed_data.json')
with open(proc_path, 'r', encoding='utf-8') as f:
    proc = json.load(f)

location_coords = proc.get('location_coords', {})

# 写入 geography.json
geo_path = os.path.join(BASE_DIR, 'data', 'processed', 'geography.json')
new_geo = {
    'protected_areas': protected_areas,
    'fishing_grounds': fishing_grounds,
    'cities': cities,
    'islands': islands,
    'location_coords': location_coords
}
with open(geo_path, 'w', encoding='utf-8') as f:
    json.dump(new_geo, f, indent=2, ensure_ascii=False)

print(f"\n✅ geography.json 修复完成")
print(f"   protected_areas: {len(protected_areas)} 个")
print(f"   fishing_grounds: {len(fishing_grounds)} 个")
print(f"   cities: {len(cities)} 个")
print(f"   islands: {len(islands)} 个")

# ============================================================
# 2. 基于时间相近性匹配 delivery_reports 与 harbor_reports
# ============================================================
print(f"\n{'='*60}")
print(f"生成 delivery_vessel_links（基于时间相近性匹配）")
print(f"{'='*60}")

delivery_reports = proc.get('delivery_reports', [])
harbor_reports = proc.get('harbor_reports', {})
vessels = proc.get('vessels', [])

# 构建 vessel_id -> vessel_name 映射
vessel_id_to_name = {v['vessel_id']: v['vessel_name'] for v in vessels}
vessel_name_to_id = {v['vessel_name']: v['vessel_id'] for v in vessels}

# 构建 port -> [(date, vessel_name, vessel_id)] 索引
# 用于快速查找在特定港口附近日期到访的船舶
from collections import defaultdict

port_date_index = defaultdict(list)  # port -> [(date_str, vessel_name, vessel_id)]
for vid, visits in harbor_reports.items():
    vname = vessel_id_to_name.get(vid, vid)
    seen = set()  # 去重：同一天同一船同一港口只保留一条
    for visit in visits:
        port = visit.get('port', '')
        date = visit.get('date', '')
        if port and date:
            key = (date, vid)
            if key not in seen:
                seen.add(key)
                port_date_index[port].append((date, vname, vid))

# 对每个港口的到访记录按日期排序
for port in port_date_index:
    port_date_index[port].sort(key=lambda x: x[0])


def parse_date(d):
    """解析日期字符串为 datetime 对象"""
    if not d:
        return None
    try:
        return datetime.strptime(d, '%Y-%m-%d')
    except:
        return None

def find_closest_vessels(port, target_date_str, max_candidates=20, max_days=30):

    """
    在指定港口找到与目标日期最接近的船舶到访记录
    返回按时间差排序的候选列表
    """
    target = parse_date(target_date_str)
    if not target or port not in port_date_index:
        return []
    
    candidates = []
    for date_str, vname, vid in port_date_index[port]:
        d = parse_date(date_str)
        if d:
            diff = abs((d - target).days)
            if diff <= max_days:
                candidates.append({
                    'vessel_name': vname,
                    'vessel_id': vid,
                    'date': date_str,
                    'date_diff': diff
                })
    
    # 按时间差排序，取前 N 个
    candidates.sort(key=lambda x: x['date_diff'])
    return candidates[:max_candidates]

# 为每条 delivery_report 匹配船舶
delivery_vessel_links = []
matched_count = 0
unmatched_count = 0

for report in delivery_reports:
    city_id = report.get('city_id', '')
    date = report.get('date', '')
    fish_name = report.get('fish_name', '')
    qty_tons = report.get('qty_tons', 0)
    
    candidates = find_closest_vessels(city_id, date)
    
    best_match = candidates[0] if candidates else None
    
    link = {
        'id': report.get('id', ''),
        'date': date,
        'port': city_id,
        'fish_name': fish_name,
        'qty_tons': qty_tons,
        'best_match_vessel': best_match,
        'candidate_vessels': candidates,
        'vessel_name': best_match['vessel_name'] if best_match else '',
        'company': ''
    }
    delivery_vessel_links.append(link)
    
    if best_match:
        matched_count += 1
    else:
        unmatched_count += 1

# 更新 processed_data.json
proc['delivery_vessel_links'] = delivery_vessel_links

with open(proc_path, 'w', encoding='utf-8') as f:
    json.dump(proc, f, indent=2, ensure_ascii=False)

print(f"\n✅ delivery_vessel_links 生成完成")
print(f"   总 delivery_reports: {len(delivery_reports)}")
print(f"   匹配到船舶: {matched_count}")
print(f"   未匹配: {unmatched_count}")
print(f"   匹配率: {matched_count/len(delivery_reports)*100:.1f}%")

# 验证 Snapper Snatcher
print(f"\n📊 验证 Snapper Snatcher:")
n = 'Snapper Snatcher'
links_for_snapper = [l for l in delivery_vessel_links 
                     if l.get('vessel_name') == n 
                     or (l.get('best_match_vessel') and l['best_match_vessel'].get('vessel_name') == n)
                     or any(c.get('vessel_name') == n for c in l.get('candidate_vessels', []))]
print(f"   关联的 delivery 记录数: {len(links_for_snapper)}")
if links_for_snapper:
    for l in links_for_snapper[:5]:
        bm = l.get('best_match_vessel', {})
        print(f"   port={l['port']}, date={l['date']}, fish={l['fish_name']}, best={bm.get('vessel_name','N/A')}, diff={bm.get('date_diff','N/A')}天")

# 验证 Roach Robber
print(f"\n📊 验证 Roach Robber:")
n = 'Roach Robber'
links_for_rr = [l for l in delivery_vessel_links 
                if l.get('vessel_name') == n 
                or (l.get('best_match_vessel') and l['best_match_vessel'].get('vessel_name') == n)
                or any(c.get('vessel_name') == n for c in l.get('candidate_vessels', []))]
print(f"   关联的 delivery 记录数: {len(links_for_rr)}")
if links_for_rr:
    for l in links_for_rr[:5]:
        bm = l.get('best_match_vessel', {})
        print(f"   port={l['port']}, date={l['date']}, fish={l['fish_name']}, best={bm.get('vessel_name','N/A')}, diff={bm.get('date_diff','N/A')}天")

# 统计每艘船关联的 delivery 记录数（包括 candidate_vessels）
print(f"\n📊 每艘船关联的 delivery 记录数分布:")
vessel_link_count = defaultdict(int)
vessels_in_candidates = set()
for l in delivery_vessel_links:
    # 统计 best_match
    bm = l.get('best_match_vessel')
    if bm and bm.get('vessel_name'):
        vessel_link_count[bm['vessel_name']] += 1
        vessels_in_candidates.add(bm['vessel_name'])
    # 统计 candidates 中的船
    for c in l.get('candidate_vessels', []):
        if c.get('vessel_name'):
            vessels_in_candidates.add(c['vessel_name'])

# 按记录数排序
sorted_vessels = sorted(vessel_link_count.items(), key=lambda x: -x[1])
print(f"   有 best_match 的船: {len(sorted_vessels)} 艘")
print(f"   在 candidates 中的船: {len(vessels_in_candidates)} 艘")
print(f"   前 10 艘:")
for vn, cnt in sorted_vessels[:10]:
    print(f"     {vn:30s}: {cnt} 条")
print(f"   后 10 艘:")
for vn, cnt in sorted_vessels[-10:]:
    print(f"     {vn:30s}: {cnt} 条")

# 统计无关联的船（不在任何 candidates 中）
vessels_without_links = [v for v in vessels if v['vessel_name'] not in vessels_in_candidates]
print(f"\n   不在任何 candidates 中的船: {len(vessels_without_links)} 艘")
if vessels_without_links:
    for v in vessels_without_links[:10]:
        print(f"     {v['vessel_name']:30s} (company={v.get('company','N/A')})")


