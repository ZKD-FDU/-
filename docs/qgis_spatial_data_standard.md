# 洪策 QGIS 空间数据标准

本标准用于把 QGIS 工程转成可驱动仿真的 `spatial_package.json`。空间数据越真实，仿真中的路线时间、桥梁封闭、避难点覆盖和资源压力越可信。

## 图层要求

| 图层 | 几何 | 必填字段 | 推荐字段 |
| --- | --- | --- | --- |
| `villages` | 点或面 | `id`, `name`, `population`, `vulnerable_population` | `elevation_m`, `river_distance_m`, `hazard_exposure`, `administrative_level` |
| `shelters` | 点或面 | `id`, `name`, `capacity` | `service_radius_minutes`, `care_capacity`, `backup_power`, `medical_support` |
| `risk_zones` | 面 | `id`, `name`, `risk_score` 或 `level` | `hazard_type`, `depth_m`, `velocity_mps` |
| `rivers` | 线 | `id`, `name` | `kind`, `flow_direction`, `risk_score` |
| `roads` | 线 | 无硬性必填 | `speed_kmh`, `road_class`, `oneway` |
| `bridges` | 点或线 | `id`, `name`, `risk_score` | `closure_threshold`, `bridge_type` |

`risk_score` 建议使用 `0-1`。如果只有 `level`，脚本会映射为：

| level | risk_score |
| --- | ---: |
| 低 / low | 0.25 |
| 中 / medium | 0.50 |
| 高 / high | 0.75 |
| 极高 / extreme | 0.95 |

## 空间包字段

生成命令：

```bash
/Applications/QGIS.app/Contents/MacOS/bin/python3 scripts/qgis_build_spatial_package.py \
  --project data/qgis/hongce.qgz \
  --out data/spatial/qingyuan \
  --places villages \
  --shelters shelters \
  --risk-zones risk_zones \
  --roads roads \
  --bridges bridges \
  --rivers rivers
```

输出文件：

```text
data/spatial/qingyuan/spatial_package.json
```

空间包会包含：

- `places`
- `shelters`
- `risk_zones`
- `rivers`
- `bridges`
- `routes`
- `coverage`
- `quality`

路线字段包括：

- `route_distance_m`
- `travel_minutes`
- `risk_exposure_minutes`
- `bridge_dependency`
- `risk_zone_dependency`
- `bridge_exposure_score`
- `crosses_high_risk`
- `coordinates`
- `route_engine`

河流字段包括：

- `coordinates`
- `kind`
- `flow_direction`
- `risk_score`

避难点字段包括：

- `capacity`
- `service_radius_minutes`
- `care_capacity`
- `backup_power`
- `medical_support`

风险区字段包括：

- `risk_score`
- `hazard_type`
- `depth_m`
- `velocity_mps`
- `polygon`

## 质量评分

`quality.spatial_quality_score` 根据以下检查形成：

- 是否有人口字段
- 是否有脆弱人口字段
- 是否有避难容量字段
- 是否有风险区叠加
- 是否有桥梁图层
- 是否使用 QGIS 网络路径
- 是否输出风险暴露分钟

评分只代表空间包完备度，不代表现实准确度。正式比赛展示时，建议至少达到：

```text
spatial_quality_score >= 0.70
```

## 与仿真的映射

空间包会推导这些仿真参数：

- `vulnerable_ratio`
- `warning_minute`
- `evacuation_order_minute`
- `bridge_closure_minute`
- `danger_arrival_minute`
- `communication_failure_minute`
- `communication_failure_rate`
- `vehicles`
- `care_workers`
- `stretchers`
- `shelter_beds`

映射逻辑：

- 高风险区平均风险越高，危险到达越早。
- 河流线按上游到下游顺序保存，前端会据此显示流向。
- 涵洞/桥梁应落在河流或支沟与道路交汇处；否则空间包虽然可运行，但不应作为严肃地理证据。
- 高风险路线占比越高，桥梁封闭和绕行压力越大。
- 路线时间越长，所需预警提前量越大。
- 避难点覆盖缺口越大，通信失败和资源排队风险越高。
- 避难点容量直接进入床位约束；一个床位对应一个人。

## 当前清源样例的水系假设

当前样例采用“清源河主槽自西向东流”的拓扑假设。四类核心对象按以下逻辑定位：

- `north_valley` 北谷村位于北岸高台，距主河道约 1200 米，默认不做全村强制转移；仿真中只把脆弱人群预转移或道路隔离风险纳入转移对象。
- `qingyuan_town` 清源镇位于镇区台地，承担指挥与资源支撑功能，只针对低洼街区和行动不便人群触发转移。
- `south_valley` 南谷村贴近南支沟，受支沟倒灌和南涵洞溢流影响，是优先转移村庄；其关键路线必须依赖 `bridge_south` 南涵洞。
- `nursing_home` 青松养老照料中心位于主河道低地，是强制优先转移对象；其去往北岸高地学校避难点的路线依赖 `bridge_east` 东桥。

避难与安置点目前设置为：`school_shelter` 位于北岸高地，适合承接养老中心和北侧预转移对象；`gym_shelter` 位于南部高地，适合承接南谷村并减少跨主河道转移。后续替换真实 QGIS 数据时，应优先校准这四个村居/机构、两处避难点、东桥和南涵洞之间的相对位置。

## 数据迭代建议

优先级如下：

1. 用真实村居、养老机构、学校、医院和避难点位置替代手绘点。
2. 用真实道路网络替代直线连接。
3. 添加河流/支沟图层，并确保河流坐标顺序表示真实流向。
4. 给桥梁/涵洞补 `risk_score`、`closure_threshold`，并检查其是否位于道路与河流/支沟交汇处。
5. 把风险区拆成河道漫溢、积水、山洪沟、低洼路段等类型。
6. 给避难点补照护容量、医疗支持、备用电源。
7. 对关键路线人工核验时间，形成 QGIS 与实地认知的一致校准。

## 当前限制

当前系统可以读取旧版空间包；缺失的新字段会被默认值或质量评分吸收。只有当路线、桥梁、风险区和避难点字段足够真实时，空间推演结果才适合作为严肃政策比较证据。
