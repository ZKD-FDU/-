"""Promote MEM case analysis into the HongCe training corpus.

This script turns the raw case matrix into a simulation-facing corpus. It does
not invent outcomes: observed deaths, injuries, losses, and extracted transfer
facts are carried over from the source matrix and marked as official-report
derived fields that still need human citation checks before publication.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


RAW_MATRIX = Path("data/raw/mem_reports/hongce_case_matrix.csv")
OUT_DIR = Path("data/processed")
DOCS_DIR = Path("docs")

STATE_MACHINE = [
    "hazard_accumulation",
    "risk_detection",
    "warning_release",
    "graded_response",
    "command_dispatch",
    "grassroots_or_institution_confirmation",
    "evacuation_mobilization",
    "route_and_shelter_execution",
    "rescue_response",
    "loss_assessment",
    "review_and_rectification",
]

BOTTOM_UP_BRANCH = [
    "resident_or_frontline_detection",
    "grassroots_verification",
    "town_county_escalation",
    "command_integration",
    "reverse_task_dispatch",
]

CORE_ACTORS = {
    "command": ["防汛抗旱指挥部", "应急管理部门"],
    "technical": ["气象部门", "水利部门", "自然资源部门", "交通部门", "住建部门"],
    "public_services": ["公安", "消防救援", "民政", "卫健", "教育"],
    "frontline": ["街镇", "村委会/居委会", "网格员", "机构负责人", "企业/工地负责人", "志愿者"],
    "public": ["普通居民", "脆弱居民", "家属", "邻里网络"],
}

INDICATOR_BANK = {
    "primary": ["casualty_rate", "property_loss_rate"],
    "evacuation": [
        "safe_transfer_rate",
        "transfer_completion_minutes",
        "effective_lead_time_minutes",
        "refusal_rate",
        "return_after_transfer_rate",
        "vulnerable_group_coverage_rate",
    ],
    "organization": [
        "warning_to_action_conversion_rate",
        "response_activation_delay_minutes",
        "grassroots_confirmation_closure_rate",
        "department_coordination_density",
        "institution_lead_execution_rate",
        "upward_reporting_timeliness",
    ],
    "social": [
        "public_satisfaction",
        "institutional_trust_delta",
        "risk_communication_effectiveness",
        "neighbor_support_coverage",
        "social_confirmation_trigger_rate",
    ],
    "review": ["rectification_completion_rate", "hidden_risk_recheck_rate", "accountability_closure_rate"],
}


def main() -> int:
    rows = load_rows(RAW_MATRIX)
    corpus = [build_case(row, idx) for idx, row in enumerate(rows, 1)]
    summary = build_summary(corpus)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(OUT_DIR / "hongce_training_case_corpus.csv", corpus)
    (OUT_DIR / "hongce_training_case_corpus.json").write_text(
        json.dumps({"summary": summary, "cases": corpus}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_corpus_design(DOCS_DIR / "hongce_case_corpus_design.md", corpus, summary)
    write_simulation_mapping(DOCS_DIR / "hongce_simulation_mapping.md", corpus, summary)

    print(f"training cases: {len(corpus)}")
    print("scenario classes:", dict(Counter(case["scenario_class"] for case in corpus)))
    print("simulation modules:", dict(Counter(module for case in corpus for module in case["simulation_modules"])))
    print("outputs:")
    print(OUT_DIR / "hongce_training_case_corpus.csv")
    print(OUT_DIR / "hongce_training_case_corpus.json")
    print(DOCS_DIR / "hongce_case_corpus_design.md")
    print(DOCS_DIR / "hongce_simulation_mapping.md")
    return 0


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def build_case(row: dict[str, str], idx: int) -> dict[str, Any]:
    scenario = row["scenario_class"]
    title = row["title"]
    actors = infer_actors(row)
    failure_modes = infer_failure_modes(row)
    interventions = infer_interventions(row)
    indicators = infer_indicators(row, failure_modes)
    modules = infer_modules(row, indicators)
    policy_links = infer_policy_links(row, interventions)
    return {
        "case_id": f"HC-MEM-{idx:03d}",
        "source_label": "FACT",
        "source_agency": "中华人民共和国应急管理部",
        "source_report_role": row["report_role"],
        "case_name": title,
        "scenario_class": scenario,
        "hazard_trigger": split_field(row["hazard_or_trigger"]),
        "affected_setting": split_field(row["affected_setting"]),
        "actor_chain": actors,
        "process_trace": build_process_trace(row, actors),
        "bottom_up_signals": infer_bottom_up_signals(row),
        "failure_modes": failure_modes,
        "intervention_points": interventions,
        "observed_outcomes": {
            "deaths_or_dead_missing": row["actual_deaths_or_dead_missing"],
            "missing": row["actual_missing"],
            "injured": row["actual_injured"],
            "direct_economic_loss": row["actual_direct_loss"],
            "transfer_or_evacuation_data": row["transfer_or_evacuation_data"],
            "extraction_note": "自动抽取字段，正式引用前需回到 PDF 原文核对。",
        },
        "metric_candidates": indicators,
        "simulation_modules": modules,
        "policy_scenarios": policy_links,
        "training_use": {
            "rag_retrieval": True,
            "state_machine_rule_extraction": True,
            "parameter_calibration": bool(row["actual_deaths_or_dead_missing"] or row["actual_direct_loss"]),
            "scenario_template_generation": True,
        },
        "source_files": row["source_files"],
        "source_url": row["source_url"],
        "pdf_url": row["pdf_url"],
    }


def split_field(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("；") if part.strip()]


def infer_actors(row: dict[str, str]) -> list[str]:
    actors = ["应急管理部门", "属地政府", "基层组织", "受影响群众"]
    text = " ".join([row["case_name"] if "case_name" in row else row["title"], row["scenario_class"], row["affected_setting"], row["key_process_summary"]])
    if any(word in text for word in ["暴雨", "洪水", "山洪", "桥梁"]):
        actors.extend(["防汛抗旱指挥部", "气象部门", "水利部门", "交通部门", "消防救援力量"])
    if "滑坡" in text or "地质" in text:
        actors.extend(["自然资源部门", "园区/企业负责人", "周边居民"])
    if any(word in text for word in ["养老", "医院", "学校", "培训", "宾馆", "酒店", "店铺"]):
        actors.extend(["民政/卫健/教育/商务主管部门", "机构负责人", "脆弱群体/人员密集场所人员"])
    if any(word in text for word in ["工厂", "工地", "施工", "矿", "化工", "危险品", "燃气"]):
        actors.extend(["企业负责人", "行业监管部门", "工人/作业人员"])
    if any(word in text for word in ["村", "社区", "乡镇", "街道", "基层"]):
        actors.extend(["街镇干部", "村委会/居委会", "网格员", "志愿者"])
    return dedupe(actors)


def infer_bottom_up_signals(row: dict[str, str]) -> list[str]:
    text = row["key_process_summary"] + " " + row["process_nodes_present"]
    signals = []
    if "群众报告" in text or "基层" in text:
        signals.append("群众/基层发现异常并报告")
    if "机构" in text or "养老" in row["affected_setting"] or "医院" in row["affected_setting"]:
        signals.append("机构负责人或值班人员发现险情")
    if "村" in row["affected_setting"] or "社区" in row["affected_setting"]:
        signals.append("村居干部现场确认风险")
    if "交通" in row["scenario_class"] or "桥梁" in row["scenario_class"]:
        signals.append("现场司机/路管人员报警")
    return signals or ["未稳定抽取，可作为人工标注字段"]


def infer_failure_modes(row: dict[str, str]) -> list[str]:
    text = " ".join([row["title"], row["scenario_class"], row["key_process_summary"], row["transfer_or_evacuation_data"]])
    modes = []
    rules = [
        ("warning_response_gap", ["预警与响应", "响应启动", "预警", "响应"]),
        ("registry_coverage_gap", ["台账", "未覆盖", "未包括", "养老", "脆弱"]),
        ("evacuation_not_decisive", ["未转移", "不彻底", "转移后又返回", "疏散"]),
        ("route_or_infrastructure_failure", ["桥梁", "道路", "隧道", "水毁", "阻断"]),
        ("grassroots_confirmation_gap", ["基层", "镇村", "现场核查", "确认"]),
        ("institution_execution_gap", ["机构", "医院", "养老", "学校", "酒店", "培训"]),
        ("enterprise_responsibility_gap", ["企业", "工厂", "工地", "矿", "施工", "化工"]),
        ("reporting_integrity_gap", ["迟报", "瞒报", "漏报", "上报", "信息报送"]),
        ("regulatory_enforcement_gap", ["监管", "隐患", "排查", "整改", "失职"]),
    ]
    for code, keywords in rules:
        if any(keyword in text for keyword in keywords):
            modes.append(code)
    return modes or ["generic_emergency_coordination_gap"]


def infer_interventions(row: dict[str, str]) -> list[str]:
    modes = infer_failure_modes(row)
    mapping = {
        "warning_response_gap": "预警-响应联动触发阈值",
        "registry_coverage_gap": "脆弱群体/重点场所动态台账",
        "evacuation_not_decisive": "强制/协商转移与返家管控",
        "route_or_infrastructure_failure": "关键通道巡查、封控与备用路线",
        "grassroots_confirmation_gap": "网格员确认闭环和上报时限",
        "institution_execution_gap": "机构负责人预案演练和一键求援",
        "enterprise_responsibility_gap": "企业/工地停工撤人触发规则",
        "reporting_integrity_gap": "灾情报送一致性与审计",
        "regulatory_enforcement_gap": "隐患排查整改闭环",
    }
    return [mapping[mode] for mode in modes if mode in mapping]


def infer_indicators(row: dict[str, str], failure_modes: list[str]) -> list[str]:
    indicators = ["casualty_rate", "property_loss_rate"]
    mode_to_indicators = {
        "warning_response_gap": ["effective_lead_time_minutes", "response_activation_delay_minutes", "warning_to_action_conversion_rate"],
        "registry_coverage_gap": ["vulnerable_group_coverage_rate", "critical_facility_registry_coverage_rate"],
        "evacuation_not_decisive": ["safe_transfer_rate", "refusal_rate", "return_after_transfer_rate"],
        "route_or_infrastructure_failure": ["route_blockage_exposure_rate", "alternate_route_activation_rate"],
        "grassroots_confirmation_gap": ["grassroots_confirmation_closure_rate", "upward_reporting_timeliness"],
        "institution_execution_gap": ["institution_lead_execution_rate", "vulnerable_group_coverage_rate"],
        "enterprise_responsibility_gap": ["worksite_shutdown_timeliness", "worker_evacuation_rate"],
        "reporting_integrity_gap": ["reporting_timeliness", "reporting_consistency_rate"],
        "regulatory_enforcement_gap": ["rectification_completion_rate", "hidden_risk_recheck_rate"],
    }
    for mode in failure_modes:
        indicators.extend(mode_to_indicators.get(mode, []))
    if "信任满意" in row["hongce_indicator_evidence"]:
        indicators.extend(["public_satisfaction", "institutional_trust_delta"])
    return dedupe(indicators)


def infer_modules(row: dict[str, str], indicators: list[str]) -> list[str]:
    modules = ["case_retrieval_rag", "scenario_template_generator", "state_machine_rule_library"]
    if any(ind in indicators for ind in ["safe_transfer_rate", "vulnerable_group_coverage_rate"]):
        modules.append("evacuation_kernel")
    if any(ind in indicators for ind in ["effective_lead_time_minutes", "response_activation_delay_minutes"]):
        modules.append("warning_response_kernel")
    if any(ind in indicators for ind in ["grassroots_confirmation_closure_rate", "upward_reporting_timeliness"]):
        modules.append("bottom_up_reporting_kernel")
    if any(ind in indicators for ind in ["route_blockage_exposure_rate", "alternate_route_activation_rate"]):
        modules.append("infrastructure_route_kernel")
    if row["report_role"] == "整改评估/制度修复":
        modules.append("review_rectification_kernel")
    return dedupe(modules)


def infer_policy_links(row: dict[str, str], interventions: list[str]) -> list[str]:
    links = ["S0"]
    joined = " ".join(interventions + [row["scenario_class"], row["affected_setting"]])
    if "关键通道" in joined or "备用路线" in joined:
        links.append("S1")
    if "预警" in joined or "响应" in joined:
        links.append("S2")
    if "脆弱" in joined or "机构" in joined or "台账" in joined:
        links.append("S3")
    if "网格" in joined or "上报" in joined or "确认" in joined:
        links.append("S4")
    links.append("S5")
    return dedupe(links)


def build_process_trace(row: dict[str, str], actors: list[str]) -> list[dict[str, Any]]:
    trace = []
    for position, state in enumerate(STATE_MACHINE, 1):
        trace.append(
            {
                "order": position,
                "state": state,
                "evidence_level": "explicit_or_inferred_from_report_keywords",
                "related_actors": actors_for_state(state, actors),
            }
        )
    include_bottom_up = "基层闭环与自下而上报告" in row["hongce_modeling_use"]
    if include_bottom_up:
        trace.append(
            {
                "order": len(trace) + 1,
                "state": "bottom_up_branch",
                "branch_states": BOTTOM_UP_BRANCH,
                "evidence_level": "inferred_from_case_process",
                "related_actors": [actor for actor in actors if actor in {"基层组织", "街镇干部", "村委会/居委会", "网格员", "机构负责人", "受影响群众"}],
            }
        )
    return trace


def actors_for_state(state: str, actors: list[str]) -> list[str]:
    if state in {"hazard_accumulation", "risk_detection", "warning_release"}:
        preferred = {"气象部门", "水利部门", "自然资源部门", "交通部门", "企业负责人", "机构负责人"}
    elif state in {"graded_response", "command_dispatch"}:
        preferred = {"防汛抗旱指挥部", "应急管理部门", "属地政府"}
    elif state in {"grassroots_or_institution_confirmation", "evacuation_mobilization"}:
        preferred = {"基层组织", "街镇干部", "村委会/居委会", "网格员", "机构负责人", "企业负责人"}
    elif state in {"route_and_shelter_execution", "rescue_response"}:
        preferred = {"消防救援力量", "交通部门", "公安", "志愿者", "受影响群众"}
    else:
        preferred = {"应急管理部门", "行业监管部门", "属地政府"}
    selected = [actor for actor in actors if actor in preferred]
    return selected or actors[:3]


def build_summary(corpus: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_count": len(corpus),
        "source_label": "FACT",
        "scenario_classes": dict(Counter(case["scenario_class"] for case in corpus)),
        "report_roles": dict(Counter(case["source_report_role"] for case in corpus)),
        "state_machine": STATE_MACHINE,
        "bottom_up_branch": BOTTOM_UP_BRANCH,
        "actor_groups": CORE_ACTORS,
        "indicator_bank": INDICATOR_BANK,
        "quality_note": "案例均来自已抓取的应急管理部 PDF；自动抽取的数值和流程标签需在正式引用前人工复核。",
    }


def write_csv(path: Path, cases: list[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id",
        "source_label",
        "source_report_role",
        "case_name",
        "scenario_class",
        "hazard_trigger",
        "affected_setting",
        "actor_chain",
        "failure_modes",
        "intervention_points",
        "observed_outcomes",
        "metric_candidates",
        "simulation_modules",
        "policy_scenarios",
        "source_url",
        "pdf_url",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            writer.writerow({key: csv_value(case.get(key, "")) for key in fieldnames})


def csv_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def write_corpus_design(path: Path, corpus: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    lines = [
        "# 洪策案例训练语料库设计",
        "",
        "## 定位",
        "",
        "洪策案例训练语料库把应急管理部灾害/事故调查报告转化为可检索、可标注、可映射到仿真的训练素材。它不是静态展示资料，而是服务于 RAG 检索、状态机规则抽取、场景模板生成和参数校准的数据层。",
        "",
        "## 当前规模",
        "",
        f"- 训练案例：{summary['case_count']} 个去重报告标题。",
        f"- 报告类型：{summary['report_roles']}。",
        f"- 情景类型：{summary['scenario_classes']}。",
        "",
        "## 字段口径",
        "",
        "- `case_id`：洪策内部案例编号。",
        "- `source_label`：事实来源标签，当前均为 `FACT`。",
        "- `scenario_class`：统一危机类群，支持跨洪涝、滑坡、桥梁垮塌、工厂/工地、医院/养老机构等情景训练。",
        "- `actor_chain`：可参与仿真的主体链条。",
        "- `process_trace`：从风险积累到整改复盘的流程节点。",
        "- `bottom_up_signals`：自下而上报告、现场确认、机构值班发现等信号。",
        "- `failure_modes`：报告暴露的流程断点。",
        "- `intervention_points`：可作为政策实验的干预点。",
        "- `observed_outcomes`：报告中的真实伤亡、损失、转移/疏散信息。",
        "- `metric_candidates`：可转化为洪策指标的候选字段。",
        "- `simulation_modules`：该案例可训练或校准的系统模块。",
        "",
        "## 训练方式",
        "",
        "1. RAG 检索：用户输入场景后，检索相似案例并生成仿真初始设定。",
        "2. 状态机规则抽取：把真实流程转成预警、响应、指挥、确认、转移、安置、复盘等节点。",
        "3. 参数校准：用真实伤亡、损失、转移失败、响应延迟、机构遗漏等事实约束仿真参数。",
        "4. 情景模板生成：把每个报告转成可运行的 S0-S5 政策实验模板。",
        "",
        "## 质量控制",
        "",
        "当前语料库由 PDF 文本自动抽取和规则标注生成。正式写入论文、申报书或演示材料前，伤亡、损失、时间线和转移人数必须回到 PDF 原文逐项核对。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_simulation_mapping(path: Path, corpus: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    scenario_counts = Counter(case["scenario_class"] for case in corpus)
    module_counts = Counter(module for case in corpus for module in case["simulation_modules"])
    lines = [
        "# 洪策案例语料到仿真系统映射",
        "",
        "## 总体映射",
        "",
        "所有案例都作为训练素材进入洪策，而不是只保留洪涝案例。洪涝、台风、山洪、滑坡、桥梁垮塌、医院/养老机构火灾、工厂/工地/矿山事故可以被统一抽象为“极端事件下人员保护与协同治理”。",
        "",
        "```text",
        "风险积累 -> 风险识别 -> 预警发布 -> 分级响应 -> 指挥调度 -> 基层/机构确认 -> 转移动员 -> 路线与安置 -> 救援处置 -> 损失核算 -> 复盘整改",
        "```",
        "",
        "自下而上支路：",
        "",
        "```text",
        "居民/网格员/机构负责人发现异常 -> 基层核实 -> 街镇/县区上报 -> 指挥系统整合 -> 反向派发任务",
        "```",
        "",
        "## 情景覆盖",
        "",
    ]
    for scenario, count in scenario_counts.most_common():
        lines.append(f"- {scenario}：{count} 个案例。")
    lines.extend(
        [
            "",
            "## 系统模块覆盖",
            "",
        ]
    )
    for module, count in module_counts.most_common():
        lines.append(f"- `{module}`：{count} 个案例。")
    lines.extend(
        [
            "",
            "## S0-S5 政策映射",
            "",
            "- `S0`：现状基线，所有案例都可作为无强化干预的对照。",
            "- `S1`：工程优先，适配桥梁、道路、水毁、堤防、通信等基础设施失效案例。",
            "- `S2`：数字预警优先，适配预警到响应转换不足、信息触达不足案例。",
            "- `S3`：脆弱群体优先，适配养老、医院、学校、培训机构、低行动能力居民等案例。",
            "- `S4`：社区互助优先，适配群众报告、村居确认、网格员上报、邻里互助案例。",
            "- `S5`：综合韧性，适配所有多链条耦合案例，尤其是郑州暴雨、密云养老机构、商洛桥梁垮塌。",
            "",
            "## 指标落地",
            "",
            "- 结果指标：`casualty_rate`、`property_loss_rate`。",
            "- 转移指标：`safe_transfer_rate`、`effective_lead_time_minutes`、`refusal_rate`、`return_after_transfer_rate`、`vulnerable_group_coverage_rate`。",
            "- 组织指标：`warning_to_action_conversion_rate`、`response_activation_delay_minutes`、`grassroots_confirmation_closure_rate`、`department_coordination_density`、`institution_lead_execution_rate`。",
            "- 社会指标：`public_satisfaction`、`institutional_trust_delta`、`risk_communication_effectiveness`、`neighbor_support_coverage`、`social_confirmation_trigger_rate`。",
            "- 复盘指标：`rectification_completion_rate`、`hidden_risk_recheck_rate`、`accountability_closure_rate`。",
            "",
            "## 下一步接入点",
            "",
            "1. 在 API 中暴露案例检索接口。",
            "2. 用 `scenario_class` 和 `policy_scenarios` 生成仿真实验预设。",
            "3. 把 `failure_modes` 映射到状态机异常状态。",
            "4. 把 `observed_outcomes` 作为校准边界，而不是作为固定演示结果。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
