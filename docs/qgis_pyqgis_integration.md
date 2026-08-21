# 洪策 QGIS/PyQGIS 高级联动

目标：用 QGIS/PyQGIS 自动批量生成路线、风险区叠加、避难点覆盖范围，再把空间结果转成洪策仿真参数。

## 图层约定

QGIS 工程建议包含这些图层：

| 图层名 | 几何 | 必要字段 | 用途 |
| --- | --- | --- | --- |
| `villages` | 点/面 | `id`, `name`, `population`, `vulnerable_population` | 村居、街镇、机构或人员聚集点 |
| `shelters` | 点/面 | `id`, `name`, `capacity` | 避难点容量与覆盖 |
| `risk_zones` | 面 | `id`, `name`, `risk_score` 或 `level` | 洪涝、山洪、滑坡、积水等风险区 |
| `roads` | 线 | 可选 | 后续替换为真实道路网络最短路径 |
| `bridges` | 点/线 | `id`, `name`, `risk_score` | 桥梁、涵洞、道路断点暴露 |

`risk_score` 范围为 `0-1`。如果只有 `level`，脚本会把 `低/中/高/极高` 映射为 `0.25/0.5/0.75/0.95`。

## 生成空间包

在安装 QGIS 的机器上运行：

```bash
/Applications/QGIS.app/Contents/MacOS/bin/python3 scripts/qgis_build_spatial_package.py \
  --project data/qgis/hongce.qgz \
  --out data/spatial/qingyuan \
  --places villages \
  --shelters shelters \
  --risk-zones risk_zones \
  --roads roads \
  --bridges bridges
```

输出：

```text
data/spatial/qingyuan/spatial_package.json
```

当前脚本会为每个地点匹配最近避难点，计算路线距离、预计转移分钟、是否穿越高风险区、桥梁暴露分数和避难点覆盖率。后续如果道路网字段完备，可以在同一脚本里把路线计算替换为 QGIS `native:shortestpathpointtopoint` 或网络分析模块。

## 接入洪策 API

推导空间场景参数：

```bash
curl -s http://127.0.0.1:8000/spatial/derive-scenario \
  -H 'content-type: application/json' \
  -d '{"spatial_package_path":"data/spatial/qingyuan"}'
```

带空间包运行仿真：

```bash
curl -s http://127.0.0.1:8000/simulations/run \
  -H 'content-type: application/json' \
  -d '{
    "policy_id": "S5",
    "seed": 20260821,
    "population": 500,
    "spatial_package_path": "data/spatial/qingyuan",
    "output_dir": "outputs/api"
  }'
```

空间包会自动映射到这些仿真参数：

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

如果请求里同时给了 `scenario_overrides`，手动参数优先，用于做 what-if 调参。

## 研究解释

空间联动后的仿真含义是：

- 风险区叠加影响危险到达时间、通信失败率和桥梁封闭时刻。
- 避难点容量直接进入 `shelter_beds`，一个床位对应一个人。
- 路线耗时和高风险路线比例影响预警提前量与资源压力。
- 脆弱人口字段影响合成智能体的脆弱群体比例。

所有政策比较仍由洪策本地仿真内核运行产生，不使用固定演示数据。
