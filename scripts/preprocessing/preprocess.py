#!/usr/bin/env python3
"""
VAST Challenge 2024 MC2 — 完整数据预处理脚本 v2
================================================
功能：
1. 数据清洗（删除元数据字段、异常检测）
2. 统一时间框架（Ping 精确时间 + HarborReport 日期）
3. 构建船舶移动指标
4. 保护区分析（点-in-多边形判断 + 位置名直接匹配）
5. 船舶相似度计算
6. 风险评分
7. 输出 processed_data.json + vessel_movements.json + geography.json

输出文件：
  - data/processed/processed_data.json  (前端主数据)
  - data/processed/vessel_movements.json (船舶轨迹)
  - data/processed/geography.json       (地理信息)
  - data/processed/preprocess_report.json (预处理报告)
"""

import json
import os
import math
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

# ============================================================
# 路径配置
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
RAW_DATA_PATH = os.path.join(PROJECT_DIR, "data", "raw", "mc2.json")
GEOJSON_PATH = os.path.join(PROJECT_DIR, "data", "raw", "Oceanus Information", "Oceanus Geography.geojson")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "data", "processed")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 工具函数
# ============================================================
def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def normalize_name(value: Any) -> str:
    return str(value).strip() if value is not None else ""

def safe_get(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return default

def is_vessel(node: Dict[str, Any]) -> bool:
    return "Entity.Vessel" in str(node.get("type", ""))

def is_ping(link: Dict[str, Any]) -> bool:
    return "TransponderPing" in str(link.get("type", ""))

def is_harbor_report(link: Dict[str, Any]) -> bool:
    return "HarborReport" in str(link.get("type", ""))

def is_delivery_report(node: Dict[str, Any]) -> bool:
    return "DeliveryReport" in str(node.get("type", ""))

def point_in_polygon(lon: float, lat: float, polygon: List) -> bool:
    """Ray-casting 算法判断点是否在多边形内"""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def is_night_time(time_str: str) -> bool:
    """判断时间戳是否在夜间 (20:00~05:59)"""
    try:
        dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
        h = dt.hour
        return h >= 20 or h < 6
    except Exception:
        return False

def cosine_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    """计算两个特征向量的余弦相似度"""
    common_keys = set(a.keys()) & set(b.keys())
    if not common_keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in common_keys)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

# ============================================================
# 主流程
# ============================================================
print("=" * 72)
print("VAST Challenge 2024 MC2 — 完整数据预处理 v2")
print("=" * 72)

# ------------------------------------------------------------------
# 1) 加载原始数据
# ------------------------------------------------------------------
print("[1/7] 加载原始数据...")
raw = load_json(RAW_DATA_PATH)
geojson = load_json(GEOJSON_PATH)

nodes: List[Dict[str, Any]] = raw.get("nodes", [])
links: List[Dict[str, Any]] = raw.get("links", [])

print(f"  nodes={len(nodes)}, links={len(links)}")

# ------------------------------------------------------------------
# 2) 构建节点查找表
# ------------------------------------------------------------------
print("[2/7] 构建节点查找表...")
vessel_nodes = [n for n in nodes if is_vessel(n)]
print(f"  船舶节点: {len(vessel_nodes)}")

# ------------------------------------------------------------------
# 3) 提取并清洗 Ping 和 HarborReport
# ------------------------------------------------------------------
print("[3/7] 提取并清洗事件数据...")

# 3.1 提取所有 Ping
all_pings: List[Dict[str, Any]] = []
for link in links:
    if not is_ping(link):
        continue
    dwell_raw = link.get("dwell")
    try:
        dwell_sec = float(dwell_raw) if dwell_raw is not None else 0.0
    except (TypeError, ValueError):
        dwell_sec = 0.0

    all_pings.append({
        "time": link.get("time"),
        "dwell": dwell_sec,  # 秒
        "location": normalize_name(link.get("source")),  # source=位置
        "vessel_id": normalize_name(link.get("target")),  # target=船
        "key": link.get("key"),
    })

print(f"  Ping 总数: {len(all_pings)}")

# 3.2 提取所有 HarborReport
all_harbor_reports: List[Dict[str, Any]] = []
for link in links:
    if not is_harbor_report(link):
        continue
    all_harbor_reports.append({
        "date": link.get("date"),
        "vessel_id": normalize_name(link.get("source")),  # source=船
        "port": normalize_name(link.get("target")),  # target=港口
        "key": link.get("key"),
    })

