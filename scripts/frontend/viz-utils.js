/**
 * FishEye Analytics - Shared Visualization Utilities
 * VAST Challenge 2024 MC2
 */

// ============================================================
// Color Schemes
// ============================================================
const COLORS = {
    southseafood: '#ef4444',
    southseafood2: '#f97316',
    normal: '#3b82f6',
    normal2: '#06b6d4',
    protected: '#10b981',
    fishing: '#f59e0b',
    city: '#8b5cf6',
    
    // For categorical data
    category: d3.schemeCategory10,
    
    // Gradients
    gradient: ['#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#f97316', '#ef4444'],
    
    // Time of day
    day: '#fbbf24',
    night: '#1e293b',
    
    // Severity
    low: '#10b981',
    medium: '#f59e0b',
    high: '#ef4444'
};

// ============================================================
// Data Loading
// ============================================================
const DATA_PATH_PREFIX = (() => {
    if (typeof window === 'undefined' || !window.location) return '';
    const path = window.location.pathname || '';
    return path.includes('/pages/') ? '../' : '';
})();

function resolveDataUrl(relativePath) {
    if (!relativePath) return relativePath;
    if (/^(?:https?:)?\/\//i.test(relativePath)) return relativePath;
    return DATA_PATH_PREFIX + relativePath.replace(/^\/*/, '');
}

async function loadProcessedData() {
    const primaryUrl = resolveDataUrl('data/processed/processed_data.json');
    const fallbackUrl = resolveDataUrl('data/origin_data_process/processed_data.json');

    let data = null;
    let primaryError = null;

    try {
        const response = await fetch(primaryUrl);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status} ${response.statusText}`);
        }
        data = await response.json();
    } catch (err) {
        primaryError = err;
        console.warn('加载 data/processed_data_v2.json 失败，准备使用 origin_data_process 备份：', err);
    }

    if (!data || !Array.isArray(data.delivery_vessel_links) || !Array.isArray(data.delivery_reports)) {
        try {
            const fallbackResp = await fetch(fallbackUrl);
            if (!fallbackResp.ok) {
                throw new Error(`HTTP ${fallbackResp.status} ${fallbackResp.statusText}`);
            }
            const full = await fallbackResp.json();
            if (!data) {
                data = full;
            } else {
                data.delivery_vessel_links = full.delivery_vessel_links || data.delivery_vessel_links || [];
                data.delivery_reports = full.delivery_reports || data.delivery_reports || [];
                if (!Array.isArray(data.fish_types) && Array.isArray(full.fish_types)) {
                    data.fish_types = full.fish_types;
                }
                Object.keys(full).forEach(key => {
                    if (!(key in data)) {
                        data[key] = full[key];
                    }
                });
            }
        } catch (fallbackErr) {
            console.error('加载 origin_data_process/processed_data_v2.json 失败：', fallbackErr);
            if (primaryError) {
                throw primaryError;
            }
            throw fallbackErr;
        }
    }

    return data;
}

async function loadVesselMovements() {
    const response = await fetch(resolveDataUrl('data/processed/vessel_movements.json'));
    return await response.json();
}

async function loadVesselMovementsV1() {
    const response = await fetch(resolveDataUrl('data/processed/vessel_movements.json'));
    return await response.json();
}

async function loadGeography() {
    const response = await fetch(resolveDataUrl('data/processed/geography.json'));
    return await response.json();
}



// ============================================================
// SVG Helpers
// ============================================================
function createSVG(container, width, height, margin = {}) {
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .append('g')
        .attr('transform', `translate(${margin.left || 0}, ${margin.top || 0})`);
    return svg;
}

function createTooltip() {
    return d3.select('body')
        .append('div')
        .attr('class', 'tooltip')
        .style('opacity', 0);
}

function showTooltip(tooltip, html, event) {
    tooltip.transition()
        .duration(200)
        .style('opacity', 1);
    tooltip.html(html)
        .style('left', (event.pageX + 10) + 'px')
        .style('top', (event.pageY - 10) + 'px');
}

function hideTooltip(tooltip) {
    tooltip.transition()
        .duration(500)
        .style('opacity', 0);
}

// ============================================================
// Axis Helpers
// ============================================================
function createAxis(svg, xScale, yScale, width, height, margin) {
    // X axis
    svg.append('g')
        .attr('transform', `translate(0, ${height})`)
        .call(d3.axisBottom(xScale))
        .attr('class', 'axis');
    
    // Y axis
    svg.append('g')
        .call(d3.axisLeft(yScale))
        .attr('class', 'axis');
    
    // Grid lines
    svg.append('g')
        .attr('class', 'grid')
        .call(d3.axisLeft(yScale)
            .tickSize(-width)
            .tickFormat('')
        );
}

// ============================================================
// Legend
// ============================================================
function createLegend(container, items) {
    const legend = d3.select(container)
        .append('div')
        .attr('class', 'legend');
    
    items.forEach(item => {
        const div = legend.append('div')
            .attr('class', 'legend-item');
        
        div.append('div')
            .attr('class', 'legend-color')
            .style('background', item.color);
        
        div.append('span')
            .text(item.label);
    });
}

// ============================================================
// Responsive Sizing
// ============================================================
function getResponsiveSize(container) {
    const rect = container.getBoundingClientRect();
    return {
        width: Math.max(200, rect.width - 40),
        height: Math.max(180, rect.height - 20)
    };
}


// ============================================================
// Date Parsing
// ============================================================
function parseDate(dateStr) {
    if (!dateStr) return null;
    // Handle formats: "2035-09-16T04:06:48.185987" or "2035-11-03"
    if (dateStr.includes('T')) {
        return new Date(dateStr);
    }
    return new Date(dateStr + 'T00:00:00');
}

function getMonth(dateStr) {
    const d = parseDate(dateStr);
    return d ? d.getMonth() : 0;
}

function getWeek(dateStr) {
    const d = parseDate(dateStr);
    if (!d) return 0;
    const start = new Date(d.getFullYear(), 0, 1);
    const diff = d - start;
    return Math.ceil((diff / 86400000 + start.getDay() + 1) / 7);
}

// ============================================================
// Statistics
// ============================================================
function calculateStats(values) {
    const sorted = values.slice().sort(d3.ascending);
    const n = sorted.length;
    return {
        min: sorted[0],
        max: sorted[n - 1],
        mean: d3.mean(sorted),
        median: d3.median(sorted),
        q1: d3.quantile(sorted, 0.25),
        q3: d3.quantile(sorted, 0.75),
        sd: d3.deviation(sorted)
    };
}

// ============================================================
// Animation
// ============================================================
function animatePath(path, duration = 1000) {
    const totalLength = path.node().getTotalLength();
    path
        .attr('stroke-dasharray', totalLength + ' ' + totalLength)
        .attr('stroke-dashoffset', totalLength)
        .transition()
        .duration(duration)
        .ease(d3.easeLinear)
        .attr('stroke-dashoffset', 0);
}

// ============================================================
// Formatting
// ============================================================
function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toFixed(0);
}

function formatDate(dateStr) {
    const d = parseDate(dateStr);
    if (!d) return dateStr;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatPercent(val) {
    return (val * 100).toFixed(1) + '%';
}
