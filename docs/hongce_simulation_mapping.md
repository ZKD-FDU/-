# 洪策案例语料到仿真系统映射

## 总体映射

所有案例都作为训练素材进入洪策，而不是只保留洪涝案例。洪涝、台风、山洪、滑坡、桥梁垮塌、医院/养老机构火灾、工厂/工地/矿山事故可以被统一抽象为“极端事件下人员保护与协同治理”。

```text
风险积累 -> 风险识别 -> 预警发布 -> 分级响应 -> 指挥调度 -> 基层/机构确认 -> 转移动员 -> 路线与安置 -> 救援处置 -> 损失核算 -> 复盘整改
```

自下而上支路：

```text
居民/网格员/机构负责人发现异常 -> 基层核实 -> 街镇/县区上报 -> 指挥系统整合 -> 反向派发任务
```

## 情景覆盖

- 危化品/燃气爆炸火灾：6 个案例。
- 人员密集或脆弱机构场所：5 个案例。
- 极端降雨洪涝/山洪及基础设施失效：4 个案例。
- 建筑坍塌/工地与城市空间：3 个案例。
- 道路交通/通道安全：3 个案例。
- 矿山事故/工矿场所：2 个案例。
- 工厂/仓储/企业火灾：2 个案例。
- 跨案例整改复盘：2 个案例。
- 地质灾害/堆填体滑坡：1 个案例。

## 系统模块覆盖

- `case_retrieval_rag`：28 个案例。
- `scenario_template_generator`：28 个案例。
- `state_machine_rule_library`：28 个案例。
- `evacuation_kernel`：28 个案例。
- `review_rectification_kernel`：9 个案例。
- `warning_response_kernel`：8 个案例。
- `infrastructure_route_kernel`：6 个案例。
- `bottom_up_reporting_kernel`：2 个案例。

## S0-S5 政策映射

- `S0`：现状基线，所有案例都可作为无强化干预的对照。
- `S1`：工程优先，适配桥梁、道路、水毁、堤防、通信等基础设施失效案例。
- `S2`：数字预警优先，适配预警到响应转换不足、信息触达不足案例。
- `S3`：脆弱群体优先，适配养老、医院、学校、培训机构、低行动能力居民等案例。
- `S4`：社区互助优先，适配群众报告、村居确认、网格员上报、邻里互助案例。
- `S5`：综合韧性，适配所有多链条耦合案例，尤其是郑州暴雨、密云养老机构、商洛桥梁垮塌。

## 指标落地

- 结果指标：`casualty_rate`、`property_loss_rate`。
- 转移指标：`safe_transfer_rate`、`effective_lead_time_minutes`、`refusal_rate`、`return_after_transfer_rate`、`vulnerable_group_coverage_rate`。
- 组织指标：`warning_to_action_conversion_rate`、`response_activation_delay_minutes`、`grassroots_confirmation_closure_rate`、`department_coordination_density`、`institution_lead_execution_rate`。
- 社会指标：`public_satisfaction`、`institutional_trust_delta`、`risk_communication_effectiveness`、`neighbor_support_coverage`、`social_confirmation_trigger_rate`。
- 复盘指标：`rectification_completion_rate`、`hidden_risk_recheck_rate`、`accountability_closure_rate`。

## 下一步接入点

1. 在 API 中暴露案例检索接口。
2. 用 `scenario_class` 和 `policy_scenarios` 生成仿真实验预设。
3. 把 `failure_modes` 映射到状态机异常状态。
4. 把 `observed_outcomes` 作为校准边界，而不是作为固定演示结果。