print(f"  HarborReport 总数: {len(all_harbor_reports)}")

# 3.3 构建 Fish 节点查找表（用于 DeliveryReport 关联）
fish_nodes_map: Dict[str, Dict] = {}
for n in nodes:
    ntype = str(n.get("type", ""))
    if "Entity.Commodity.Fish" in ntype or "Fish" in ntype:
        fid = n.get("id")
        if fid:
            fish_nodes_map[fid] = {
                "fish_id": fid,
                "fish_name": n.get("name") or n.get("fish_name") or fid,
            }

# 3.4 构建 Transaction 链接索引（DeliveryReport -> Fish / City）
# 每个 DeliveryReport 有 2 条 Event.Transaction 链接：
#   1) source=DeliveryReport.id -> target=Fish.id
#   2) source=DeliveryReport.id -> target=City.id
dr_transactions: Dict[str, Dict] = defaultdict(dict)
for link in links:
    if "Event.Transaction" not in str(link.get("type", "")):
        continue
    src = link.get("source", "")
    tgt = link.get("target", "")
    # 判断 target 是 Fish 还是 City
    if tgt in fish_nodes_map:
        dr_transactions[src]["fish_id"] = tgt
        dr_transactions[src]["fish_name"] = fish_nodes_map[tgt]["fish_name"]
    elif "City" in str(tgt):
        dr_transactions[src]["city_id"] = tgt

# 3.5 提取所有 DeliveryReport（通过 Transaction 链接关联鱼种和城市）
delivery_reports_raw = [n for n in nodes if is_delivery_report(n)]
clean_delivery_reports: List[Dict[str, Any]] = []
for dr in delivery_reports_raw:
    qty = dr.get("qty_tons")
    try:
        qty_value = float(qty) if qty is not None else None
    except (TypeError, ValueError):
        qty_value = None
    if qty_value is not None and qty_value <= 0:
        continue
    dr_id = dr.get("id", "")
    tx = dr_transactions.get(dr_id, {})
    clean_delivery_reports.append({
        "id": dr_id,
        "date": dr.get("date"),
        "qty_tons": qty_value,
        "fish_id": tx.get("fish_id"),
        "fish_name": tx.get("fish_name"),
        "city_id": tx.get("city_id"),
    })

print(f"  DeliveryReport 清洗后: {len(clean_delivery_reports)}")
print(f"  Fish 种类: {len(fish_nodes_map)}")

# ------------------------------------------------------------------
# 4) 构建地理信息
# ------------------------------------------------------------------
print("[4/7] 构建地理信息...")

# 4.1 从 GeoJSON 提取保护区 Polygon
preserves: Dict[str, List] = {}
preserve_names: set = set()  # 保护区名称集合，用于直接匹配位置名
fishing_grounds: List[str] = []
cities: List[str] = []
all_geo_features: List[Dict] = []

for feat in geojson.get("features", []):
    props = feat.get("properties", {})
    geom = feat.get("geometry", {})
    name = normalize_name(props.get("Name"))
    geom_type = geom.get("type")
    coords = geom.get("coordinates")

    if not name:
        continue

    feature = {
        "name": name,
        "description": props.get("Description"),
        "kind": props.get("*Kind") or props.get("Kind"),
        "type": props.get("type"),
        "activities": props.get("Activities", []),
        "geometry_type": geom_type,
        "coordinates": coords,
    }
    all_geo_features.append(feature)

    # 分类
    if "Preserve" in name or "Reef" in name:
        preserve_names.add(name)
        if geom_type == "Polygon" and coords:
            preserves[name] = coords[0]  # 外环
    if "Fishing" in str(props.get("type", "")) or "Ground" in name:
        fishing_grounds.append(name)
    if "City" in str(props.get("type", "")):
        cities.append(name)

# 补充 fishing_grounds 和 cities
for feat in all_geo_features:
    name = feat["name"]
    ftype = feat.get("type", "")
    if "Fishing" in str(ftype) and name not in fishing_grounds:
        fishing_grounds.append(name)
    if "City" in str(ftype) and name not in cities:
        cities.append(name)

