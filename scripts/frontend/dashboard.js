/**
 * Oceanus 非法渔业调查系统 — 三栏布局 · 地图为主
 * VAST Challenge 2024 MC2
 * 
 * 布局：左筛选 | 中地图+时间轴+聚类 | 右证据链
 * 叙事：全局描述 → 违规画像 → 相似扩展 → 变化验证
 */

// ============================================================
// 全局状态
// ============================================================
const STATE = {
  vessels: [],
  southseafood: [],
  movements: {},
  geography: null,
  vesselId: null,
  location: 'all',
  commodity: 'all',
  timePreset: 'all',
  mode: 'overview',
  selectedVesselIds: [],
  mapMode: 'single',
  timelineLayer: 'all',
  filterSeedOnly: false,
  filterProtected: false, // 时间轴过滤：仅显示保护区停留
  vesselById: new Map(),
  vesselByName: new Map(),
  seedIds: new Set(),
  seedNames: new Set(),
  locationCoords: {},
  tsneCoords: null,
  deliveryLinks: [],
  deliveryReports: [],
  fishTypes: [],
  // 时间范围（实际过滤用）
  timeRange: null, // { start: Date, end: Date }
  // 曝光日期（用于时间预设）
  // SouthSeafood 最后活动时间为 2035-05-14，之后船只停止活动，故曝光日期设为 2035-05-15
  exposureDate: new Date('2035-05-15'),
  // 自定义时间区间
  customTimeStart: null, // Date
  customTimeEnd: null,   // Date
};

// ============================================================
// 工具函数
// ============================================================
function fmt(v) { return formatNumber(v); }
function fmtPct(v) { return (v * 100).toFixed(1) + '%'; }
function fmtHour(v) { return v.toFixed(1) + 'h'; }
function coordLon(coord) { return Array.isArray(coord) ? coord[0] : coord?.lon; }
function coordLat(coord) { return Array.isArray(coord) ? coord[1] : coord?.lat; }
function pingLon(ping) { return ping?.lon ?? coordLon(STATE.locationCoords?.[ping?.location]); }
function pingLat(ping) { return ping?.lat ?? coordLat(STATE.locationCoords?.[ping?.location]); }
function pingDwellHours(ping) {
  if (!ping) return 0;
  if (Number.isFinite(ping.dwell_hours)) return ping.dwell_hours;
  if (Number.isFinite(ping.dwell_seconds)) return ping.dwell_seconds / 3600;
  return Number.isFinite(ping.dwell) ? ping.dwell : 0;
}
function isValidPingCoord(ping) {
  return Number.isFinite(pingLon(ping)) && Number.isFinite(pingLat(ping));
}

function calcRisk(v) {
  if (!v) return 0;
  const pb = Math.min(1, (v.protected_dwell_ratio || 0) * 2.4);
  const nb = Math.min(1, (v.night_fishing_ratio || 0) * 1.3);
  const sb = Math.min(1, (10 / Math.max(1, v.avg_dwell_hours || 1)) / 5);
  const eb = Math.min(1, (v.entropy || 0) / 2.5);
  return Math.max(0, Math.min(1, pb * 0.42 + nb * 0.28 + sb * 0.14 + eb * 0.16));
}

function getRiskLevel(v) {
  const r = calcRisk(v);
  return r > 0.7 ? 'high' : r > 0.45 ? 'medium' : 'low';
}

function getVesselTypeShort(type) {
  if (!type) return 'Other';
  const map = { FishingVessel: 'Fishing', CargoVessel: 'Cargo', Tour: 'Tour', 'Ferry.Passenger': 'Ferry', 'Ferry.Cargo': 'Ferry', Research: 'Research', Other: 'Other' };
  return map[type.split('.').pop()] || type.split('.').pop();
}

function getVesselTypeColor(type) {
  const map = { FishingVessel: '#3b82f6', CargoVessel: '#f97316', Tour: '#8b5cf6', 'Ferry.Passenger': '#8b5cf6', 'Ferry.Cargo': '#8b5cf6', Research: '#10b981', Other: '#6b7280' };
  return map[type?.split('.').pop()] || '#6b7280';
}

function avg(arr, key) {
  const vals = arr.map(d => d?.[key]).filter(v => v != null && !Number.isNaN(v));
  return d3.mean(vals) || 0;
}

// ============================================================
// 数据加载
// ============================================================
async function loadAllData() {
  const [processed, movements, geo] = await Promise.all([
    loadProcessedData(),
    loadVesselMovements(),
    loadGeography()
  ]);

  STATE.vessels = processed.vessels || [];
  STATE.southseafood = processed.southseafood_vessels || [];
  STATE.movements = movements;
  STATE.geography = geo;
  STATE.locationCoords = processed.location_coords || {};
  STATE.deliveryLinks = processed.delivery_vessel_links || [];
  STATE.deliveryReports = processed.delivery_reports || [];
  if (Array.isArray(processed.fish_types)) {
    STATE.fishTypes = processed.fish_types;
  }

  STATE.vesselById = new Map(STATE.vessels.map(v => [v.vessel_id, v]));
  STATE.vesselByName = new Map(STATE.vessels.map(v => [v.vessel_name, v]));
  // 正确方式：从 vessels 中筛选 company 为 SouthSeafood Express Corp 的船
  STATE.seedIds = new Set(
    STATE.vessels
      .filter(v => v.company === 'SouthSeafood Express Corp')
      .map(v => v.vessel_id)
  );
  STATE.seedNames = new Set(
    STATE.vessels
      .filter(v => v.company === 'SouthSeafood Express Corp')
      .map(v => v.vessel_name)
  );

  // 默认选中第一艘 SouthSeafood 的船
  const firstSeedVessel = STATE.vessels.find(v => v.company === 'SouthSeafood Express Corp');
  STATE.vesselId = firstSeedVessel?.vessel_id || STATE.vessels[0]?.vessel_id;

  // 加载 t-SNE 坐标
  try {
    const resp = await fetch('data/tsne_coords.json');
    STATE.tsneCoords = await resp.json();
  } catch (e) {
    console.warn('tsne_coords.json not loaded, using fallback');
  }
}

// ============================================================
// 筛选逻辑（含时间过滤）
// ============================================================
function getFilteredVessels() {
  let list = STATE.vessels;
  if (STATE.filterSeedOnly) list = list.filter(v => STATE.seedIds.has(v.vessel_id));
  return list;
}

/** 根据时间预设或自定义时间区间过滤 pings */
function filterPingsByTime(pings) {
  if (!pings || pings.length === 0) return pings;
  // 自定义时间区间优先
  if (STATE.customTimeStart && STATE.customTimeEnd) {
    return pings.filter(p => {
      const t = new Date(p.time);
      return t >= STATE.customTimeStart && t <= STATE.customTimeEnd;
    });
  }
  // 预设
  if (STATE.timePreset === 'all') return pings;
  const exposure = STATE.exposureDate;
  return pings.filter(p => {
    const t = new Date(p.time);
    if (STATE.timePreset === 'pre') return t < exposure;
    if (STATE.timePreset === 'post') return t >= exposure;
    return true;
  });
}

/** 获取某艘船过滤后的 pings */
function getFilteredPings(vesselId) {
  const mov = STATE.movements[vesselId];
  if (!mov || !mov.pings) return null;
  return filterPingsByTime(mov.pings);
}

// ============================================================
// 渲染：顶部控制栏（已移除分析对象下拉框）
// ============================================================
function renderTopBar() {
  // 顶部控制栏不再包含船舶选择
}
// ============================================================
// 渲染：左侧筛选
// ============================================================
// ============================================================
// Autocomplete 船舶筛选器（只初始化一次）
// ============================================================
let _vesselAutocompleteInitialized = false;

