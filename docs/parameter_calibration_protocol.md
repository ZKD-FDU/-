# 洪策参数校准协议

本协议用于把应急管理部案例、QGIS 空间包和专家意见转成洪策仿真参数。目标不是给出单一“真值”，而是形成可复核、可更新、可用于不确定性分析的参数范围。

## 数据来源标签

| 标签 | 含义 | 使用方式 |
| --- | --- | --- |
| `CASE_DERIVED` | 来自应急管理部案例报告的事实字段、流程断点或合理推断 | 可进入参数库，但正式引用前需回到 PDF 原文复核 |
| `QGIS_DERIVED` | 来自 QGIS 空间包的路线、风险区、桥梁、避难点覆盖 | 可直接影响仿真配置；质量取决于图层真实性 |
| `EXPERT_PRIOR` | 专家给出的参数范围或领域常识先验 | 用于填补案例未披露字段，需记录专家复核时间 |
| `SYNTHETIC_ASSUMPTION` | 临时合成假设 | 只用于演示或敏感性分析，不作为实证结论 |
| `SIMULATION_OUTPUT` | 仿真运行结果 | 只能由仿真内核生成，不能手写固定结果 |

## 参数库结构

当前参数库输出位置：

```text
data/parameters/mem_case_parameter_library.json
```

重建命令：

```bash
python3 scripts/build_mem_parameter_library.py
```

每个案例记录包含：

- `case_id`
- `case_name`
- `scenario_class`
- `actor_chain`
- `state_machine`
- `failure_modes`
- `intervention_points`
- `observed_outcomes`
- `parsed_outcomes`
- `parameter_estimates`
- `calibration_readiness`

每个参数估计包含：

- `name`
- `value_min`
- `value_max`
- `unit`
- `source_label`
- `confidence`
- `rationale`
- `evidence_keys`
- `review_status`

## 核心参数

| 参数 | 解释 | 进入仿真的方式 |
| --- | --- | --- |
| `warning_lead_minutes` | 预警相对危险到达的提前量 | 推导 `warning_minute` |
| `evacuation_order_delay_minutes` | 从预警到明确转移命令的延迟 | 推导 `evacuation_order_minute` |
| `response_activation_delay_minutes` | 风险识别到响应启动的延迟 | 用于政策实验和状态机解释 |
| `communication_failure_rate` | 目标人群未触达或延迟触达比例 | 进入仿真通信失败率 |
| `grassroots_call_strength` | 网格员、村居、机构负责人叫应强度 | 进入 S3/S5 与 RL 决策解释 |
| `vulnerable_priority_weight` | 脆弱人群转移优先权重 | 进入资源优先分配和公平约束 |
| `bridge_closure_threshold` | 桥梁/涵洞风险关闭阈值 | 与 QGIS 桥梁风险叠加 |
| `route_failure_probability` | 路线失效或绕行概率 | 与 QGIS 路线暴露叠加 |
| `shelter_capacity_pressure` | 避难需求相对容量压力 | 影响床位约束和等待时间 |
| `public_trust_delta_prior` | 群众满意度/制度信任变化先验 | 用于社会反馈指标 |
| `casualty_rate_anchor` | 伤亡严重度锚点 | 用于校准风险损失权重 |
| `property_loss_rate_anchor` | 财产损失严重度锚点 | 用于校准财产损失权重 |

## 复核流程

1. 自动构建初版参数库。
2. 对 `missing_review_items` 排序，优先复核转移人数、预警时间、响应升级时间、伤亡和直接损失。
3. 回到 PDF 原文或权威网页，填补具体时间线和转移规模。
4. 用 QGIS 空间包校准路线时间、风险区覆盖、桥梁依赖和避难容量。
5. 请专家复核洪涝致灾因子范围，例如雨强、水位上涨速度、积水深度、桥涵风险阈值。
6. 将复核后的参数重新进入 `data/parameters/`，再运行 S0-S5、参数优化、Bandit/RL 对比。

## 验证实验

每次参数库更新后至少运行：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m hongce.cli batch --policies S0,S3,S5 --seeds 202608060:202608065 --population 500 --out-dir outputs/calibration_check
```

建议输出四类对比：

- S0-S5 政策对比
- 参数优化策略对比
- Contextual Bandit 推荐策略对比
- 消融实验：去掉网格叫应、脆弱优先、QGIS 空间约束、通信失败

## 当前限制

当前参数库由自动抽取和规则推断生成，平均置信度不应被解释为“实证精确度”。它的作用是建立可追踪的参数框架，让后续人工复核、专家校准和空间校准有明确落点。
