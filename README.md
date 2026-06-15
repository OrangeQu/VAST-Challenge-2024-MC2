# FishEye Analytics — Oceanus 非法渔业调查系统

**VAST Challenge 2024 · Mini Challenge 2 参赛作品**

基于 D3.js 构建的交互式可视化分析平台，用于调查 Oceanus 水域中 SouthSeafood Express Corp 的非法捕捞行为，并帮助 FishEye International 识别潜在违规船舶。

---

## 项目背景

FishEye International 持续收集 Oceanus 岛海域的船舶动向及运输记录数据，并整合至 **CatchNet：Oceanus 知识图谱**平台。SouthSeafood Express Corp 被查获从事非法捕捞（IUU）后，本项目通过地理与时间维度的可视化分析，揭示违规特征，识别相似行为船舶，并追踪曝光前后的行为变化。

---

## 功能模块

| 页面 | 路径 | 功能描述 |
|------|------|----------|
| 调查工作台 | `index.html` | 系统主入口：t-SNE 聚类、地图轨迹、时间轴、证据链、弦图、雷达图 |
| 船货关联 | `pages/q1.html` | Q1：建立船舶与港口出口货物的概率关联，识别季节趋势与异常 |

### 主要可视化组件

- **t-SNE 聚类图** — 对所有船舶行为特征进行降维，支持框选聚集船群
- **地图视图** — 支持单船/多船轨迹，叠加保护区与港口地理信息，区分保护区（红）、渔区（蓝）、港口（黄）、导航点（灰）
- **时间轴视图** — 以位置为纵轴的行程序列，联动报告记录与货物交易事件，可过滤保护区停留段
- **移动模式弦图** — 位置转移共现矩阵，对比主船与聚集船群
- **行为雷达图** — 多维度风险评分（保护区驻留比、夜间捕鱼比、行为熵、平均停留时长）
- **证据链面板** — 汇总选中船舶的可疑行为证据
- **统计对比条** — 主船 vs 选中船群 vs 全局基线的多项指标对比
- **桑基图（Q1）** — 港口 → 鱼种 → 船舶的货物流向可视化，基于 4992 条港口出口记录
- **弦图（Q1）** — 货物流向集中性分析

### 风险评分算法

系统基于以下四项指标对船舶进行综合风险评分（0–1）：

| 指标 | 权重 | 说明 |
|------|------|------|
| 保护区驻留比 | 42% | 在保护区内停留时间占总时间的比例 |
| 夜间作业比 | 28% | 夜间（20:00–06:00）作业时长占比 |
| 平均停留时长 | 14% | 停留时长过短暗示频繁转移 |
| 行为熵 | 16% | 位置转移模式的不规律程度 |

---

## 技术栈

- **前端**：原生 HTML5 / CSS3 / JavaScript (ES6+)
- **可视化库**：[D3.js v7](https://d3js.org/)、[d3-sankey v0.12](https://github.com/d3/d3-sankey)
- **字体**：Google Fonts — Inter
- **数据预处理**：Python 3（`scripts/preprocessing/preprocess.py`）
- **无构建工具**：无需 npm/webpack，直接在浏览器中运行

---

## 目录结构

```
.
├── index.html                        # 调查工作台（主页）
├── pages/
│   └── q1.html                       # 船货关联分析（Q1）
├── scripts/
│   ├── frontend/
│   │   ├── dashboard.js              # 主仪表盘逻辑（状态管理、地图、聚类、弦图、雷达图）
│   │   ├── timeline.js               # 时间轴渲染模块
│   │   └── viz-utils.js              # 公共工具函数
│   ├── preprocessing/
│   │   └── preprocess.py             # 数据预处理脚本
│   └── fix_geography_and_links.py    # 地理与链接修复工具
├── styles/
│   └── main.css                      # 全局样式（玻璃拟态风格）
├── data/
│   ├── raw/
│   │   ├── mc2.json                  # 原始知识图谱数据
│   │   └── Oceanus Information/      # 地理节点数据
│   └── processed/
│       ├── processed_data.json       # 船舶行为统计（含风险指标）
│       ├── vessel_movements.json     # 船舶停留序列
│       ├── geography.json            # 地理坐标与保护区信息
│       ├── tsne_coords.json          # t-SNE 降维坐标
│       └── preprocess_report.json    # 预处理统计报告
└── task.md                           # 赛题说明
```

---

## 快速开始

项目为纯静态网页，无需安装依赖或构建步骤。

### 方法一：VSCode Live Server（推荐）

1. 克隆或下载本仓库
2. 在 VSCode 中安装 **Live Server** 插件
3. 右键 `index.html` → **Open with Live Server**

> 直接双击 `index.html` 在部分浏览器中会因跨域限制无法加载本地 JSON 数据，建议通过 Live Server 或其他本地服务器访问。

### 方法二：Python HTTP 服务器

```bash
# Python 3
python -m http.server 8080
# 然后访问 http://localhost:8080
```

### 数据预处理（可选）

若需从原始数据重新生成处理后文件：

```bash
cd scripts/preprocessing
python preprocess.py
```

预处理脚本从 `data/raw/mc2.json` 读取知识图谱，输出 `data/processed/` 下的各 JSON 文件，并生成 `preprocess_report.json` 汇总处理统计。

---

## 数据说明

- **来源**：VAST Challenge 2024 MC2 官方合成数据集
- **核心文件**：`data/raw/mc2.json`（知识图谱，含船舶、位置、货物、报告节点）
- **规模**：4992 条港口出口记录；时间跨度约 2030–2035 年（虚构时间轴）
- **声明**：所有数据均为**完全合成**，与真实人物、地点或事件无关

---

## 主要分析发现

**Q1 — 船货关联**
- South Paackland、Paackland、Lomark 为核心枢纽港口
- Cod、Wrasse 为最主要出货鱼种
- 8–11 月出货量显著高于其他月份，呈典型季节性集中特征
- 部分船舶存在"港内停留无对应交付记录"的异常，疑似规避正规报关卸货

**Q2 — 违规画像**
- SouthSeafood 旗下船舶Snapper Snatcher在保护区内长时间停留、夜间作业、多次进出保护区、航线多位于保护区附近、缺少港口报告等行为均多于其他船舶

**Q3 — 相似扩展**
- 通过 t-SNE 聚类与行为向量相似度，识别出多艘与 SouthSeafood 行为模式高度相似的非关联船舶

**Q4 — 曝光前后变化**
- 曝光后部分船舶存在非法捕捞行为的船只减少了它们在禁渔区（封闭区域）的停留时间，其时长基本上与普通船只无异，但它们进入该禁渔区的次数却增加了；以及之前一直从事非法行为。但在得知扣押事件后，便转为了正常的捕捞活动等新型可疑行为

---

## 使用说明

1. 在筛选面板中选择船舶或按类型/位置筛选
2. 在 t-SNE 图中框选船群进行批量对比
3. 切换时间区间（全部 / 曝光前 / 曝光后 / 自定义）观察行为变化
4. 点击地图标记查看单船轨迹，时间轴随之联动
5. 证据链面板自动汇总当前选中船舶的可疑记录
6. 使用「导出」按钮保存当前分析状态
