# 阶段验证报告

## 阶段 0

- 已实现：工作区审计、方案阅读、数据标签、状态机、S0/S3/S5 MVP 范围冻结。
- 关键文件：`src/hongce/models.py`、`docs/assumptions.md`、`docs/implementation_plan.md`。
- 验证：阶段合同测试通过。

## 阶段 1

- 已实现：可复现合成县域、规则智能体仿真内核、S0/S3/S5 端到端 CLI。
- 关键文件：`src/hongce/scenario.py`、`src/hongce/engine.py`、`src/hongce/cli.py`。
- 验证：单次运行与批量比较均写入 `outputs/`，仿真输出标注为 SIMULATED。

## 阶段 2

- 已实现：S1/S2/S4 扩展、A/B/C 批量实验、解释包、区间统计。
- 关键文件：`src/hongce/experiments.py`、`outputs/experiments/experiments_abc_summary.json`。
- 验证：批量实验结果来自真实 `run_policy` 调用。

## 阶段 3

- 已实现：API 服务层、FastAPI 可选入口、无依赖 HTTP server、七页前端工作台。
- 关键文件：`api/service.py`、`api/simple_server.py`、`web/index.html`、`web/src/app.js`、`web/src/styles.css`。
- 验证：API 服务测试覆盖仿真、事件、个体轨迹、实验。

## 阶段 4

- 已实现：规则智能体适配器、玉兰万象适配器 payload 契约。
- 关键文件：`src/hongce/adapters.py`。
- 限制：当前不调用玉兰万象外部服务；后续可按冻结 schema 对接平台。

## 阶段 5

- 已实现：架构文档、技术文档、演示脚本、启动命令。
- 现存限制：合成场景尚未校准真实灾情数据；前端是轻量原生实现，不包含用户系统、权限或在线部署。
