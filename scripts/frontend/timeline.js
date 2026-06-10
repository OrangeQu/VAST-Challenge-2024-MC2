/**
 * Timeline view rendering module
 * Extracted from dashboard.js for better separation of concerns.
 */
(function (window) {
  function renderTimeline() {
    const container = document.getElementById('timeline-viz');
    container.innerHTML = '';
    const { width, height } = getResponsiveSize(container);
    const timelineHeight = height;
    const margin = { top: 30, right: 20, bottom: 50, left: 110 };
    const innerW = width - margin.left - margin.right;

    const svg = d3.select(container).append('svg').attr('width', width).attr('height', timelineHeight);
    const g = svg.append('g').attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');

    const mainVessel = STATE.vesselById.get(STATE.vesselId);
    if (!mainVessel) {
      container.innerHTML = '<div class="loading" style="min-height:200px">选择船舶后显示时间轴</div>';
      return;
    }

    // 获取主船和聚集船群的pings
    const mainPings = getFilteredPings(mainVessel.vessel_id);
    const clusterIds = STATE.selectedVesselIds.length > 0
      ? STATE.selectedVesselIds.filter(id => id !== STATE.vesselId)
      : [];
    const clusterVessels = clusterIds.map(id => STATE.vesselById.get(id)).filter(Boolean);
    const clusterPingsList = clusterVessels.map(v => ({
      vessel: v,
      pings: getFilteredPings(v.vessel_id) || []
    })).filter(d => d.pings.length > 0);

    // ---- 时间范围（取主船和聚集船群的全集） ----
    let allPings = [];
    if (mainPings && mainPings.length > 0) allPings = [...mainPings];
    clusterPingsList.forEach(d => { allPings = allPings.concat(d.pings); });

    // 如果完全没有数据（主船和聚集船都没有），才显示无数据提示
    if (allPings.length === 0) {
      container.innerHTML = '<div class="loading" style="min-height:200px">该船舶暂无定位数据</div>';
      return;
    }
    const timeExtent = d3.extent(allPings, d => new Date(d.time));
    const startDate = timeExtent[0];
    const endDate = timeExtent[1];
    const xScale = d3.scaleTime().domain([startDate, endDate]).range([0, innerW]);

    // ---- 位置颜色映射 ----
    const locationColorMap = {
      'Himark': '#3b82f6', 'Paackland': '#3b82f6', 'Lomark': '#3b82f6',
      'South Paackland': '#3b82f6', 'Haacklee': '#3b82f6', 'Port Grove': '#3b82f6',
      'Ghoti Preserve': '#ef4444', 'Don Limpet Preserve': '#ef4444',
      'Wrasse Beds': '#f59e0b',
      'Cod Table': '#f59e0b',
      'Nemo Reef': '#f59e0b',
      'Tuna Shelf': '#f59e0b',
      'Nav 1': '#94a3b8', 'Nav 2': '#94a3b8', 'Nav 3': '#94a3b8',
      'Nav A': '#94a3b8', 'Nav B': '#94a3b8', 'Nav C': '#94a3b8',
      'Nav D': '#94a3b8', 'Nav E': '#94a3b8',
      'Exit East': '#6b7280', 'Exit North': '#6b7280', 'Exit South': '#6b7280', 'Exit West': '#6b7280'
    };
    function getLocColor(loc) {
      if (!loc) return '#10b981';
      if (locationColorMap[loc]) return locationColorMap[loc];
      for (const [key, color] of Object.entries(locationColorMap)) {
        if (loc.includes(key) || key.includes(loc)) return color;
      }
      return '#10b981';
    }
    function getLocLabel(loc) {
      if (loc === 'Ghoti Preserve' || loc === 'Don Limpet Preserve') return '🔴 ' + loc;
      if (loc === 'Wrasse Beds' || loc === 'Cod Table' || loc === 'Nemo Reef' || loc === 'Tuna Shelf') return '🟠 ' + loc;
      if (loc?.startsWith('Nav') || loc?.startsWith('Exit')) return '⚪ ' + loc;
      return '🔵 ' + loc;
    }

    const protectedPolygons = [];
    const protectedBBoxes = [];
    const protectedCache = new Map();
    if (Array.isArray(STATE.geography?.protected_areas)) {
      STATE.geography.protected_areas.forEach(area => {
        const coords = area.coordinates;
        if (!coords) return;
        const rings = Array.isArray(coords[0]?.[0]) ? coords : [coords];
        rings.forEach(ring => {
          if (!Array.isArray(ring) || ring.length < 3) return;
          const normalized = ring
            .map(pt => Array.isArray(pt) ? [Number(pt[0]), Number(pt[1])] : null)
            .filter(pt => pt && Number.isFinite(pt[0]) && Number.isFinite(pt[1]));
          if (normalized.length < 3) return;
          protectedPolygons.push(normalized);
          let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
          normalized.forEach(([x, y]) => {
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
          });
          protectedBBoxes.push({ minX, maxX, minY, maxY });
        });
      });
    }

    function pointInPolygon(x, y, ring) {
      let inside = false;
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const xi = ring[i][0], yi = ring[i][1];
        const xj = ring[j][0], yj = ring[j][1];
        const intersects = ((yi > y) !== (yj > y)) &&
          (x < ((xj - xi) * (y - yi)) / ((yj - yi) || 1e-12) + xi);
        if (intersects) inside = !inside;
      }
      return inside;
    }

    function isProtectedLonLat(lon, lat) {
      if (!protectedPolygons.length) return false;
      for (let i = 0; i < protectedPolygons.length; i++) {
        const bbox = protectedBBoxes[i];
        if (lon < bbox.minX || lon > bbox.maxX || lat < bbox.minY || lat > bbox.maxY) continue;
        if (pointInPolygon(lon, lat, protectedPolygons[i])) return true;
      }
      return false;
    }

    function isProtectedPing(p) {
      if (!p) return false;
      if (p.loc_type === 'protected' || p.is_protected === true) return true;
      // 按地点名称判断：保护区的名称包含 Preserve
      if (p.location && p.location.includes('Preserve')) return true;
      const lon = typeof p.lon === 'number' ? p.lon : Number(p.lon);
      const lat = typeof p.lat === 'number' ? p.lat : Number(p.lat);
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) return false;
      const key = lon.toFixed(4) + ',' + lat.toFixed(4);
      if (protectedCache.has(key)) return protectedCache.get(key);
      const result = isProtectedLonLat(lon, lat);
      protectedCache.set(key, result);
      return result;
    }

    // ---- 月份参考线 ----
    function drawMonthLines(yStart, yEnd) {
      let mc = new Date(startDate);
      mc.setDate(1);
      mc.setMonth(mc.getMonth() - 1);
      while (mc <= endDate) {
        mc.setMonth(mc.getMonth() + 1);
        if (mc > endDate) break;
        const x = xScale(mc);
        if (x > 0 && x < innerW) {
          g.append('line').attr('x1', x).attr('y1', yStart).attr('x2', x).attr('y2', yEnd)
            .attr('stroke', '#cbd5e1').attr('stroke-dasharray', '4,4').attr('stroke-width', 0.5);
          g.append('text').attr('x', x + 3).attr('y', yStart + 12)
            .attr('font-size', '8px').attr('fill', '#64748b')
            .text((mc.getMonth() + 1) + '月');
        }
      }
    }

    // ---- 绘制单艘船的停留色块行 ----
    function drawDwellRow(y, rowH, pings, label, labelColor, isMain) {
      const barH = Math.max(8, rowH - 4);
      // 船名标签
      g.append('text').attr('x', -8).attr('y', y + barH / 2 + 3)
        .attr('text-anchor', 'end').attr('font-size', '7px')
        .attr('fill', labelColor || '#1e293b').attr('font-weight', isMain ? '800' : '600')
        .text(label);

      // 按位置聚合停留段
      const dwellPings = pings.filter(p => (p.dwell || 0) > 0);
      const locGroups = d3.group(dwellPings, d => d.location);
      const locDurations = Array.from(locGroups, ([loc, items]) => ({
        location: loc,
        totalDwell: d3.sum(items, d => d.dwell || 0),
        pings: items.sort((a, b) => new Date(a.time) - new Date(b.time))
      })).sort((a, b) => b.totalDwell - a.totalDwell);

      locDurations.forEach(locData => {
        const baseColor = getLocColor(locData.location);
        locData.pings.forEach(p => {
          // 地点筛选：模糊匹配（trim + 忽略大小写）
          if (STATE.location !== 'all') {
            const locTrim = p.location?.trim().toLowerCase() || '';
            const filterTrim = STATE.location.trim().toLowerCase();
            if (locTrim !== filterTrim) return;
          }

          // 仅保护区过滤：勾选后只显示保护区的停留色块
          if (STATE.filterProtected && !isProtectedPing(p)) return;

          const t = new Date(p.time);
          const dwellH = (p.dwell || 0) / 3600;
          const x = xScale(t);
          const w = Math.max(2, Math.min(innerW - x, dwellH * 3));
          if (x < innerW && w > 0) {
            const inProtected = isProtectedPing(p);
            const fillColor = inProtected ? '#ef4444' : baseColor;
            const opacity = inProtected ? (isMain ? 0.95 : 0.85) : (isMain ? 0.9 : 0.7);
            const strokeColor = inProtected ? '#991b1b' : 'none';
            const tooltipLines = [
              inProtected ? '保护区' : (locData.location || '未知位置'),
              label,
              '时间: ' + p.time,
              '停留: ' + dwellH.toFixed(1) + 'h'
            ];
            g.append('rect').attr('x', x).attr('y', y).attr('width', w).attr('height', barH)
              .attr('fill', fillColor).attr('opacity', opacity).attr('rx', 2)
              .attr('stroke', strokeColor).attr('stroke-width', inProtected ? 0.6 : 0)
              .append('title')
              .text(tooltipLines.join('\n'));
          }
        });
      });
    }

    // ---- 层高分配 ----
    const layerGap = 8;
    const baseHeights = { e1: 140, e2: 100, e3: 100, e4: 80, e5: 90 };
    const baseTotal = Object.values(baseHeights).reduce((a, b) => a + b, 0) + layerGap * 4;
    const availableH = timelineHeight - margin.top - margin.bottom - 30;
    const scale = Math.max(1, availableH / baseTotal);
    const layerHeights = {};
    for (const [k, v] of Object.entries(baseHeights)) {
      layerHeights[k] = Math.round(v * scale);
    }
    let currentY = 0;

    // ================================================================
    // 第1层：位置与停留 — 主船 + 每艘聚集船一行
    // ================================================================
    const e1 = layerHeights.e1;
    g.append('rect').attr('x', 0).attr('y', currentY).attr('width', innerW).attr('height', e1)
      .attr('fill', '#f8fafc').attr('stroke', '#e2e8f0').attr('stroke-width', 0.5).attr('rx', 4);
    g.append('text').attr('x', -8).attr('y', currentY + 16)
      .attr('text-anchor', 'end').attr('font-size', '10px').attr('font-weight', '700').attr('fill', '#1e293b')
      .text('📍 位置与停留' + (STATE.location !== 'all' ? '  |  筛选: ' + STATE.location : '') + (STATE.filterProtected ? '  |  🛡️ 仅保护区' : ''));
    drawMonthLines(currentY, currentY + e1);

    // 计算行数：主船 + 聚集船
    const totalRows1 = 1 + clusterPingsList.length;
    const rowH1 = Math.min(20, (e1 - 30) / Math.max(totalRows1, 1));

    // 主船行（红色高亮）
    drawDwellRow(currentY + 24, rowH1, mainPings,
      '🔴 ' + mainVessel.vessel_name.slice(0, 14), '#e11d48', true);

    // 聚集船行
    clusterPingsList.forEach((d, idx) => {
      const y = currentY + 24 + (idx + 1) * rowH1;
      if (y + rowH1 > currentY + e1) return; // 超出隐藏
      drawDwellRow(y, rowH1, d.pings,
        d.vessel.vessel_name.slice(0, 14), '#0ea5e9', false);
    });

    currentY += e1 + layerGap;

    // ================================================================
    // 第2层：移动模式 — 主船 vs 聚集船群聚合（两行）
    // ================================================================
    const e2 = layerHeights.e2;
    g.append('rect').attr('x', 0).attr('y', currentY).attr('width', innerW).attr('height', e2)
      .attr('fill', '#fffbeb').attr('stroke', '#e2e8f0').attr('stroke-width', 0.5).attr('rx', 4);
    g.append('text').attr('x', -8).attr('y', currentY + 16)
      .attr('text-anchor', 'end').attr('font-size', '10px').attr('font-weight', '700').attr('fill', '#1e293b')
      .text('🚢 移动模式');
    drawMonthLines(currentY, currentY + e2);

    const rowH2 = Math.min(22, (e2 - 30) / 2);

    // 第1行：主船轨迹
    drawDwellRow(currentY + 24, rowH2, mainPings,
      '🔴 ' + mainVessel.vessel_name.slice(0, 14), '#e11d48', true);

    // 第2行：聚集船群聚合（按时间+位置聚合，透明度=密度）
    if (clusterPingsList.length > 0) {
      const y2 = currentY + 24 + rowH2;
      const barH2 = Math.max(8, rowH2 - 4);
      g.append('text').attr('x', -8).attr('y', y2 + barH2 / 2 + 3)
        .attr('text-anchor', 'end').attr('font-size', '7px')
        .attr('fill', '#0ea5e9').attr('font-weight', '700')
        .text('🔵 船群聚合 (' + clusterPingsList.length + '艘)');

      // 把所有聚集船的pings按时间分桶，统计每个位置的出现次数
      const timeBuckets = {};
      clusterPingsList.forEach(d => {
        d.pings.forEach(p => {
          const t = new Date(p.time);
          const bucketKey = Math.floor(t.getTime() / (24 * 60 * 60 * 1000)); // 按天分桶
          if (!timeBuckets[bucketKey]) timeBuckets[bucketKey] = {};
          if (!timeBuckets[bucketKey][p.location]) timeBuckets[bucketKey][p.location] = 0;
          timeBuckets[bucketKey][p.location]++;
        });
      });

      // 绘制聚合色块
      Object.entries(timeBuckets).forEach(([bucketKey, locs]) => {
        const t = new Date(parseInt(bucketKey) * 24 * 60 * 60 * 1000);
        const total = Object.values(locs).reduce((a, b) => a + b, 0);
        const x = xScale(t);
        if (x < 0 || x > innerW) return;
        // 按位置数量分配宽度
        const locEntries = Object.entries(locs);
        const totalWidth = Math.max(4, Math.min(innerW - x, 20));
        locEntries.forEach(([loc, count], li) => {
          const w = totalWidth * (count / total);
          const opacity = 0.3 + 0.5 * (count / total);
          g.append('rect').attr('x', x).attr('y', y2).attr('width', w).attr('height', barH2)
            .attr('fill', getLocColor(loc)).attr('opacity', opacity).attr('rx', 1)
            .append('title')
            .text(loc + '\n船数: ' + count + '/' + total + '\n日期: ' + t.toISOString().slice(0, 10));
        });
      });
    } else {
      // 无聚集船时显示提示
      const y2 = currentY + 24 + rowH2;
      const barH2 = Math.max(8, rowH2 - 4);
      g.append('text').attr('x', -8).attr('y', y2 + barH2 / 2 + 3)
        .attr('text-anchor', 'end').attr('font-size', '7px')
        .attr('fill', '#94a3b8').attr('font-weight', '600')
        .text('⚪ 无聚集船只');
    }

    currentY += e2 + layerGap;

    // ================================================================
    // 第3层：港口报告 — 主船 + 每艘聚集船一行
    // ================================================================
    const e3 = layerHeights.e3;
    g.append('rect').attr('x', 0).attr('y', currentY).attr('width', innerW).attr('height', e3)
      .attr('fill', '#f0fdf4').attr('stroke', '#e2e8f0').attr('stroke-width', 0.5).attr('rx', 4);
    g.append('text').attr('x', -8).attr('y', currentY + 16)
      .attr('text-anchor', 'end').attr('font-size', '10px').attr('font-weight', '700').attr('fill', '#1e293b')
      .text('📦 港口报告');
    drawMonthLines(currentY, currentY + e3);

    // 获取所有报告
    const reports = STATE.deliveryLinks || [];
    function getVesselReports(vesselName) {
      if (!vesselName) return [];

      return reports
        .filter(r => {
          if (!r) return false;
          if (r.best_match_vessel?.vessel_name === vesselName) return true;
          if (r.vessel_name === vesselName) return true;
          if (Array.isArray(r.candidate_vessels)) {
            return r.candidate_vessels.some(c => c?.vessel_name === vesselName);
          }
          return false;
        })
        .map(r => {
          const matchMeta = {
            type: 'candidate',
            rank: null,
            weight: 0.4,
            company: r.company || '',
            date: r.date,
            date_diff: null
          };

          if (r.best_match_vessel?.vessel_name === vesselName) {
            matchMeta.type = 'best';
            matchMeta.weight = 1;
            matchMeta.company = r.best_match_vessel.company || matchMeta.company;
            matchMeta.date = r.best_match_vessel.date || r.date;
            matchMeta.date_diff = r.best_match_vessel.date_diff ?? null;
          } else if (r.vessel_name === vesselName) {
            matchMeta.type = 'direct';
            matchMeta.weight = 1;
          } else if (Array.isArray(r.candidate_vessels)) {
            const idx = r.candidate_vessels.findIndex(c => c?.vessel_name === vesselName);
            if (idx !== -1) {
              const info = r.candidate_vessels[idx];
              matchMeta.type = 'candidate';
              matchMeta.rank = idx + 1;
              matchMeta.weight = Math.max(0.25, 1 - idx * 0.15);
              matchMeta.company = info?.company || matchMeta.company;
              matchMeta.date = info?.date || matchMeta.date;
              matchMeta.date_diff = info?.date_diff ?? null;
            }
          }

          return { ...r, match_meta: matchMeta };
        });
    }

    const mainReports = getVesselReports(mainVessel.vessel_name);
    const clusterReports = clusterPingsList.map(d => ({
      vessel: d.vessel,
      reports: getVesselReports(d.vessel.vessel_name)
    }));

    const totalRows3 = 1 + clusterReports.length;
    const rowH3 = Math.min(20, (e3 - 30) / Math.max(totalRows3, 1));

    // 主船报告行
    function drawReportRow(y, rowH, reports, label, labelColor, isMain) {
      const barH = Math.max(8, rowH - 4);
      g.append('text').attr('x', -8).attr('y', y + barH / 2 + 3)
        .attr('text-anchor', 'end').attr('font-size', '7px')
        .attr('fill', labelColor || '#1e293b').attr('font-weight', isMain ? '800' : '600')
        .text(label);

      if (reports.length === 0) {
        g.append('text').attr('x', 4).attr('y', y + barH / 2 + 3)
          .attr('font-size', '7px').attr('fill', '#94a3b8')
          .text('无报告');
        return;
      }

      reports.forEach(r => {
        const d = new Date(r.date);
        if (d < startDate || d > endDate) return;
        const x = xScale(d);
        const matchMeta = r.match_meta || {};
        const weight = matchMeta.weight ?? (matchMeta.type === 'candidate' ? 0.4 : 1);
        const tons = (r.qty_tons || 0) * weight;
        const cy = y + barH / 2;
        const side = Math.min(16, Math.max(6, Math.sqrt(Math.max(tons, 0.1)) * 2));
        const halfSide = side / 2;
        const isCandidate = matchMeta.type === 'candidate';
        const baseBlue = '#2563eb';
        const fillColor = isCandidate ? '#60a5fa' : baseBlue;
        const strokeColor = isCandidate ? baseBlue : '#1d4ed8';
        const squareOpacity = isMain ? (isCandidate ? 0.8 : 0.95) : (isCandidate ? 0.65 : 0.8);

        const tooltipLines = [
          label,
          '鱼种: ' + (r.fish_name || '未知'),
          '港口: ' + (r.port || r.location || '未知'),
          '日期: ' + r.date,
          '吨位 (加权): ' + tons.toFixed(1) + 't',
          '原始吨位: ' + (r.qty_tons || 0).toFixed(1) + 't'
        ];
        if (matchMeta.type === 'best') {
          tooltipLines.push('匹配: ✅ 最佳匹配');
        } else if (matchMeta.type === 'direct') {
          tooltipLines.push('匹配: 📄 直接报告关联');
        } else {
          tooltipLines.push('匹配: 🤝 候选第' + (matchMeta.rank || '?') + '位');
        }
        if (matchMeta.date_diff != null) {
          tooltipLines.push('日期差: ' + matchMeta.date_diff + ' 天');
        }

        g.append('rect')
          .attr('x', x - halfSide)
          .attr('y', cy - halfSide)
          .attr('width', side)
          .attr('height', side)
          .attr('fill', fillColor)
          .attr('opacity', squareOpacity)
          .attr('stroke', strokeColor)
          .attr('stroke-width', isCandidate ? 1.5 : 1)
          .append('title')
          .text(tooltipLines.join('\n'));
      });
    }

    drawReportRow(currentY + 24, rowH3, mainReports,
      '🔴 ' + mainVessel.vessel_name.slice(0, 14), '#e11d48', true);

    clusterReports.forEach((d, idx) => {
      const y = currentY + 24 + (idx + 1) * rowH3;
      if (y + rowH3 > currentY + e3) return;
      drawReportRow(y, rowH3, d.reports,
        d.vessel.vessel_name.slice(0, 14), '#0ea5e9', false);
    });

    currentY += e3 + layerGap;

    // ================================================================
    // 第4层：商品关联 — 主船 + 每艘聚集船一行
    // ================================================================
    const e4 = layerHeights.e4;
    g.append('rect').attr('x', 0).attr('y', currentY).attr('width', innerW).attr('height', e4)
      .attr('fill', '#faf5ff').attr('stroke', '#e2e8f0').attr('stroke-width', 0.5).attr('rx', 4);
    g.append('text').attr('x', -8).attr('y', currentY + 16)
      .attr('text-anchor', 'end').attr('font-size', '10px').attr('font-weight', '700').attr('fill', '#1e293b')
      .text('🏷️ 商品关联');
    drawMonthLines(currentY, currentY + e4);

    const commodityColors = {
      'Seafood': '#b91c1c', 'Dry Goods': '#c2410c', 'Electronics': '#b91c1c',
      'Mixed': '#b91c1c', 'Other': '#92400e'
    };

    const commodityPalette = ['#7f1d1d', '#991b1b', '#b91c1c', '#c53030', '#dc2626', '#ef4444', '#f87171', '#fca5a5'];
    const dynamicCommodityColors = new Map();
    function assignCommodityColor(name) {
      if (!name) return '#6b7280';
      if (commodityColors[name]) return commodityColors[name];
      if (!dynamicCommodityColors.has(name)) {
        const idx = dynamicCommodityColors.size % commodityPalette.length;
        dynamicCommodityColors.set(name, commodityPalette[idx]);
      }
      return dynamicCommodityColors.get(name);
    }

    function updateCommodityLegend(labels) {
      const legendInner = document.querySelector('#legend-bar .legend-bar-inner');
      if (!legendInner) return;
      let group = document.getElementById('commodity-legend-group');
      const mergedSet = new Set();
      (labels || []).forEach(label => { if (label) mergedSet.add(label); });
      const reports = Array.isArray(STATE.deliveryReports) ? STATE.deliveryReports : [];
      reports.forEach(r => {
        const label = resolveFishLabel(r);
        if (label) mergedSet.add(label);
      });
      const allLabels = Array.from(mergedSet);
      if (allLabels.length === 0) {
        if (group) group.remove();
        return;
      }
      if (!group) {
        group = document.createElement('div');
        group.className = 'legend-bar-group';
        group.id = 'commodity-legend-group';
        const labelEl = document.createElement('span');
        labelEl.className = 'legend-group-label';
        labelEl.textContent = '🏷️ 商品';
        group.appendChild(labelEl);
        legendInner.appendChild(group);
      }
      while (group.children.length > 1) {
        group.removeChild(group.lastChild);
      }
      allLabels.sort((a, b) => a.localeCompare(b, 'zh-CN'));
      allLabels.forEach(label => {
        const item = document.createElement('span');
        item.className = 'legend-item';
        const swatch = document.createElement('span');
        swatch.className = 'ld';
        swatch.style.background = assignCommodityColor(label);
        item.appendChild(swatch);
        item.appendChild(document.createTextNode(label.length > 10 ? label.slice(0, 8) + '…' : label));
        group.appendChild(item);
      });
    }

    const vesselReportsMap = new Map();
    vesselReportsMap.set(mainVessel.vessel_id, mainReports);
    clusterReports.forEach(({ vessel, reports }) => {
      vesselReportsMap.set(vessel.vessel_id, reports);
    });

    function resolveFishLabel(report) {
      if (!report) return '未分类';
      if (report.fish_name) return report.fish_name;
      if (report.fish_family) return report.fish_family;
      if (report.fish_id) {
        const match = STATE.fishTypes?.find?.(f => f.fish_id === report.fish_id);
        if (match?.fish_name) return match.fish_name;
      }
      return '未分类';
    }

    function pushUnique(arr, value) {
      if (!value) return;
      if (!arr.includes(value)) arr.push(value);
    }

    function getCommodities(v, reports) {
      const base = [];
      if (Array.isArray(v.commodities)) v.commodities.forEach(c => pushUnique(base, c));
      if (v.commodity) pushUnique(base, v.commodity);

      const counts = new Map();
      (reports || []).forEach(r => {
        const label = resolveFishLabel(r);
        const weight = r.qty_tons || 0;
        counts.set(label, (counts.get(label) || 0) + weight);
      });

      const derived = Array.from(counts.entries())
        .sort((a, b) => b[1] - a[1])
        .map(([label]) => label)
        .filter(label => label && label !== '未分类');

      derived.forEach(label => pushUnique(base, label));
      if (base.length === 0 && counts.size > 0) {
        // 若仅有未分类数据，至少展示一个标签
        return Array.from(counts.entries())
          .sort((a, b) => b[1] - a[1])
          .map(([label]) => label || '未分类')
          .slice(0, 4);
      }
      return base.slice(0, 6);
    }

    const allComVessels = [mainVessel, ...clusterVessels];
    const totalRows4 = allComVessels.length;
    const rowH4 = Math.min(22, (e4 - 30) / Math.max(totalRows4, 1));

    const legendCommoditiesSet = new Set();
    const vesselCommodityData = allComVessels.map(v => {
      const reportsForVessel = vesselReportsMap.get(v.vessel_id) || [];
      const dayBuckets = new Map();
      reportsForVessel.forEach(r => {
        const label = resolveFishLabel(r);
        if (!label) return;
        const rawDate = r.match_meta?.date || r.date;
        const dateObj = rawDate ? new Date(rawDate) : null;
        if (!dateObj || isNaN(dateObj)) return;
        const dayKey = dateObj.toISOString().slice(0, 10);
        if (!dayBuckets.has(dayKey)) dayBuckets.set(dayKey, new Map());
        const labelCounts = dayBuckets.get(dayKey);
        const weight = Math.max(0, r.qty_tons || 0);
        labelCounts.set(label, (labelCounts.get(label) || 0) + weight);
        legendCommoditiesSet.add(label);
      });

      const dailyEntries = Array.from(dayBuckets.entries()).map(([day, counts]) => {
        const date = new Date(day + 'T00:00:00');
        const labels = Array.from(counts.entries())
          .sort((a, b) => b[1] - a[1])
          .map(([label, weight]) => ({ label, weight }));
        return { day, date, labels };
      }).sort((a, b) => a.date - b.date);

      const comSet = new Set();
      dailyEntries.forEach(entry => entry.labels.forEach(({ label }) => comSet.add(label)));
      if (comSet.size === 0) {
        getCommodities(v, reportsForVessel).forEach(label => comSet.add(label));
      }

      return { vessel: v, coms: Array.from(comSet), dailyEntries };
    });

    updateCommodityLegend(Array.from(legendCommoditiesSet));

    const squareGap = 3;

    vesselCommodityData.forEach((entry, idx) => {
      const { vessel: v, coms, dailyEntries } = entry;
      const y = currentY + 24 + idx * rowH4;
      if (y + rowH4 > currentY + e4) return;
      const barH = Math.max(6, rowH4 - 4);
      const isMain = v.vessel_id === STATE.vesselId;
      const labelColor = isMain ? '#e11d48' : '#0ea5e9';
      g.append('text').attr('x', -8).attr('y', y + barH / 2 + 3)
        .attr('text-anchor', 'end').attr('font-size', '7px')
        .attr('fill', labelColor).attr('font-weight', isMain ? '800' : '600')
        .text((isMain ? '🔴 ' : '🔵 ') + v.vessel_name.slice(0, 14));
      if (coms.length === 0) {
        g.append('text').attr('x', 4).attr('y', y + barH / 2 + 3)
          .attr('font-size', '7px').attr('fill', '#94a3b8').text('无商品数据');
        return;
      }
      // 商品筛选：如果选了商品，只显示有该商品的船
      if (STATE.commodity !== 'all' && !coms.includes(STATE.commodity)) {
        g.append('text').attr('x', 4).attr('y', y + barH / 2 + 3)
          .attr('font-size', '7px').attr('fill', '#94a3b8').text('无此商品');
        return;
      }

      if (dailyEntries.length === 0) {
        g.append('text').attr('x', 4).attr('y', y + barH / 2 + 3)
          .attr('font-size', '7px').attr('fill', '#94a3b8').text('无报告映射');
        return;
      }

      const squareSize = Math.max(6, Math.min(12, barH - 4));
      const maxRows = Math.max(1, Math.floor(barH / (squareSize + squareGap)));

      dailyEntries.forEach(entryDay => {
        if (entryDay.date < startDate || entryDay.date > endDate) return;
        const baseLabels = entryDay.labels.filter(({ label }) => STATE.commodity === 'all' || label === STATE.commodity);
        if (baseLabels.length === 0) return;

        const gridRows = Math.min(maxRows, baseLabels.length);
        const gridHeight = gridRows * squareSize + (gridRows - 1) * squareGap;
        const baseY = y + (barH - gridHeight) / 2;
        const baseX = xScale(entryDay.date);
        const totalCols = Math.ceil(baseLabels.length / maxRows);
        const leftAnchor = baseX - ((totalCols - 1) * (squareSize + squareGap)) / 2 - squareSize / 2;

        baseLabels.forEach(({ label, weight }, idx2) => {
          const column = Math.floor(idx2 / maxRows);
          const rowIdx = idx2 % maxRows;
          const xPos = leftAnchor + column * (squareSize + squareGap);
          const yPos = baseY + rowIdx * (squareSize + squareGap);
          const color = assignCommodityColor(label);
          const opacity = isMain ? 0.75 : 0.55;
          const weightHint = weight > 0 ? weight.toFixed(1) + 't' : '未知吨位';

          g.append('rect')
            .attr('x', xPos)
            .attr('y', yPos)
            .attr('width', squareSize)
            .attr('height', squareSize)
            .attr('fill', color)
            .attr('opacity', opacity)
            .attr('stroke', '#7f1d1d')
            .attr('stroke-width', 0.4)
            .attr('rx', 2)
            .append('title')
            .text([
              v.vessel_name,
              '日期: ' + entryDay.day,
              '鱼种: ' + label,
              '吨位: ' + weightHint
            ].join('\n'));
        });
      });
    });

    currentY += e4 + layerGap;

    // ================================================================
    // 第5层：交易趋势 — 主船 vs 聚集船群平均（两行）
    // ================================================================
    const e5 = layerHeights.e5;
    g.append('rect').attr('x', 0).attr('y', currentY).attr('width', innerW).attr('height', e5)
      .attr('fill', '#fef2f2').attr('stroke', '#e2e8f0').attr('stroke-width', 0.5).attr('rx', 4);
    g.append('text').attr('x', -8).attr('y', currentY + 16)
      .attr('text-anchor', 'end').attr('font-size', '10px').attr('font-weight', '700').attr('fill', '#1e293b')
      .text('📈 交易趋势');
    drawMonthLines(currentY, currentY + e5);

    // 按天聚合交易量
    function getDailyTons(reports) {
      const map = new Map();
      reports.forEach(r => {
        const d = new Date(r.date);
        if (d < startDate || d > endDate) return;
        const key = d.toISOString().slice(0, 10);
        const weight = r.match_meta?.weight ?? (r.match_meta?.type === 'candidate' ? 0.4 : 1);
        map.set(key, (map.get(key) || 0) + (r.qty_tons || 0) * weight);
      });
      return Array.from(map, ([date, tons]) => ({ date: new Date(date), tons }))
        .sort((a, b) => a.date - b.date);
    }

    const mainDaily = getDailyTons(mainReports);
    // 聚集船群平均
    const clusterDailyMap = new Map();
    clusterReports.forEach(d => {
      getDailyTons(d.reports).forEach(pt => {
        const key = pt.date.toISOString().slice(0, 10);
        if (!clusterDailyMap.has(key)) clusterDailyMap.set(key, []);
        clusterDailyMap.get(key).push(pt.tons);
      });
    });
    const clusterDaily = Array.from(clusterDailyMap, ([date, tons]) => ({
      date: new Date(date),
      tons: d3.mean(tons) || 0
    })).sort((a, b) => a.date - b.date);

    const allDaily = [...mainDaily, ...clusterDaily];
    const maxTons = allDaily.length > 0 ? d3.max(allDaily, d => d.tons) || 1 : 1;
    const yScale5 = d3.scaleLinear().domain([0, maxTons * 1.1]).range([e5 - 20, 8]);

    // 主船折线（红色）
    if (mainDaily.length > 0) {
      const lineGen = d3.line()
        .x(d => xScale(d.date))
        .y(d => currentY + yScale5(d.tons))
        .curve(d3.curveMonotoneX);

      g.append('path').datum(mainDaily).attr('d', lineGen)
        .attr('fill', 'none').attr('stroke', '#e11d48').attr('stroke-width', 2);

      mainDaily.forEach(d => {
        g.append('circle').attr('cx', xScale(d.date)).attr('cy', currentY + yScale5(d.tons))
          .attr('r', 3).attr('fill', '#e11d48').attr('opacity', 0.8)
          .append('title').text('主船\n' + d.date.toISOString().slice(0, 10) + '\n' + d.tons.toFixed(1) + 't');
      });
    }

    // 聚集船群平均折线（蓝色）
    if (clusterDaily.length > 0) {
      const lineGen = d3.line()
        .x(d => xScale(d.date))
        .y(d => currentY + yScale5(d.tons))
        .curve(d3.curveMonotoneX);

      g.append('path').datum(clusterDaily).attr('d', lineGen)
        .attr('fill', 'none').attr('stroke', '#0ea5e9').attr('stroke-width', 1.5).attr('stroke-dasharray', '4,3');

      clusterDaily.forEach(d => {
        g.append('circle').attr('cx', xScale(d.date)).attr('cy', currentY + yScale5(d.tons))
          .attr('r', 2.5).attr('fill', '#0ea5e9').attr('opacity', 0.6)
          .append('title').text('船群平均\n' + d.date.toISOString().slice(0, 10) + '\n' + d.tons.toFixed(1) + 't');
      });
    }

    if (allDaily.length === 0) {
      g.append('text').attr('x', innerW / 2).attr('y', currentY + e5 / 2)
        .attr('text-anchor', 'middle').attr('font-size', '11px').attr('fill', '#94a3b8')
        .text('无交易数据');
    }

    // ---- 底部日期轴 ----
    const bottomAxis = d3.axisBottom(xScale).ticks(8).tickFormat(d3.timeFormat('%m/%d'));
    g.append('g').attr('transform', 'translate(0,' + (currentY + e5 + 5) + ')')
      .call(bottomAxis).selectAll('text')
      .attr('font-size', '8px').attr('transform', 'rotate(-20)').style('text-anchor', 'end');
  }

  window.renderTimeline = renderTimeline;
})(window);