# 手动补充已知的渔场
for fg in ["Cod Table", "Tuna Shelf", "Wrasse Beds"]:
    if fg not in fishing_grounds:
        fishing_grounds.append(fg)

# 手动补充已知的城市
for c in ["City of Port Grove", "City of Haacklee", "City of Paackland",
          "City of South Paackland", "City of Lomark", "City of Himark"]:
    if c not in cities:
        cities.append(c)

print(f"  保护区: {list(preserves.keys())}")
print(f"  渔场: {fishing_grounds}")
print(f"  城市: {cities}")

# 4.2 构建位置坐标查找表
location_coords: Dict[str, Dict] = {}
for feat in all_geo_features:
    name = feat["name"]
    geom_type = feat["geometry_type"]
    coords = feat.get("coordinates")
    if not coords:
        continue
    if geom_type == "Point" and len(coords) >= 2:
        location_coords[name] = {
            "lon": coords[0], "lat": coords[1], "type": geom_type
        }
    elif geom_type == "Polygon" and coords:
        ring = coords[0]
        if ring:
            lons = [p[0] for p in ring if isinstance(p, list) and len(p) >= 2]
            lats = [p[1] for p in ring if isinstance(p, list) and len(p) >= 2]
            if lons and lats:
                location_coords[name] = {
                    "lon": sum(lons) / len(lons),
                    "lat": sum(lats) / len(lats),
                    "type": geom_type,
                    "bounds": {
                        "min_lon": min(lons), "max_lon": max(lons),
                        "min_lat": min(lats), "max_lat": max(lats),
                    }
                }

print(f"  位置坐标: {len(location_coords)} 个")

# ------------------------------------------------------------------
# 5) 构建船舶移动指标
# ------------------------------------------------------------------
print("[5/7] 构建船舶移动指标...")

# 5.1 按船舶分组 Ping
vessel_pings: Dict[str, List[Dict]] = defaultdict(list)
for ping in all_pings:
    vid = ping["vessel_id"]
    if vid:
        vessel_pings[vid].append(ping)

# 5.2 按船舶分组 HarborReport
vessel_harbor: Dict[str, List[Dict]] = defaultdict(list)
for hr in all_harbor_reports:
    vid = hr["vessel_id"]
    if vid:
        vessel_harbor[vid].append(hr)

# 5.3 对每艘船计算指标
vessels_data: List[Dict] = []
vessel_movements: Dict[str, Dict] = {}

# SouthSeafood 公司名称
SOUTHSEAFOOD_COMPANY = "SouthSeafood Express Corp"