function initVesselAutocomplete() {
  if (_vesselAutocompleteInitialized) {
    // 已初始化，只需更新输入框的值
    const input = document.getElementById('vessel-input');
    if (input) {
      const currentVessel = STATE.vesselById.get(STATE.vesselId);
      if (currentVessel) input.value = currentVessel.vessel_name;
    }
    return;
  }

  const input = document.getElementById('vessel-input');
  let dropdown = document.getElementById('vessel-dropdown');
  if (!input || !dropdown) return;

  _vesselAutocompleteInitialized = true;

  // 将 dropdown 移到 body 下，彻底脱离所有父容器的层叠上下文限制
  document.body.appendChild(dropdown);

  // 构建船舶列表（按名称字典序排列）
  const seedFleet = STATE.vessels
    .filter(v => STATE.seedIds.has(v.vessel_id))
    .sort((a, b) => a.vessel_name.localeCompare(b.vessel_name, 'zh-CN'));
  const nonSeed = STATE.vessels
    .filter(v => !STATE.seedIds.has(v.vessel_id))
    .sort((a, b) => a.vessel_name.localeCompare(b.vessel_name, 'zh-CN'));

  let highlightedIndex = -1;
  let currentFilteredItems = [];

  function getFilteredItems(query) {
    const q = query.trim().toLowerCase();
    if (!q) {
      // 无输入时显示全部，按分组排列
      return [
        ...seedFleet.map(v => ({ ...v, _group: '🚨 SouthSeafood 种子船', _isSeed: true })),
        ...nonSeed.map(v => ({ ...v, _group: '🚢 其他船舶', _isSeed: false }))
      ];
    }
    // 前缀匹配
    const seedMatches = seedFleet
      .filter(v => v.vessel_name.toLowerCase().startsWith(q))
      .map(v => ({ ...v, _group: '🚨 SouthSeafood 种子船', _isSeed: true }));
    const nonSeedMatches = nonSeed
      .filter(v => v.vessel_name.toLowerCase().startsWith(q))
      .map(v => ({ ...v, _group: '🚢 其他船舶', _isSeed: false }));
    return [...seedMatches, ...nonSeedMatches];
  }

  function positionDropdown() {
    const rect = input.getBoundingClientRect();
    dropdown.style.left = rect.left + 'px';
    dropdown.style.top = (rect.bottom + 4) + 'px';
    dropdown.style.width = rect.width + 'px';
  }

  // 滚动时重新定位
  window.addEventListener('scroll', function() {
    if (dropdown.classList.contains('open')) {
      positionDropdown();
    }
  }, true);

  function renderDropdown(items) {
    dropdown.innerHTML = '';
    currentFilteredItems = items;
    highlightedIndex = -1;

    if (items.length === 0) {
      dropdown.innerHTML = '<div class="dropdown-empty">未找到匹配的船舶</div>';
      dropdown.classList.add('open');
      positionDropdown();
      return;
    }

    // 分组渲染
    let currentGroup = '';
    items.forEach((item, idx) => {
      if (item._group !== currentGroup) {
        currentGroup = item._group;
        const groupLabel = document.createElement('div');
        groupLabel.className = 'dropdown-group-label';
        groupLabel.textContent = currentGroup;
        dropdown.appendChild(groupLabel);
      }

      const div = document.createElement('div');
      div.className = 'dropdown-item' + (item._isSeed ? ' is-seed' : '');
      div.dataset.index = idx;

      // 船名（高亮匹配前缀）
      const query = input.value.trim().toLowerCase();
      const nameSpan = document.createElement('span');
      nameSpan.className = 'vessel-name';
      if (query && item.vessel_name.toLowerCase().startsWith(query)) {
        const prefix = item.vessel_name.substring(0, query.length);
        const rest = item.vessel_name.substring(query.length);
        nameSpan.innerHTML = `<span class="match-highlight">${escapeHtml(prefix)}</span>${escapeHtml(rest)}`;
      } else {
        nameSpan.textContent = item.vessel_name;
      }

      // 类型标签
      const badge = document.createElement('span');
      badge.className = 'vessel-type-badge';
      badge.textContent = getVesselTypeShort(item.vessel_type);

      div.appendChild(nameSpan);
      div.appendChild(badge);

      // 点击事件
      div.addEventListener('mousedown', function(e) {
        e.preventDefault();
        selectVesselItem(item);
      });

      // 悬停高亮
      div.addEventListener('mouseenter', function() {
        highlightedIndex = idx;
        updateHighlight();
      });

      dropdown.appendChild(div);
    });

    dropdown.classList.add('open');
    positionDropdown();
  }

  function updateHighlight() {
    const items = dropdown.querySelectorAll('.dropdown-item');
    items.forEach((el, idx) => {
      el.classList.toggle('highlighted', idx === highlightedIndex);
    });
  }

  function selectVesselItem(item) {
    input.value = item.vessel_name;
    dropdown.classList.remove('open');
    STATE.vesselId = item.vessel_id;
    refreshAll();
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // --- 事件绑定 ---

  // 输入事件：实时过滤
  input.addEventListener('input', function() {
    const items = getFilteredItems(this.value);
    renderDropdown(items);
  });

  // 聚焦事件：展开下拉
  input.addEventListener('focus', function() {
    const items = getFilteredItems(this.value);
    renderDropdown(items);
  });

  // 失焦事件：延迟关闭下拉（让点击事件先触发）
  input.addEventListener('blur', function() {
    setTimeout(() => {
      dropdown.classList.remove('open');
    }, 200);
  });

  // 键盘导航
  input.addEventListener('keydown', function(e) {
    const items = currentFilteredItems;
    if (items.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      highlightedIndex = Math.min(highlightedIndex + 1, items.length - 1);
      updateHighlight();
      // 滚动到可见区域
      const highlightedEl = dropdown.querySelector('.dropdown-item.highlighted');
      if (highlightedEl) highlightedEl.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      highlightedIndex = Math.max(highlightedIndex - 1, 0);
      updateHighlight();
      const highlightedEl = dropdown.querySelector('.dropdown-item.highlighted');
      if (highlightedEl) highlightedEl.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (highlightedIndex >= 0 && highlightedIndex < items.length) {
        selectVesselItem(items[highlightedIndex]);
      }
    } else if (e.key === 'Escape') {
      dropdown.classList.remove('open');
    }
  });

  // 点击外部关闭下拉
  document.addEventListener('click', function(e) {
    const wrap = document.getElementById('vessel-autocomplete');
    if (wrap && !wrap.contains(e.target)) {
      dropdown.classList.remove('open');
    }
  });

  // 设置初始值
  const currentVessel = STATE.vesselById.get(STATE.vesselId);
  if (currentVessel) {
    input.value = currentVessel.vessel_name;
  }
}

// ============================================================
// Autocomplete 地点筛选器
// ============================================================
let _locationAutocompleteInitialized = false;

function initLocationAutocomplete() {
  if (_locationAutocompleteInitialized) {
    // 已初始化，只需更新输入框的值
    const input = document.getElementById('location-input');
    if (input) {
      input.value = STATE.location === 'all' ? '' : STATE.location;
    }
    return;
  }

  const input = document.getElementById('location-input');
  let dropdown = document.getElementById('location-dropdown');
  if (!input || !dropdown) return;

  _locationAutocompleteInitialized = true;

  // 将 dropdown 移到 body 下
  document.body.appendChild(dropdown);

  // 构建地点列表
  const locs = new Set();
  STATE.vessels.forEach(v => {
    if (v.transitions) Object.keys(v.transitions).forEach(k => {
      k.split('->').forEach(l => locs.add(l.trim()));
    });
  });
  const locationItems = ['all', ...[...locs].sort()];

  let highlightedIndex = -1;
  let currentFilteredItems = [];

  function getFilteredItems(query) {
    const q = query.trim().toLowerCase();
    if (!q) {
      return locationItems.map(loc => ({
        value: loc,
        label: loc === 'all' ? '📍 全部位置' : loc
      }));
    }
    return locationItems
      .filter(loc => loc === 'all' || loc.toLowerCase().includes(q))
      .map(loc => ({
        value: loc,
        label: loc === 'all' ? '📍 全部位置' : loc
      }));
  }

  function positionDropdown() {
    const rect = input.getBoundingClientRect();
    dropdown.style.left = rect.left + 'px';
    dropdown.style.top = (rect.bottom + 4) + 'px';
    dropdown.style.width = rect.width + 'px';
  }

  // 滚动时重新定位
  window.addEventListener('scroll', function() {
    if (dropdown.classList.contains('open')) {
      positionDropdown();
    }
  }, true);

  function renderDropdown(items) {
    dropdown.innerHTML = '';
    currentFilteredItems = items;
    highlightedIndex = -1;

    if (items.length === 0) {
      dropdown.innerHTML = '<div class="dropdown-empty">未找到匹配的地点</div>';
      dropdown.classList.add('open');
      positionDropdown();
      return;
    }

    items.forEach((item, idx) => {
      const div = document.createElement('div');
      div.className = 'dropdown-item' + (item.value === STATE.location ? ' selected' : '');
      div.dataset.index = idx;
      div.textContent = item.label;

      div.addEventListener('mousedown', function(e) {
        e.preventDefault();
        selectLocationItem(item);
      });

      div.addEventListener('mouseenter', function() {
        highlightedIndex = idx;
        updateHighlight();
      });

      dropdown.appendChild(div);
    });

    dropdown.classList.add('open');
    positionDropdown();
  }

  function updateHighlight() {
    const items = dropdown.querySelectorAll('.dropdown-item');
    items.forEach((el, idx) => {
      el.classList.toggle('highlighted', idx === highlightedIndex);
    });
  }

  function selectLocationItem(item) {
    input.value = item.value === 'all' ? '' : item.value;
    dropdown.classList.remove('open');
    STATE.location = item.value;
    refreshAll({ skipCluster: true });
  }

  // --- 事件绑定 ---

  // 点击时始终弹出下拉框，显示全部选项（不做匹配过滤）
  input.addEventListener('click', function(e) {
    e.stopPropagation();
    const items = getFilteredItems('');
    renderDropdown(items);
  });

  input.addEventListener('focus', function() {
    const items = getFilteredItems('');
    renderDropdown(items);
  });

  input.addEventListener('blur', function() {
    setTimeout(() => {
      dropdown.classList.remove('open');
    }, 200);
  });

  input.addEventListener('keydown', function(e) {
    const items = currentFilteredItems;
    if (items.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      highlightedIndex = Math.min(highlightedIndex + 1, items.length - 1);
      updateHighlight();
      const highlightedEl = dropdown.querySelector('.dropdown-item.highlighted');
      if (highlightedEl) highlightedEl.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      highlightedIndex = Math.max(highlightedIndex - 1, 0);
      updateHighlight();
      const highlightedEl = dropdown.querySelector('.dropdown-item.highlighted');
      if (highlightedEl) highlightedEl.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (highlightedIndex >= 0 && highlightedIndex < items.length) {
        selectLocationItem(items[highlightedIndex]);
      }
    } else if (e.key === 'Escape') {
      dropdown.classList.remove('open');
    }
  });

  document.addEventListener('click', function(e) {
    const wrap = document.getElementById('location-autocomplete');
    if (wrap && !wrap.contains(e.target)) {
      dropdown.classList.remove('open');
    }
  });

  // 设置初始值
  input.value = STATE.location === 'all' ? '' : STATE.location;
}

// ============================================================
// Autocomplete 商品筛选器
// ============================================================
let _commodityAutocompleteInitialized = false;

function initCommodityAutocomplete() {
  if (_commodityAutocompleteInitialized) {
    const input = document.getElementById('commodity-input');
    if (input) {
      input.value = STATE.commodity === 'all' ? '' : STATE.commodity;
    }
    return;
  }

  const input = document.getElementById('commodity-input');
  let dropdown = document.getElementById('commodity-dropdown');
  if (!input || !dropdown) return;

  _commodityAutocompleteInitialized = true;

  // 将 dropdown 移到 body 下
  document.body.appendChild(dropdown);

  // 构建商品列表
  function resolveCommodityLabel(report) {
    if (!report) return null;
    if (report.fish_name) return report.fish_name;
    if (report.fish_family) return report.fish_family;
    if (report.fish_id && Array.isArray(STATE.fishTypes)) {
      const match = STATE.fishTypes.find(f => f.fish_id === report.fish_id);
      if (match?.fish_name) return match.fish_name;
    }
    return null;
  }

  const dynamicCommoditySet = new Set();
  const reports = Array.isArray(STATE.deliveryReports) ? STATE.deliveryReports : [];
  reports.forEach(r => {
    const label = resolveCommodityLabel(r);
    if (label) dynamicCommoditySet.add(label);
  });

  let commodityItems;
  if (dynamicCommoditySet.size === 0) {
    commodityItems = ['all', 'Seafood', 'Dry Goods', 'Electronics', 'Mixed', 'Other'];
  } else {
    commodityItems = ['all', ...Array.from(dynamicCommoditySet).sort()];
  }

  let highlightedIndex = -1;
  let currentFilteredItems = [];

  function getFilteredItems(query) {
    const q = query.trim().toLowerCase();
    if (!q) {
      return commodityItems.map(c => ({
        value: c,
        label: c === 'all' ? '📦 全部商品' : c
      }));
    }
    return commodityItems
      .filter(c => c === 'all' || c.toLowerCase().includes(q))
      .map(c => ({
        value: c,
        label: c === 'all' ? '📦 全部商品' : c
      }));
  }

  function positionDropdown() {
    const rect = input.getBoundingClientRect();
    dropdown.style.left = rect.left + 'px';
    dropdown.style.top = (rect.bottom + 4) + 'px';
    dropdown.style.width = rect.width + 'px';
  }

  // 滚动时重新定位
  window.addEventListener('scroll', function() {
    if (dropdown.classList.contains('open')) {
      positionDropdown();
    }
  }, true);

  function renderDropdown(items) {
    dropdown.innerHTML = '';
    currentFilteredItems = items;
    highlightedIndex = -1;

    if (items.length === 0) {
      dropdown.innerHTML = '<div class="dropdown-empty">未找到匹配的商品</div>';
      dropdown.classList.add('open');
      positionDropdown();
      return;
    }

    items.forEach((item, idx) => {
      const div = document.createElement('div');
      div.className = 'dropdown-item' + (item.value === STATE.commodity ? ' selected' : '');
      div.dataset.index = idx;
      div.textContent = item.label;

      div.addEventListener('mousedown', function(e) {
        e.preventDefault();
        selectCommodityItem(item);
      });

      div.addEventListener('mouseenter', function() {
        highlightedIndex = idx;
        updateHighlight();
      });

      dropdown.appendChild(div);
    });

    dropdown.classList.add('open');
    positionDropdown();
  }

  function updateHighlight() {
    const items = dropdown.querySelectorAll('.dropdown-item');
    items.forEach((el, idx) => {
      el.classList.toggle('highlighted', idx === highlightedIndex);
    });
  }

  function selectCommodityItem(item) {
    input.value = item.value === 'all' ? '' : item.value;
    dropdown.classList.remove('open');
    STATE.commodity = item.value;
    refreshAll({ skipCluster: true });
  }

  // --- 事件绑定 ---

  // 点击时始终弹出下拉框，显示全部选项（不做匹配过滤）
  input.addEventListener('click', function(e) {
    e.stopPropagation();
    const items = getFilteredItems('');
    renderDropdown(items);
  });

  input.addEventListener('focus', function() {
    const items = getFilteredItems('');
    renderDropdown(items);
  });

  input.addEventListener('blur', function() {
    setTimeout(() => {
      dropdown.classList.remove('open');
    }, 200);
  });

  input.addEventListener('keydown', function(e) {
    const items = currentFilteredItems;
    if (items.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      highlightedIndex = Math.min(highlightedIndex + 1, items.length - 1);
      updateHighlight();
      const highlightedEl = dropdown.querySelector('.dropdown-item.highlighted');
      if (highlightedEl) highlightedEl.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      highlightedIndex = Math.max(highlightedIndex - 1, 0);
      updateHighlight();
      const highlightedEl = dropdown.querySelector('.dropdown-item.highlighted');
      if (highlightedEl) highlightedEl.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (highlightedIndex >= 0 && highlightedIndex < items.length) {
        selectCommodityItem(items[highlightedIndex]);
      }
    } else if (e.key === 'Escape') {
      dropdown.classList.remove('open');
    }
  });

  document.addEventListener('click', function(e) {
    const wrap = document.getElementById('commodity-autocomplete');
    if (wrap && !wrap.contains(e.target)) {
      dropdown.classList.remove('open');
    }
  });

  // 设置初始值
  input.value = STATE.commodity === 'all' ? '' : STATE.commodity;
}

function renderFilters() {
  // 初始化 autocomplete（只初始化一次）
  initVesselAutocomplete();
  initLocationAutocomplete();
  initCommodityAutocomplete();
}

// ============================================================
// 渲染：地图视图（主视图）
// ============================================================
function renderMap() {
  const container = document.getElementById('map-viz');
  container.innerHTML = '';
  const { width, height } = getResponsiveSize(container);
  const margin = { top: 22, right: 18, bottom: 18, left: 18 };
  const lonExtent = [-167.5, -163.0];
  const latExtent = [38.0, 40.8];
  const x = d3.scaleLinear().domain(lonExtent).range([margin.left, width - margin.right]);
  const y = d3.scaleLinear().domain(latExtent).range([height - margin.bottom, margin.top]);

  const svg = d3.select(container).append('svg').attr('width', width).attr('height', height);
  const g = svg.append('g');

  // 保护区（全部用红色）
  STATE.geography.protected_areas?.forEach(p => {
    const pts = (p.coordinates?.[0] || p.coordinates || []).map(c => x(c[0]) + ',' + y(c[1])).join(' ');
    if (!pts) return;
    g.append('polygon').attr('points', pts)
      .attr('fill', 'rgba(239,68,68,.14)')
      .attr('stroke', '#ef4444')
      .attr('stroke-dasharray', '5 4').attr('stroke-width', 1.3);
  });

  // 渔场
  STATE.geography.fishing_grounds?.forEach(p => {
    const pts = (p.coordinates?.[0] || p.coordinates || []).map(c => x(c[0]) + ',' + y(c[1])).join(' ');
    if (!pts) return;
    g.append('polygon').attr('points', pts)
      .attr('fill', 'rgba(59,130,246,.10)').attr('stroke', '#3b82f6').attr('stroke-width', 1.1);
  });

  // 城市
  STATE.geography.cities?.forEach(c => {
    const [cx, cy] = c.coordinates;
    g.append('circle').attr('cx', x(cx)).attr('cy', y(cy)).attr('r', 4.2)
      .attr('fill', '#8b5cf6').attr('stroke', '#fff').attr('stroke-width', 1.5);
  });

  // 岛屿（多边形）
  STATE.geography.islands?.forEach(is => {
    const coords = is.coordinates?.[0] || is.coordinates || [];
    const pts = coords.map(c => x(c[0]) + ',' + y(c[1])).join(' ');
    if (!pts) return;
    g.append('polygon').attr('points', pts)
      .attr('fill', 'rgba(16,185,129,.15)')
      .attr('stroke', '#10b981').attr('stroke-width', 1.2);
  });

  // 轨迹
  if (STATE.mapMode === 'single') {
    drawSingleTrajectory(g, x, y);
  } else {
    drawMultiTrajectory(g, x, y);
  }

  // ---- 缩放/平移（左键拖动 + 滚轮缩放） ----
  const zoom = d3.zoom()
    .scaleExtent([0.5, 10])
    .extent([[0, 0], [width, height]])
    .on('zoom', function(event) {
      g.attr('transform', event.transform);
    });
  svg.call(zoom);
}

function drawSingleTrajectory(g, x, y) {
  const vessel = STATE.vesselById.get(STATE.vesselId);
  if (!vessel) return;
  const pings = getFilteredPings(vessel.vessel_id);
  if (!pings || pings.length === 0) {
    const trans = Object.entries(vessel.transitions || {}).sort((a, b) => b[1] - a[1]).slice(0, 8);
    trans.forEach(([k, count]) => {
      const [from, to] = k.split('->');
      const loc = Object.keys(STATE.locationCoords).find(l =>
        l.toLowerCase().includes(from.toLowerCase()) || l.toLowerCase().includes(to.toLowerCase())
      ) || 'Himark';
      const coord = STATE.locationCoords[loc];
      if (coord) {
        g.append('circle').attr('cx', x(coordLon(coord))).attr('cy', y(coordLat(coord)))
          .attr('r', 5 + Math.min(count, 10)).attr('fill', '#e11d48')
          .attr('opacity', .7).attr('stroke', '#fff').attr('stroke-width', 1.2)
          .style('cursor', 'pointer')
          .append('title').text(loc + ' (' + count + '次)');
        g.append('text').attr('x', x(coordLon(coord)) + 8).attr('y', y(coordLat(coord)) - 8)
          .style('font-size', '8px').style('fill', '#e11d48').style('font-weight', '600')
          .text(loc + ' (' + count + ')');
      }
    });
    return;
  }

  const isSeed = STATE.seedIds.has(vessel.vessel_id);
  const lineColor = isSeed ? '#e11d48' : '#0ea5e9';
  const validPings = pings.filter(isValidPingCoord);
  if (validPings.length === 0) return;
  const lineGen = d3.line().x(d => x(pingLon(d))).y(d => y(pingLat(d))).curve(d3.curveCatmullRom);

  // 轨迹线（可点击）
  const path = g.append('path').datum(validPings).attr('fill', 'none').attr('stroke', lineColor)
    .attr('stroke-width', 1).attr('opacity', .85).attr('d', lineGen)
    .style('cursor', 'pointer');
  path.append('title').text(vessel.vessel_name + ' · ' + pings.length + ' 个定位点');

  // 停留点（可点击）
  const dwellPings = validPings.filter(p => pingDwellHours(p) > 0);
  g.selectAll('.dwell-point').data(dwellPings).enter().append('circle')
    .attr('class', 'dwell-point')
    .attr('cx', d => x(pingLon(d))).attr('cy', d => y(pingLat(d)))
    .attr('r', d => Math.min(8, 2 + pingDwellHours(d) * 0.5))
    .attr('fill', d => d.loc_type === 'protected' ? '#ef4444' : '#f59e0b')
    .attr('opacity', .7).attr('stroke', '#fff').attr('stroke-width', 1.2)
    .style('cursor', 'pointer')
    .append('title').text(d => d.location + ' · 停留 ' + pingDwellHours(d).toFixed(1) + 'h · ' + d.time);

  if (validPings.length > 0) {
    const first = validPings[0], last = validPings[validPings.length - 1];
    g.append('circle').attr('cx', x(pingLon(first))).attr('cy', y(pingLat(first)))
      .attr('r', 5).attr('fill', '#22c55e').attr('stroke', '#fff').attr('stroke-width', 2)
      .append('title').text('起点: ' + first.time);
    g.append('circle').attr('cx', x(pingLon(last))).attr('cy', y(pingLat(last)))
      .attr('r', 5).attr('fill', '#ef4444').attr('stroke', '#fff').attr('stroke-width', 2)
      .append('title').text('终点: ' + last.time);
  }
}

function drawMultiTrajectory(g, x, y) {
  const ids = STATE.selectedVesselIds.length > 0 ? STATE.selectedVesselIds : [STATE.vesselId];
  const color = d3.scaleOrdinal(d3.schemeCategory10);
  ids.forEach((id, i) => {
    const vessel = STATE.vesselById.get(id);
    if (!vessel) return;
    const pings = getFilteredPings(id);
    if (!pings || pings.length === 0) return;
    const validPings = pings.filter(isValidPingCoord);
    if (validPings.length === 0) return;
    const lineGen = d3.line().x(d => x(pingLon(d))).y(d => y(pingLat(d))).curve(d3.curveCatmullRom);
    g.append('path').datum(validPings).attr('fill', 'none').attr('stroke', color(i))
      .attr('stroke-width', 1.2).attr('opacity', .7).attr('d', lineGen)
      .style('cursor', 'pointer')
      .append('title').text(vessel.vessel_name);
    const mid = pings[Math.floor(pings.length / 2)];
    if (mid) {
      g.append('text').attr('x', x(mid.lon)).attr('y', y(mid.lat) - 8)
        .style('font-size', '8px').style('font-weight', '700')
        .style('fill', color(i)).text(vessel.vessel_name);
    }
  });
}

// 时间轴渲染逻辑已迁移至 scripts/timeline.js

// ============================================================
// 渲染：聚类视图（t-SNE 降维）
// ============================================================
function renderCluster() {
  const container = document.getElementById('cluster-viz');
  container.innerHTML = '';
  const { width, height } = getResponsiveSize(container);
  const margin = { top: 20, right: 16, bottom: 28, left: 28 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const svg = d3.select(container).append('svg').attr('width', width).attr('height', height);
  const g = svg.append('g').attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');

  // 使用 t-SNE 坐标（如果已加载）
  let points;
  if (STATE.tsneCoords) {
    points = STATE.tsneCoords.map(d => ({
      id: d.vessel_id,
      name: d.name,
      type: d.type,
      seed: d.is_seed,
      x: d.x,
      y: d.y
    }));
  } else {
    // 回退：使用行为特征手动计算
    const vessels = getFilteredVessels();
    points = vessels.map(v => ({
      id: v.vessel_id, name: v.vessel_name, type: v.vessel_type,
      seed: STATE.seedIds.has(v.vessel_id),
      x: (v.protected_dwell_ratio || 0) * 0.6 + (v.night_fishing_ratio || 0) * 0.3 + ((v.entropy || 0) / 2.5) * 0.1,
      y: ((v.avg_dwell_hours || 0) / 20) * 0.5 + ((v.locations_per_day || 0) / 15) * 0.3 + (v.night_fishing_ratio || 0) * 0.2
    }));
  }

  const xExt = d3.extent(points, d => d.x);
  const yExt = d3.extent(points, d => d.y);
  const xPad = (xExt[1] - xExt[0]) * 0.05 || 1;
  const yPad = (yExt[1] - yExt[0]) * 0.05 || 1;
  const xScale = d3.scaleLinear().domain([xExt[0] - xPad, xExt[1] + xPad]).range([0, innerW]);
  const yScale = d3.scaleLinear().domain([yExt[0] - yPad, yExt[1] + yPad]).range([innerH, 0]);

  // 坐标轴标签
  g.append('text').attr('x', innerW / 2).attr('y', innerH + 18)
    .style('text-anchor', 'middle').style('font-size', '8px').style('fill', '#94a3b8')
    .text('t-SNE 维度 1 (行为相似度 →)');

  g.append('text').attr('x', -14).attr('y', innerH / 2)
    .style('text-anchor', 'middle').style('font-size', '8px').style('fill', '#94a3b8')
    .attr('transform', 'rotate(-90, -14, ' + (innerH / 2) + ')')
    .text('t-SNE 维度 2');

  g.append('g').attr('transform', 'translate(0,' + innerH + ')')
    .call(d3.axisBottom(xScale).ticks(4).tickFormat('')).attr('class', 'axis');
  g.append('g').call(d3.axisLeft(yScale).ticks(4).tickFormat('')).attr('class', 'axis');

  const brush = d3.brush().extent([[0, 0], [innerW, innerH]])
    .on('end', function(event) {
      if (!event.selection) return;
      const [[x0, y0], [x1, y1]] = event.selection;
      const selected = points.filter(d => {
        const px = xScale(d.x), py = yScale(d.y);
        return px >= x0 && px <= x1 && py >= y0 && py <= y1;
      });
      STATE.selectedVesselIds = selected.map(d => d.id);
      if (STATE.mapMode === 'multi') renderMap();
      renderTimeline();
      renderRadar();
      renderEvidence();
      renderSimilar();
      renderStatsCompare();
      renderChordCharts();  // 新增：聚类框选后立即刷新弦图
    });

  g.selectAll('.cluster-point').data(points).enter().append('circle')
    .attr('class', 'cluster-point')
    .attr('cx', d => xScale(d.x)).attr('cy', d => yScale(d.y))
    .attr('r', d => d.seed ? 5 : 2.5)
    .attr('fill', d => d.seed ? '#e11d48' : getVesselTypeColor(d.type))
    .attr('opacity', d => d.seed ? 1 : 0.6)
    .attr('stroke', d => d.seed ? '#fff' : 'none')
    .attr('stroke-width', d => d.seed ? 2 : 0)
    .style('cursor', 'pointer')
    .on('click', function(event, d) {
      STATE.vesselId = d.id;
      const vesselInput = document.getElementById('vessel-input');
      const vessel = STATE.vesselById.get(d.id);
      if (vesselInput && vessel) vesselInput.value = vessel.vessel_name;
      refreshAll();
    })
    .append('title').text(d => d.name + '\n类型: ' + getVesselTypeShort(d.type) + '\n种子船: ' + (d.seed ? '是' : '否'));

  if (STATE.selectedVesselIds.length > 0) {
    const selSet = new Set(STATE.selectedVesselIds);
    g.selectAll('.cluster-point')
      .attr('opacity', d => selSet.has(d.id) ? 1 : 0.2)
      .attr('stroke', d => selSet.has(d.id) ? '#0ea5e9' : 'none')
      .attr('stroke-width', d => selSet.has(d.id) ? 2 : 0);
  }

  g.append('g').attr('class', 'brush').call(brush);

  // ---- 缩放/平移（滚轮缩放，右键拖动） ----
  const zoom = d3.zoom()
    .scaleExtent([0.5, 8])
    .extent([[0, 0], [innerW, innerH]])
    .on('zoom', function(event) {
      g.attr('transform', event.transform);
    })
    .filter(function(event) {
      // 左键：brush（不触发zoom），滚轮：缩放，右键：平移
      if (event.type === 'mousedown' && event.button === 0) return false; // 左键不触发zoom
      if (event.type === 'mousedown' && event.button === 2) return true;  // 右键触发zoom（平移）
      if (event.type === 'wheel') return true;  // 滚轮缩放
      return false;
    });
  svg.call(zoom);

  // 阻止右键菜单
  svg.on('contextmenu', function() { d3.event.preventDefault(); });
}

// ============================================================
// 渲染：雷达图（右侧）
// ============================================================
function renderRadar() {
  const container = document.getElementById('radar-viz');
  container.innerHTML = '';
  const ids = STATE.selectedVesselIds.length > 0 ? STATE.selectedVesselIds : [STATE.vesselId];
  const selectedVessels = ids.map(id => STATE.vesselById.get(id)).filter(Boolean);
  if (selectedVessels.length === 0) {
    container.innerHTML = '<div class="loading" style="min-height:80px">选择船舶后显示</div>';
    return;
  }

  const { width, height } = getResponsiveSize(container);
  const radius = Math.min(width, height) / 2 - 20;
  const svg = d3.select(container).append('svg').attr('width', width).attr('height', height);
  const g = svg.append('g').attr('transform', 'translate(' + (width / 2) + ',' + (height / 2) + ')');

  const dims = [
    { key: 'avg_dwell_hours', label: '停留', max: 20 },
    { key: 'night_fishing_ratio', label: '夜间', max: 1 },
    { key: 'protected_dwell_ratio', label: '保护区', max: 0.5 },
    { key: 'locations_per_day', label: '移动', max: 15 },
    { key: 'entropy', label: '熵值', max: 2.5 }
  ];

  const series = [...selectedVessels];
  const seedFleet = STATE.vessels.filter(v => STATE.seedIds.has(v.vessel_id));
  if (seedFleet.length > 0) {
    const seedAvg = { vessel_id: '__seed_avg__', vessel_name: 'SouthSeafood 平均', __seedAverage: true };
    dims.forEach(dim => {
      seedAvg[dim.key] = avg(seedFleet, dim.key);
    });
    series.push(seedAvg);
  }

  const angleSlice = Math.PI * 2 / dims.length;
  const rScale = d3.scaleLinear().domain([0, 1]).range([0, radius]);

  [0.25, 0.5, 0.75, 1].forEach(level => {
    const r = rScale(level);
    const pts = dims.map((_, i) => {
      const a = angleSlice * i - Math.PI / 2;
      return [r * Math.cos(a), r * Math.sin(a)];
    });
    g.append('polygon').attr('points', pts.map(p => p.join(',')).join(' '))
      .attr('fill', 'none').attr('stroke', '#e2e8f0').attr('stroke-width', 0.5);
  });

  dims.forEach((dim, i) => {
    const a = angleSlice * i - Math.PI / 2;
    g.append('line').attr('x1', 0).attr('y1', 0)
      .attr('x2', rScale(1) * Math.cos(a)).attr('y2', rScale(1) * Math.sin(a))
      .attr('stroke', '#cbd5e1').attr('stroke-width', 1);
    g.append('text').attr('x', rScale(1.1) * Math.cos(a)).attr('y', rScale(1.1) * Math.sin(a))
      .attr('text-anchor', 'middle').attr('dy', '.35em')
      .style('font-size', '7px').style('fill', '#64748b').text(dim.label);
  });

  const palette = ['#0ea5e9', '#6366f1', '#14b8a6', '#f97316', '#8b5cf6'];
  let paletteIndex = 0;
  const legendItems = [];

  series.forEach((v, vi) => {
    const values = dims.map(d => Math.min(1, (v[d.key] || 0) / d.max));
    const pts = values.map((val, i) => {
      const a = angleSlice * i - Math.PI / 2;
      const r = rScale(val);
      return [r * Math.cos(a), r * Math.sin(a)];
    });
    const isSeedAvg = v.__seedAverage === true;
    const isSeedVessel = !isSeedAvg && STATE.seedIds.has(v.vessel_id);
    let strokeColor;
    if (isSeedAvg) {
      strokeColor = '#1e293b';
    } else if (isSeedVessel) {
      strokeColor = '#e11d48';
    } else {
      strokeColor = palette[paletteIndex % palette.length];
      paletteIndex += 1;
    }

    const polygon = g.append('polygon').attr('points', pts.map(p => p.join(',')).join(' '))
      .attr('fill', strokeColor)
      .attr('opacity', isSeedAvg ? 0.08 : 0.12)
      .attr('stroke', strokeColor)
      .attr('stroke-width', isSeedAvg ? 2 : 1.2);
    if (isSeedAvg) {
      polygon.attr('stroke-dasharray', '4,3');
    }
    pts.forEach(p => {
      g.append('circle').attr('cx', p[0]).attr('cy', p[1]).attr('r', 2.5)
        .attr('fill', strokeColor).attr('opacity', isSeedAvg ? 0.9 : 0.8);
    });

    legendItems.push({
      label: isSeedAvg ? '🚨 SouthSeafood 平均' : (v.vessel_name || `对比 ${vi + 1}`),
      color: strokeColor,
      dashed: isSeedAvg
    });
  });

  if (legendItems.length > 0) {
    const legendEl = document.createElement('div');
    legendEl.className = 'radar-legend';
    legendItems.forEach(item => {
      const itemEl = document.createElement('span');
      itemEl.className = 'radar-legend-item' + (item.dashed ? ' dashed' : '');

      const swatch = document.createElement('span');
      swatch.className = 'radar-legend-swatch';
      if (item.dashed) {
        swatch.style.borderTop = `2px dashed ${item.color}`;
      } else {
        swatch.style.background = item.color;
      }

      const text = document.createElement('span');
      text.textContent = item.label;

      itemEl.appendChild(swatch);
      itemEl.appendChild(text);
      legendEl.appendChild(itemEl);
    });
    container.appendChild(legendEl);
  }
}

// ============================================================
// 渲染：船舶档案（右侧）
// ============================================================
function renderProfile() {
  const el = document.getElementById('vessel-profile');
  const v = STATE.vesselById.get(STATE.vesselId);
  if (!v) {
    el.innerHTML = '<div class="loading" style="min-height:60px">选择船舶后显示</div>';
    return;
  }
  const isSeed = STATE.seedIds.has(v.vessel_id);
  el.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
      <span style="font-weight:700;font-size:.85rem">${v.vessel_name}</span>
      <span style="font-size:.7rem;padding:2px 8px;border-radius:12px;background:${isSeed ? '#fef2f2' : '#f0fdf4'};color:${isSeed ? '#b91c1c' : '#15803d'};font-weight:600">${isSeed ? '🚨 SouthSeafood' : '普通船'}</span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:.72rem;color:#475569">
      <span>类型: ${getVesselTypeShort(v.vessel_type)}</span>
      <span>公司: ${v.company || '未知'}</span>
      <span>停留: ${fmtHour(v.avg_dwell_hours || 0)}</span>
      <span>夜间: ${fmtPct(v.night_fishing_ratio || 0)}</span>
      <span>保护区: ${fmtPct(v.protected_dwell_ratio || 0)}</span>
      <span>日移动: ${(v.locations_per_day || 0).toFixed(1)}</span>
    </div>
  `;
}

// ============================================================
// 渲染：证据链（右侧）
// ============================================================
function renderEvidence() {
  const el = document.getElementById('evidence-panel');
  const ids = STATE.selectedVesselIds.length > 0 ? STATE.selectedVesselIds : [STATE.vesselId];
  const vessels = ids.map(id => STATE.vesselById.get(id)).filter(Boolean);
  if (vessels.length === 0) {
    el.innerHTML = '<div class="loading" style="min-height:60px">选择船舶后显示</div>';
    return;
  }

  const items = [];
  vessels.forEach(v => {
    const risk = calcRisk(v);
    const isSeed = STATE.seedIds.has(v.vessel_id);
    if (isSeed) {
      items.push({ vessel: v.vessel_name, text: '🚨 已知违规船，夜间捕鱼率 ' + fmtPct(v.night_fishing_ratio || 0) + '，显著高于船队平均。', severity: 'high' });
    } else {
      items.push({ vessel: v.vessel_name, text: '🔍 与 SouthSeafood 行为模式相似，风险评分 ' + (risk * 100).toFixed(0) + '%。', severity: 'medium' });
    }
    if ((v.protected_dwell_ratio || 0) > 0.05) {
      items.push({ vessel: v.vessel_name, text: '⚠️ 保护区内停留占比 ' + fmtPct(v.protected_dwell_ratio) + '，涉嫌非法捕鱼。', severity: 'high' });
    }
    if ((v.night_fishing_ratio || 0) > 0.5) {
      items.push({ vessel: v.vessel_name, text: '🌙 夜间作业比例高 (' + fmtPct(v.night_fishing_ratio) + ')，规避日间监管。', severity: 'medium' });
    }
    if ((v.avg_dwell_hours || 0) < 3) {
      items.push({ vessel: v.vessel_name, text: '⚡ 平均停留时间短 (' + fmtHour(v.avg_dwell_hours) + ')，快速作业模式。', severity: 'low' });
    }
  });

  el.innerHTML = `
    <div style="display:grid;gap:4px;font-size:.76rem">
      ${items.slice(0, 8).map(d => `
        <div style="padding:5px 8px;border-radius:8px;background:${d.severity === 'high' ? 'rgba(239,68,68,.08)' : d.severity === 'medium' ? 'rgba(245,158,11,.08)' : 'rgba(59,130,246,.08)'};border-left:3px solid ${d.severity === 'high' ? '#ef4444' : d.severity === 'medium' ? '#f59e0b' : '#3b82f6'}">
          <div style="font-weight:600;color:#1e293b">${d.text}</div>
          <div style="font-size:.65rem;color:#64748b;margin-top:2px">${d.vessel}</div>
        </div>
      `).join('')}
    </div>
  `;
}

// ============================================================
// 渲染：相似船排名（右侧）
// ============================================================
function renderSimilar() {
  const el = document.getElementById('similar-vessels');
  const v = STATE.vesselById.get(STATE.vesselId);
  if (!v) {
    el.innerHTML = '<div class="loading" style="min-height:60px">选择船舶后显示</div>';
    return;
  }

  // 计算相似度：基于特征距离
  const features = ['avg_dwell_hours', 'night_fishing_ratio', 'protected_dwell_ratio', 'locations_per_day', 'entropy'];
  const scores = STATE.vessels
    .filter(other => other.vessel_id !== v.vessel_id)
    .map(other => {
      let dist = 0;
      features.forEach(f => {
        const a = v[f] || 0;
        const b = other[f] || 0;
        dist += Math.abs(a - b);
      });
      return { id: other.vessel_id, name: other.vessel_name, score: 1 / (1 + dist), risk: calcRisk(other) };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  el.innerHTML = `
    <div style="display:grid;gap:4px;font-size:.76rem">
      ${scores.map(d => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 8px;border-radius:8px;background:rgba(255,255,255,.76);cursor:pointer"
             onclick="selectVessel('${d.id}')">
          <span style="font-weight:600">${d.name}</span>
          <span style="color:#0ea5e9;font-weight:700">${(d.score * 100).toFixed(0)}%</span>
        </div>
      `).join('')}
    </div>
  `;
}

function selectVessel(id) {
  STATE.vesselId = id;
  const vesselInput = document.getElementById('vessel-input');
  const vessel = STATE.vesselById.get(id);
  if (vesselInput && vessel) vesselInput.value = vessel.vessel_name;
  refreshAll();
}

// ============================================================
// 渲染：底部统计对比
// ============================================================
function renderStatsCompare() {
  const container = document.getElementById('stats-compare');
  container.innerHTML = '';
  const { width, height } = getResponsiveSize(container);
  const margin = { top: 20, right: 16, bottom: 28, left: 40 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const svg = d3.select(container).append('svg').attr('width', width).attr('height', height);
  const g = svg.append('g').attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');

  const ids = STATE.selectedVesselIds.length > 0 ? STATE.selectedVesselIds : [STATE.vesselId];
  const vessels = ids.map(id => STATE.vesselById.get(id)).filter(Boolean);
  const mainVessel = STATE.vesselById.get(STATE.vesselId);

  const categories = [
    { key: 'avg_dwell_hours', label: '停留(h)', max: 20 },
    { key: 'night_fishing_ratio', label: '夜间捕鱼', max: 1 },
    { key: 'protected_dwell_ratio', label: '保护区', max: 0.5 },
    { key: 'locations_per_day', label: '日移动', max: 15 }
  ];

  const x0 = d3.scaleBand().domain(categories.map(d => d.key)).range([0, innerW]).padding(0.3);
  const x1 = d3.scaleBand().domain(['main', 'selected', 'global']).range([0, x0.bandwidth()]).padding(0.1);
  const y = d3.scaleLinear().domain([0, 1]).range([innerH, 0]);

  g.append('g').attr('transform', 'translate(0,' + innerH + ')')
    .call(d3.axisBottom(x0).tickFormat(d => categories.find(c => c.key === d)?.label || d))
    .selectAll('text').attr('transform', 'rotate(-15)').style('text-anchor', 'end')
    .attr('dx', '-.2em').attr('dy', '.2em').style('font-size', '8px');

  g.append('g').call(d3.axisLeft(y).ticks(4).tickFormat(d => (d * 100).toFixed(0) + '%'));

  const globalAvg = {};
  categories.forEach(cat => {
    globalAvg[cat.key] = d3.mean(STATE.vessels, v => Math.min(1, (v[cat.key] || 0) / cat.max)) || 0;
  });

  const hasSelection = STATE.selectedVesselIds.length > 0;

  categories.forEach(cat => {
    const mainVal = mainVessel ? Math.min(1, (mainVessel[cat.key] || 0) / cat.max) : 0;
    const avgVal = hasSelection && vessels.length > 0
      ? d3.mean(vessels, v => Math.min(1, (v[cat.key] || 0) / cat.max)) || 0
      : 0;
    const globalVal = globalAvg[cat.key];

    g.append('rect').attr('x', x0(cat.key) + x1('main')).attr('y', y(mainVal))
      .attr('width', x1.bandwidth()).attr('height', innerH - y(mainVal))
      .attr('fill', '#e11d48').attr('opacity', .85).attr('rx', 3)
      .append('title').text('主船: ' + (mainVal * 100).toFixed(1) + '%');

    // 只有框选了聚集船时才显示蓝色柱
    if (hasSelection) {
      g.append('rect').attr('x', x0(cat.key) + x1('selected')).attr('y', y(avgVal))
        .attr('width', x1.bandwidth()).attr('height', innerH - y(avgVal))
        .attr('fill', '#0ea5e9').attr('opacity', .7).attr('rx', 3)
        .append('title').text('选中平均: ' + (avgVal * 100).toFixed(1) + '%');
    }

    g.append('rect').attr('x', x0(cat.key) + x1('global')).attr('y', y(globalVal))
      .attr('width', x1.bandwidth()).attr('height', innerH - y(globalVal))
      .attr('fill', '#94a3b8').attr('opacity', .5).attr('rx', 3)
      .append('title').text('全局平均: ' + (globalVal * 100).toFixed(1) + '%');
  });

}

// ============================================================
// 弦图渲染模块（位置转移矩阵）
// 颜色与图例保持一致：保护区#ef4444、渔区#f59e0b、港口#3b82f6、导航点#94a3b8、其他#10b981
// ============================================================

// 根据地点名称获取颜色（与图例一致）
function getChordLocationColor(locationName) {
  if (!locationName || typeof locationName !== 'string') return '#10b981';
  const nameLower = locationName.toLowerCase().trim();
  
  const protectedKeywords = ['preserve', 'protected', 'sanctuary', 'ghoti preserve', 'don limpet preserve'];
  for (let kw of protectedKeywords) {
    if (nameLower.includes(kw)) return '#ef4444';
  }
  
  const fishingKeywords = ['beds', 'reef', 'shelf', 'table', 'fishing', 'wrasse beds', 'cod table', 'nemo reef', 'tuna shelf'];
  for (let kw of fishingKeywords) {
    if (nameLower.includes(kw)) return '#f59e0b';
  }
  
  const portKeywords = ['port', 'harbor', 'dock', 'himark', 'paackland', 'lomark', 'south paackland', 'haacklee', 'port grove'];
  for (let kw of portKeywords) {
    if (nameLower.includes(kw)) return '#3b82f6';
  }
  
  const navKeywords = ['nav', 'exit', 'waypoint'];
  for (let kw of navKeywords) {
    if (nameLower.includes(kw)) return '#94a3b8';
  }
  
  return '#10b981';
}

function getLocationCategory(locationName) {
  const color = getChordLocationColor(locationName);
  const colorMap = {
    '#ef4444': '保护区',
    '#f59e0b': '渔区',
    '#3b82f6': '港口',
    '#94a3b8': '导航点',
    '#10b981': '其他'
  };
  return colorMap[color] || '其他';
}

// 从pings中提取位置序列（相邻去重）
function getLocationSequenceFromPings(pings) {
  if (!pings || pings.length === 0) return [];
  const sorted = [...pings].sort((a, b) => new Date(a.time) - new Date(b.time));
  const locations = [];
  for (let i = 0; i < sorted.length; i++) {
    const loc = sorted[i].location;
    if (loc && typeof loc === 'string' && loc.trim() !== '') {
      if (locations.length === 0 || locations[locations.length - 1] !== loc) {
        locations.push(loc);
      }
    }
  }
  return locations;
}

// 构建转移矩阵
function buildTransitionMatrix(locations) {
  if (!locations.length) return { matrix: [], locationNames: [] };
  const uniqueLocs = [];
  const locSet = new Set();
  for (let loc of locations) {
    if (!locSet.has(loc)) {
      locSet.add(loc);
      uniqueLocs.push(loc);
    }
  }
  const n = uniqueLocs.length;
  const matrix = Array(n).fill().map(() => Array(n).fill(0));
  for (let i = 0; i < locations.length - 1; i++) {
    const fromIdx = uniqueLocs.indexOf(locations[i]);
    const toIdx = uniqueLocs.indexOf(locations[i + 1]);
    if (fromIdx !== -1 && toIdx !== -1) {
      matrix[fromIdx][toIdx] += 1;
    }
  }
  return { matrix, locationNames: uniqueLocs };
}

// 获取主船转移数据
function getMainVesselTransitionData() {
  if (!STATE.vesselId) return null;
  const vessel = STATE.vesselById.get(STATE.vesselId);
  if (!vessel) return null;
  const pings = getFilteredPings(vessel.vessel_id);
  if (!pings || pings.length === 0) return null;
  const locSeq = getLocationSequenceFromPings(pings);
  const { matrix, locationNames } = buildTransitionMatrix(locSeq);
  return { matrix, locationNames, vesselName: vessel.vessel_name };
}

// 获取聚集船群聚合转移数据
function getClusterAggregateTransition() {
  let clusterIds = STATE.selectedVesselIds && STATE.selectedVesselIds.length 
    ? [...STATE.selectedVesselIds] : [];
  
  if (STATE.vesselId && clusterIds.includes(STATE.vesselId)) {
    clusterIds = clusterIds.filter(id => id !== STATE.vesselId);
  }
  
  if (clusterIds.length === 0) return null;
  
  const clusterVessels = clusterIds.map(id => STATE.vesselById.get(id)).filter(Boolean);
  if (clusterVessels.length === 0) return null;
  
  const aggregatedMatrixMap = new Map();
  const allLocationSet = new Set();
  
  for (let v of clusterVessels) {
    const pingsV = getFilteredPings(v.vessel_id);
    if (!pingsV || pingsV.length < 2) continue;
    const locSeqV = getLocationSequenceFromPings(pingsV);
    if (locSeqV.length < 2) continue;
    for (let i = 0; i < locSeqV.length - 1; i++) {
      const fromLoc = locSeqV[i];
      const toLoc = locSeqV[i + 1];
      if (fromLoc && toLoc) {
        const key = `${fromLoc}|${toLoc}`;
        aggregatedMatrixMap.set(key, (aggregatedMatrixMap.get(key) || 0) + 1);
        allLocationSet.add(fromLoc);
        allLocationSet.add(toLoc);
      }
    }
  }
  
  if (aggregatedMatrixMap.size === 0) return null;
  
  const locationNames = Array.from(allLocationSet).sort();
  const n = locationNames.length;
  const matrix = Array(n).fill().map(() => Array(n).fill(0));
  const idxMap = new Map(locationNames.map((name, idx) => [name, idx]));
  
  for (let [key, count] of aggregatedMatrixMap.entries()) {
    const [from, to] = key.split('|');
    if (idxMap.has(from) && idxMap.has(to)) {
      matrix[idxMap.get(from)][idxMap.get(to)] += count;
    }
  }
  
  return { matrix, locationNames, vesselCount: clusterVessels.length };
}

// 渲染单个弦图
function renderSingleChordDiagram(containerId, matrix, locationNames) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';
  
  if (!matrix || matrix.length === 0 || matrix.every(row => row.every(v => v === 0))) {
    container.innerHTML = '<div class="chord-placeholder">无有效位置转移数据</div>';
    return;
  }
  
  const width = Math.min(container.clientWidth - 24, 500);
  const height = 260;
  const outerRadius = Math.min(width, height) * 0.42;
  const innerRadius = outerRadius * 0.75;
  
  const svg = d3.select(container)
    .append('svg')
    .attr('width', width)
    .attr('height', height)
    .append('g')
    .attr('transform', `translate(${width / 2}, ${height / 2})`);
  
  const colorMap = new Map();
  locationNames.forEach(name => {
    colorMap.set(name, getChordLocationColor(name));
  });
  
  const chordMatrix = matrix.map(row => [...row]);
  const chordLayout = d3.chord()
    .padAngle(0.05)
    .sortSubgroups(d3.descending)
    .sortChords(d3.descending);
  
  const chords = chordLayout(chordMatrix);
  if (!chords || chords.length === 0) {
    container.innerHTML = '<div class="chord-placeholder">无法构建弦图(数据稀疏)</div>';
    return;
  }
  
  const arc = d3.arc().innerRadius(innerRadius).outerRadius(outerRadius);
  const ribbon = d3.ribbon().radius(innerRadius);
  
  const groupArc = svg.append('g')
    .selectAll('g')
    .data(chords.groups)
    .enter()
    .append('g');
  
  groupArc.append('path')
    .attr('d', arc)
    .attr('fill', d => colorMap.get(locationNames[d.index]))
    .attr('stroke', '#fff')
    .attr('stroke-width', 1.2)
    .style('cursor', 'pointer');
  
  groupArc.append('text')
    .each(function(d) {
      const name = locationNames[d.index];
      const category = getLocationCategory(name);
      const shortName = name.length > 12 ? name.slice(0, 10) + '..' : name;
      const angle = (d.startAngle + d.endAngle) / 2;
      const rad = outerRadius + 12;
      const x = Math.cos(angle) * rad;
      const y = Math.sin(angle) * rad;
      d3.select(this)
        .attr('transform', `translate(${x}, ${y})`)
        .attr('dy', '0.32em')
        .attr('text-anchor', x > 0 ? 'start' : 'end')
        .style('font-size', '7px')
        .style('fill', '#334155')
        .style('font-weight', '500')
        .text(`${shortName} (${category})`);
    });
  
  svg.append('g')
    .selectAll('path')
    .data(chords)
    .enter()
    .append('path')
    .attr('d', ribbon)
    .attr('fill', d => colorMap.get(locationNames[d.source.index]))
    .attr('opacity', 0.65)
    .attr('stroke', '#fff')
    .attr('stroke-width', 0.4)
    .append('title')
    .text(d => {
      const fromLoc = locationNames[d.source.index];
      const toLoc = locationNames[d.target.index];
      const count = matrix[d.source.index][d.target.index];
      const fromCat = getLocationCategory(fromLoc);
      const toCat = getLocationCategory(toLoc);
      return `${fromLoc} [${fromCat}] → ${toLoc} [${toCat}] : ${count} 次转移`;
    });
  
  groupArc.append('title').text(d => {
    const name = locationNames[d.index];
    const cat = getLocationCategory(name);
    const totalOut = matrix[d.index].reduce((a, b) => a + b, 0);
    return `${name} [${cat}]\n总转出次数: ${totalOut}`;
  });
}

// 渲染双弦图
function renderChordCharts() {
  const mainData = getMainVesselTransitionData();
  const mainTitleSpan = document.getElementById('mainChordTitle');
  if (mainData && mainData.matrix && mainData.locationNames.length > 0) {
    if (mainTitleSpan) mainTitleSpan.innerText = mainData.vesselName || '主船';
    renderSingleChordDiagram('chord-main-viz', mainData.matrix, mainData.locationNames);
  } else {
    if (mainTitleSpan) mainTitleSpan.innerText = '无轨迹数据';
    const mainContainer = document.getElementById('chord-main-viz');
    if (mainContainer) mainContainer.innerHTML = '<div class="chord-placeholder">主船无有效停留位置轨迹</div>';
  }
  
  const clusterData = getClusterAggregateTransition();
  const clusterTitleSpan = document.getElementById('clusterChordTitle');
  const clusterContainer = document.getElementById('chord-cluster-viz');
  
  if (clusterData && clusterData.matrix && clusterData.locationNames.length > 0 && 
      clusterData.matrix.some(row => row.some(v => v > 0))) {
    if (clusterTitleSpan) clusterTitleSpan.innerText = `已聚合 ${clusterData.vesselCount} 艘船`;
    renderSingleChordDiagram('chord-cluster-viz', clusterData.matrix, clusterData.locationNames);
  } else {
    if (clusterTitleSpan) clusterTitleSpan.innerText = '未聚类时无数据';
    if (clusterContainer) {
      clusterContainer.innerHTML = '<div class="chord-placeholder">暂无聚集船只，请在聚类视图中框选船舶</div>';
    }
  }
}

// ============================================================
// 刷新 & 事件绑定
// ============================================================
function refreshAll(options) {
  // options: { skipCluster: true } 表示跳过聚类视图重绘
  renderTopBar();
  renderFilters();
  renderMap();
  renderTimeline();
  if (!options?.skipCluster) renderCluster();
  renderRadar();
  renderProfile();
  renderEvidence();
  renderSimilar();
  renderStatsCompare();
  renderChordCharts();  // 新增：渲染弦图
}

function initDashboard() {
  loadAllData().then(() => {
    refreshAll();

    const navEl = document.querySelector('.nav-bar');
    const mainEl = document.querySelector('.main-content');
    const navToggle = document.getElementById('nav-toggle');
    if (navEl && mainEl && navToggle) {
      navToggle.addEventListener('click', () => {
        const hideNav = !navEl.classList.contains('nav-hidden');
        navEl.classList.toggle('nav-hidden', hideNav);
        mainEl.classList.toggle('nav-collapsed', hideNav);
        navToggle.textContent = hideNav ? '☰' : '✕';
        navToggle.setAttribute('aria-expanded', (!hideNav).toString());
      });
    }

    // 顶部：时间预设 + 自定义时间区间
    const timeStartInput = document.getElementById('time-start');
    const timeEndInput = document.getElementById('time-end');

    // 设置默认日期范围
    timeStartInput.value = '2035-02-01';
    timeEndInput.value = '2035-11-29';

    document.querySelectorAll('[data-time]').forEach(btn => {
      btn.onclick = function() {
        document.querySelectorAll('[data-time]').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        STATE.timePreset = this.dataset.time;
        // 清除自定义时间区间
        STATE.customTimeStart = null;
        STATE.customTimeEnd = null;
        // 时间区间改变不重绘聚类视图，保留框选
        refreshAll({ skipCluster: true });
      };
    });

    // 自定义时间区间输入
    timeStartInput.onchange = function() {
      STATE.customTimeStart = this.value ? new Date(this.value) : null;
      STATE.customTimeEnd = timeEndInput.value ? new Date(timeEndInput.value) : null;
      if (STATE.customTimeStart && STATE.customTimeEnd) {
        // 取消预设按钮高亮
        document.querySelectorAll('[data-time]').forEach(b => b.classList.remove('active'));
        STATE.timePreset = 'custom';
        refreshAll({ skipCluster: true });
      }
    };
    timeEndInput.onchange = function() {
      STATE.customTimeStart = timeStartInput.value ? new Date(timeStartInput.value) : null;
      STATE.customTimeEnd = this.value ? new Date(this.value) : null;
      if (STATE.customTimeStart && STATE.customTimeEnd) {
        document.querySelectorAll('[data-time]').forEach(b => b.classList.remove('active'));
        STATE.timePreset = 'custom';
        refreshAll({ skipCluster: true });
      }
    };

    // 船舶选择已由 autocomplete 组件处理（initVesselAutocomplete）

    // 左侧：位置筛选和商品筛选已由 autocomplete 组件处理

    // 左侧：快速过滤（这些会改变聚类数据，需要重绘）
    document.getElementById('filter-seed-only').onchange = function(e) {
      STATE.filterSeedOnly = e.target.checked;
      STATE.selectedVesselIds = []; // 过滤条件变了，清除框选
      refreshAll();
    };
    document.getElementById('filter-protected').onchange = function(e) {
      STATE.filterProtected = e.target.checked;
      // 仅保护区是时间轴过滤，不影响聚类视图和框选
      refreshAll({ skipCluster: true });
    };

    // 地图模式
    document.getElementById('map-mode-single').onclick = function() {
      document.getElementById('map-mode-single').classList.add('active');
      document.getElementById('map-mode-multi').classList.remove('active');
      STATE.mapMode = 'single';
      renderMap();
    };
    document.getElementById('map-mode-multi').onclick = function() {
      document.getElementById('map-mode-multi').classList.add('active');
      document.getElementById('map-mode-single').classList.remove('active');
      STATE.mapMode = 'multi';
      renderMap();
    };

    // 导出
    document.getElementById('export-btn').onclick = function() {
      const v = STATE.vesselById.get(STATE.vesselId);
      const ids = STATE.selectedVesselIds.length > 0 ? STATE.selectedVesselIds : [STATE.vesselId];
      const selectedVessels = ids.map(id => STATE.vesselById.get(id)).filter(Boolean);

      // 构建详细报告
      const report = {
        exportTime: new Date().toISOString(),
        mode: STATE.mode,
        timePreset: STATE.timePreset,
        summary: {
          totalVessels: STATE.vessels.length,
          southseafoodCount: STATE.seedIds.size,
          selectedCount: ids.length
        },
        currentVessel: v ? {
          id: v.vessel_id,
          name: v.vessel_name,
          type: getVesselTypeShort(v.vessel_type),
          company: v.company,
          flag: v.flag_country,
          risk: calcRisk(v),
          riskLevel: getRiskLevel(v),
          isSouthSeafood: STATE.seedIds.has(v.vessel_id),
          indicators: {
            avgDwellHours: v.avg_dwell_hours || 0,
            nightFishingRatio: v.night_fishing_ratio || 0,
            protectedDwellRatio: v.protected_dwell_ratio || 0,
            locationsPerDay: v.locations_per_day || 0,
            entropy: v.entropy || 0,
            pingCount: v.ping_count || 0
          },
          transitions: v.transitions || {}
        } : null,
        selectedVessels: selectedVessels.map(sv => ({
          id: sv.vessel_id,
          name: sv.vessel_name,
          type: getVesselTypeShort(sv.vessel_type),
          company: sv.company,
          risk: calcRisk(sv),
          riskLevel: getRiskLevel(sv),
          isSouthSeafood: STATE.seedIds.has(sv.vessel_id),
          indicators: {
            avgDwellHours: sv.avg_dwell_hours || 0,
            nightFishingRatio: sv.night_fishing_ratio || 0,
            protectedDwellRatio: sv.protected_dwell_ratio || 0,
            locationsPerDay: sv.locations_per_day || 0,
            entropy: sv.entropy || 0,
            pingCount: sv.ping_count || 0
          }
        })),
        evidence: (() => {
          const items = [];
          selectedVessels.forEach(sv => {
            const risk = calcRisk(sv);
            const isSeed = STATE.seedIds.has(sv.vessel_id);
            if (isSeed) items.push({ vessel: sv.vessel_name, text: '已知违规船，夜间捕鱼率 ' + fmtPct(sv.night_fishing_ratio || 0), severity: 'high' });
            if ((sv.protected_dwell_ratio || 0) > 0.05) items.push({ vessel: sv.vessel_name, text: '保护区内停留占比 ' + fmtPct(sv.protected_dwell_ratio), severity: 'high' });
            if ((sv.night_fishing_ratio || 0) > 0.5) items.push({ vessel: sv.vessel_name, text: '夜间作业比例高 (' + fmtPct(sv.night_fishing_ratio) + ')', severity: 'medium' });
            if ((sv.avg_dwell_hours || 0) < 3) items.push({ vessel: sv.vessel_name, text: '平均停留时间短 (' + fmtHour(sv.avg_dwell_hours) + ')', severity: 'low' });
          });
          return items;
        })()
      };

      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'oceanus_report_' + (v?.vessel_name || 'all') + '_' + new Date().toISOString().slice(0,10) + '.json';
      a.click();
      URL.revokeObjectURL(a.href);
    };
  });
}

document.addEventListener('DOMContentLoaded', initDashboard);
