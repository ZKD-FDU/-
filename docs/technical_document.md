# 洪策技术文档

## 数据模型

核心合同见 `src/hongce/models.py`：

- 人：年龄、行动能力、照护依赖、数字可达、信任、误报记忆、转移成本、拒绝倾向。
- 机构：养老院、医院、学校避难点。
- 基础设施：堤防、桥梁、道路、通信、电力、避难点。
- 网络：家庭、邻里、机构、行政、志愿者、线上层。
- 状态机：未接触、已接触、确认、等待转移、途中、安置，以及漏管、联系失败、误解、不信任、拒绝、资源阻塞、路线阻塞等失败状态。

所有事实、合成数据、仿真结果分别用 `FACT`、`SYNTHETIC`、`SIMULATED` 标注。当前 MVP 不声称使用真实个人数据。

## 政策方案

- S0：基线单向通知。
- S1：设施优先加固。
- S2：数字预警前移。
- S3：网格叫应确认。
- S4：资源集中调拨。
- S5：韧性综合方案。

S0、S3、S5 已作为端到端 MVP 主线完成，S1、S2、S4 作为扩展和消融方案补齐。

## 指标

- `safe_before_danger_rate`：危险到达前进入安置状态比例。
- `vulnerable_harm_risk`：脆弱群体平均伤害风险。
- `lead_time_minutes_median`：安置相对危险到达的中位提前量。
- `response_closure_rate`：确认、等待、转运、安置等闭环动作覆盖率。
- `missed_critical_action_rate`：危险前仍停留在漏管、联系失败、拒绝、阻塞等状态的比例。
- `group_safety_gap`：脆弱群体与非脆弱群体安全率差异。
- `trust_delta`：仿真中信任变化均值。
- `resource_queue_minutes_mean`：资源等待分钟均值。

## 验证命令

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m hongce.cli run --policy S5 --seed 20260806 --population 500 --out-dir outputs/demo
PYTHONPATH=src python3 -m hongce.cli experiments --seeds 202608060:202608063 --population 500 --out-dir outputs/experiments
PYTHONPATH=src python3 -m api.simple_server
cd web && python3 -m http.server 5173 --bind 127.0.0.1
```