for vnode in vessel_nodes:
    vid = normalize_name(vnode.get("id"))
    vname = safe_get(vnode, "name", "Name", default=vid)
    company = safe_get(vnode, "company", "Company", default="Unknown")
    vtype = safe_get(vnode, "type", default="")
    flag = safe_get(vnode, "flag", "flag_country", default="Unknown")
    length = safe_get(vnode, "length", "length_overall", default=None)
    tonnage = safe_get(vnode, "tonnage", default=None)

    # 获取该船的 pings
    pings = vessel_pings.get(vid, [])

    if not pings:
        vessels_data.append({
            "vessel_id": vid,
            "vessel_name": vname,
            "company": company,
            "vessel_type": vtype,
            "flag_country": flag,
            "length_overall": length,
            "tonnage": tonnage,
            "is_southseafood": company == SOUTHSEAFOOD_COMPANY,
            "ping_count": 0,
            "unique_locations": 0,
            "first_seen": None,
            "last_seen": None,
            "protected_area_visits": 0,
            "fishing_ground_visits": 0,
            "city_visits": 0,
            "night_visits": 0,
            "night_fishing_ratio": 0.0,
            "avg_dwell_seconds": 0.0,
            "avg_dwell_hours": 0.0,
            "protected_dwell_ratio": 0.0,
            "protected_dwell_hours": 0.0,
            "protected_area_details": {},
            "region_visits": {},
            "entropy": 0.0,
            "locations_per_day": 0.0,
        })
        vessel_movements[vid] = {"name": vname, "pings": []}
        continue

    # 按时间排序
    pings_sorted = sorted(pings, key=lambda x: str(x.get("time", "")))

    # 统计
    ping_count = len(pings_sorted)
    location_set = set()
    protected_visits = 0
    fishing_visits = 0
    city_visits = 0
    night_visits = 0
    total_dwell_sec = 0.0
    protected_dwell_sec = 0.0
    protected_area_details: Dict[str, Dict] = {
        pname: {"visits": 0, "total_dwell_seconds": 0, "total_dwell_hours": 0}
        for pname in preserves
    }
    region_visits: Dict[str, int] = {}

    first_seen = pings_sorted[0].get("time")
    last_seen = pings_sorted[-1].get("time")

    # 计算时间跨度（天）
    try:
        t1 = datetime.fromisoformat(str(first_seen).replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
        days_span = max((t2 - t1).total_seconds() / 86400, 1)
    except Exception:
        days_span = 1

    for ping in pings_sorted:
        loc = ping.get("location", "")
        dwell_sec = ping.get("dwell", 0) or 0
        time_str = ping.get("time", "")

        location_set.add(loc)
        total_dwell_sec += dwell_sec

        # ===== 保护区判断（两种方式） =====
        # 方式1: 位置名本身就是保护区名称（如 "Ghoti Preserve"）
        if loc in preserve_names:
            protected_visits += 1
            protected_dwell_sec += dwell_sec
            if loc in protected_area_details:
                protected_area_details[loc]["visits"] += 1
                protected_area_details[loc]["total_dwell_seconds"] += dwell_sec
        else:
            # 方式2: 用坐标做点-in-多边形判断
            loc_coord = location_coords.get(loc)
            if loc_coord:
                lon = loc_coord.get("lon")
                lat = loc_coord.get("lat")
                for pname, ppoly in preserves.items():
                    if point_in_polygon(lon, lat, ppoly):
                        protected_visits += 1
                        protected_dwell_sec += dwell_sec
                        protected_area_details[pname]["visits"] += 1
                        protected_area_details[pname]["total_dwell_seconds"] += dwell_sec
                        break  # 一个 ping 只属于一个保护区

        # 判断是否在渔场
        if loc in fishing_grounds:
            fishing_visits += 1

        # 判断是否在城市
        if loc in cities:
            city_visits += 1

        # 判断是否夜间
        if is_night_time(time_str):
            night_visits += 1

        # 区域访问统计
        region_visits[loc] = region_visits.get(loc, 0) + 1

    # 计算指标
    avg_dwell_sec = total_dwell_sec / ping_count if ping_count > 0 else 0
    avg_dwell_hours = avg_dwell_sec / 3600
    protected_dwell_hours = protected_dwell_sec / 3600
    protected_dwell_ratio = protected_dwell_sec / total_dwell_sec if total_dwell_sec > 0 else 0
    night_fishing_ratio = night_visits / ping_count if ping_count > 0 else 0

    # 计算位置熵 (entropy)
    loc_probs = [cnt / ping_count for cnt in region_visits.values()]
    entropy = -sum(p * math.log2(p) for p in loc_probs) if loc_probs else 0

    # 计算 locations_per_day（每日 Ping 次数，反映活动频率）
    locations_per_day = ping_count / days_span

    # 转换 protected_area_details 的 dwell 为小时
    for pname in protected_area_details:
        protected_area_details[pname]["total_dwell_hours"] = \
            protected_area_details[pname]["total_dwell_seconds"] / 3600

    # 计算 transitions（位置转移计数）
    transitions: Dict[str, int] = {}
    for i in range(1, len(pings_sorted)):
        prev_loc = pings_sorted[i-1].get("location", "")
        curr_loc = pings_sorted[i].get("location", "")
        if prev_loc and curr_loc and prev_loc != curr_loc:
            key = f"{prev_loc} -> {curr_loc}"
            transitions[key] = transitions.get(key, 0) + 1

    vessels_data.append({
        "vessel_id": vid,
        "vessel_name": vname,
        "company": company,
        "vessel_type": vtype,
        "flag_country": flag,
        "length_overall": length,
        "tonnage": tonnage,
        "is_southseafood": company == SOUTHSEAFOOD_COMPANY,
        "ping_count": ping_count,
        "unique_locations": len(location_set),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "protected_area_visits": protected_visits,
        "fishing_ground_visits": fishing_visits,
        "city_visits": city_visits,
        "night_visits": night_visits,
        "night_fishing_ratio": night_fishing_ratio,
        "avg_dwell_seconds": avg_dwell_sec,
        "avg_dwell_hours": avg_dwell_hours,
        "protected_dwell_ratio": protected_dwell_ratio,
        "protected_dwell_hours": protected_dwell_hours,
        "protected_area_details": protected_area_details,
        "region_visits": region_visits,
        "entropy": entropy,
        "locations_per_day": locations_per_day,
        "transitions": transitions,
    })

    # 构建移动轨迹
    movement_pings = []
    for ping in pings_sorted:
        movement_pings.append({
            "time": ping.get("time"),
            "dwell": ping.get("dwell", 0),
            "location": ping.get("location", ""),
        })
    vessel_movements[vid] = {"name": vname, "pings": movement_pings}

print(f"  处理船舶: {len(vessels_data)} 艘")

# ------------------------------------------------------------------
# 6) 计算船舶相似度
# ------------------------------------------------------------------
print("[6/7] 计算船舶相似度...")

FEATURE_KEYS = [
    "avg_dwell_hours", "night_fishing_ratio",
    "protected_dwell_ratio", "locations_per_day", "entropy"
]

feature_vectors: Dict[str, Dict[str, float]] = {}
for v in vessels_data:
    vid = v["vessel_id"]
    feature_vectors[vid] = {k: v.get(k, 0) for k in FEATURE_KEYS}

southseafood_ids = {v["vessel_id"] for v in vessels_data if v["is_southseafood"]}

similar_vessels = []
for v in vessels_data:
    vid = v["vessel_id"]
    if vid in southseafood_ids:
        continue
    vec_a = feature_vectors[vid]
    for ss_id in southseafood_ids:
        vec_b = feature_vectors[ss_id]
        sim = cosine_similarity(vec_a, vec_b)
        if sim > 0.5:
            contributions = {}
            for k in FEATURE_KEYS:
                diff = abs(vec_a.get(k, 0) - vec_b.get(k, 0))
                contributions[k] = round(1 - min(diff / max(vec_b.get(k, 0.001), 0.001), 1), 4)
            similar_vessels.append({
                "vessel_id": vid,
                "vessel_name": v["vessel_name"],
                "company": v["company"],
                "similar_to": ss_id,
                "similar_to_name": next(
                    (vv["vessel_name"] for vv in vessels_data if vv["vessel_id"] == ss_id), ""),
                "similarity_score": round(sim, 4),
                "feature_contributions": contributions,
            })

similar_vessels.sort(key=lambda x: x["similarity_score"], reverse=True)
similar_vessels = similar_vessels[:100]
print(f"  相似船舶对: {len(similar_vessels)}")

# ------------------------------------------------------------------
# 7) 计算风险评分
# ------------------------------------------------------------------
print("[7/7] 计算风险评分...")

risk_vessels = []
for v in vessels_data:
    if v["ping_count"] == 0:
        continue
    risk_score = (
        v["protected_dwell_ratio"] * 0.4 +
        v["night_fishing_ratio"] * 0.3 +
        min(1, v["avg_dwell_hours"] / 20) * 0.15 +
        min(1, v["entropy"] / 2.5) * 0.15
    )
    risk_vessels.append({
        "vessel_id": v["vessel_id"],
        "vessel_name": v["vessel_name"],
        "company": v["company"],
        "risk_score": round(risk_score, 4),
        "protected_dwell_ratio": v["protected_dwell_ratio"],
        "night_fishing_ratio": v["night_fishing_ratio"],
        "protected_area_visits": v["protected_area_visits"],
        "fishing_ground_visits": v["fishing_ground_visits"],
    })

risk_vessels.sort(key=lambda x: x["risk_score"], reverse=True)
risk_vessels = risk_vessels[:50]
print(f"  高风险船舶: {len(risk_vessels)}")

# ------------------------------------------------------------------
# 8) 构建 SouthSeafood 详细数据
# ------------------------------------------------------------------
southseafood_vessels = []
for v in vessels_data:
    if not v["is_southseafood"]:
        continue
    vid = v["vessel_id"]
    mov = vessel_movements.get(vid, {"pings": []})
    southseafood_vessels.append({
        "vessel_info": {k: v[k] for k in [
            "vessel_id", "vessel_name", "company", "vessel_type",
            "flag_country", "length_overall", "tonnage", "is_southseafood",
            "ping_count", "unique_locations", "first_seen", "last_seen",
            "protected_area_visits", "fishing_ground_visits", "city_visits",
            "night_visits", "night_fishing_ratio", "avg_dwell_seconds",
            "avg_dwell_hours", "protected_dwell_ratio", "protected_dwell_hours",
            "protected_area_details", "region_visits",
        ]},
        "pings": mov["pings"],
    })

print(f"  SouthSeafood 船舶详情: {len(southseafood_vessels)} 艘")

# ------------------------------------------------------------------
# 9) 组装输出
# ------------------------------------------------------------------
print("\n[8/8] 写入输出文件...")

locations = sorted(set(
    loc for v in vessels_data
    for loc in v.get("region_visits", {}).keys()
))

fish_types = sorted(set(
    dr.get("fish_name") for dr in clean_delivery_reports
    if dr.get("fish_name")
))

# 构建 commodities（商品列表，用于前端筛选）
commodities = sorted(set(
    dr.get("fish_name") for dr in clean_delivery_reports
    if dr.get("fish_name")
))

# 构建 delivery_vessel_links（DeliveryReport 与船舶的关联）
# 先建立 Transaction 链接的索引：source -> [targets]
transaction_links: Dict[str, List[str]] = defaultdict(list)
for link in links:
    if "Event.Transaction" not in str(link.get("type", "")):
        continue
    src = link.get("source", "")
    tgt = link.get("target", "")
    if src and tgt:
        transaction_links[src].append(tgt)
        transaction_links[tgt].append(src)

# 从 Transaction 链接中找出与 DeliveryReport 关联的 vessel
# 每个 DeliveryReport 有 2 条 Transaction 链接（指向 Fish 和 City）
# 没有直接指向 Vessel 的链接，所以 delivery_vessel_links 为空列表
# 前端使用 delivery_reports 中的 fish_name/city_id 做商品关联分析
delivery_vessel_links = []

processed_data = {
    "description": "VAST Challenge 2024 MC2 — 完整预处理数据",
    "anomalies": {},
    "vessels": vessels_data,
    "southseafood_vessels": southseafood_vessels,
    "similar_vessels": similar_vessels,
    "risk_vessels": risk_vessels,
    "locations": locations,
    "fish_types": fish_types,
    "commodities": commodities,
    "delivery_reports": clean_delivery_reports,
    "delivery_vessel_links": delivery_vessel_links,
    "harbor_reports": {vid: vh for vid, vh in vessel_harbor.items()},
    "geography": {
        "protected_areas": list(preserves.keys()),
        "fishing_grounds": fishing_grounds,
        "cities": cities,
        "islands": [],
        "buoys": [],
    },
    "location_coords": location_coords,
    "protected_areas": list(preserves.keys()),
    "fishing_grounds": fishing_grounds,
    "cities": cities,
}

processed_path = os.path.join(OUTPUT_DIR, "processed_data.json")
movements_path = os.path.join(OUTPUT_DIR, "vessel_movements.json")
geography_path = os.path.join(OUTPUT_DIR, "geography.json")
report_path = os.path.join(OUTPUT_DIR, "preprocess_report.json")

save_json(processed_path, processed_data)
save_json(movements_path, vessel_movements)
save_json(geography_path, {
    "features": all_geo_features,
    "location_coords": location_coords,
})

report = {
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "summary": {
        "total_vessels": len(vessels_data),
        "total_pings": len(all_pings),
        "total_harbor_reports": len(all_harbor_reports),
        "total_delivery_reports": len(clean_delivery_reports),
        "protected_areas": list(preserves.keys()),
        "fishing_grounds": fishing_grounds,
        "cities": cities,
        "southseafood_vessels": len(southseafood_vessels),
        "similar_vessel_pairs": len(similar_vessels),
        "risk_vessels": len(risk_vessels),
    },
    "southseafood_check": {
        v["vessel_name"]: {
            "protected_dwell_ratio": v["protected_dwell_ratio"],
            "protected_dwell_hours": v["protected_dwell_hours"],
            "protected_area_details": v["protected_area_details"],
        }
        for v in vessels_data if v["is_southseafood"]
    },
}
save_json(report_path, report)

print(f"  processed_data.json -> {processed_path}")
print(f"  vessel_movements.json -> {movements_path}")
print(f"  geography.json -> {geography_path}")
print(f"  preprocess_report.json -> {report_path}")
print("=" * 72)
print("完成！")
