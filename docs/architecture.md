# 洪策系统架构

## 运行链路

1. 情景生成：`src/hongce/scenario.py` 生成带有 SYNTHETIC 标签的清源县域人口、机构、基础设施、资源和多层社会网络。
2. 仿真内核：`src/hongce/engine.py` 按 5 分钟时间步推进预警、通信故障、桥梁关闭、叫应确认、资源调度、转移和暴露风险。
3. 政策实验：`src/hongce/experiments.py` 批量运行 S0-S5，输出 SIMULATED 指标、区间、解释包和 A/B/C 实验结论。
4. API：`api/service.py` 暴露服务契约，`api/simple_server.py` 提供无依赖 HTTP 服务，`api/app.py` 在 FastAPI 可用时提供同等端点。
5. 前端：`web/index.html` 与 `web/src/app.js` 直接调用 API 运行仿真和实验，形成七页参赛工作台。

## 七页前端

- 县域态势总览：安全转移率、脆弱群体风险、响应闭环、资源排队、县域断点图。
- 情景编辑器：种子、人口、政策方案和合成县域设定。
- 实时推演：事件时间线与实时核心指标。
- 叫应确认台：脆弱个体状态、风险、阻塞原因。
- 政策对比：A/B/C 批量实验触发与 S0-S5 指标比较。
- 个体与事件解释：个体决策轨迹、事件记录。
- 复盘与建议：从真实仿真输出生成策略建议。

## 离线保证

默认路径只使用 Python 标准库、pydantic、numpy/pandas 不强依赖外部服务。没有外部模型 Key 时，`RuleBasedAgentAdapter` 完整运行；`YulanOneSimAdapter` 仅冻结未来接入契约。
