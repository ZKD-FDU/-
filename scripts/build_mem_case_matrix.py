"""Build a HongCe-oriented matrix from downloaded MEM PDF text.

The output is intentionally conservative: extracted numeric fields are
machine-assisted and should be manually verified before citation.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path("data/raw/mem_reports")
DOCS = Path("docs")

PROCESS_KEYWORDS = {
    "监测预警": ["监测", "预警", "气象", "水文", "会商", "雨情", "水情", "险情"],
    "分级响应": ["Ⅰ级", "I级", "一级响应", "Ⅱ级", "II级", "二级响应", "红色预警", "橙色预警", "黄色预警", "蓝色预警", "启动响应"],
    "指挥调度": ["指挥部", "现场指挥", "调度", "会商研判", "应急管理", "防汛抗旱"],
    "基层执行": ["乡镇", "街道", "村", "社区", "村委会", "居委会", "基层", "网格", "干部"],
    "机构场所": ["养老", "医院", "学校", "培训", "宾馆", "酒店", "工厂", "工地", "企业", "矿"],
    "人员转移": ["转移", "撤离", "疏散", "避险", "安置", "安全撤出", "逃生"],
    "救援搜救": ["救援", "搜救", "消防", "抢险", "救治", "被困", "失联"],
    "信息报送": ["上报", "报告", "迟报", "瞒报", "漏报", "统计", "信息"],
    "责任追究": ["责任", "履职", "失职", "监管", "问责", "处分", "追究"],
    "整改闭环": ["整改", "防范措施", "落实", "评估", "回头看", "隐患排查"],
}

HONGCE_INDICATORS = {
    "伤亡": ["死亡", "失踪", "失联", "遇难", "受伤", "伤亡"],
    "财产损失": ["直接经济损失", "经济损失", "损毁", "损失"],
    "提前量": ["提前", "小时", "分钟", "预警", "响应"],
    "转移执行": ["转移", "撤离", "疏散", "避险", "安置", "安全撤出"],
    "脆弱群体": ["老人", "养老", "医院", "学生", "儿童", "病人", "失能", "特殊人群"],
    "组织协同": ["指挥部", "应急管理", "气象", "水利", "公安", "交通", "民政", "卫健", "消防", "住建", "自然资源"],
    "基层闭环": ["乡镇", "街道", "村", "社区", "网格", "包保", "责任人"],
    "信任满意": ["舆情", "社会影响", "满意", "信任", "群众", "安抚"],
}


def main() -> int:
    rows = load_case_rows()
    grouped = consolidate_by_title(rows)
    matrix = [build_record(row) for row in grouped]

    ROOT.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    write_csv(ROOT / "hongce_case_matrix.csv", matrix)
    (ROOT / "hongce_case_matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(DOCS / "hongce_mem_case_analysis.md", matrix)

    print(f"matrix reports: {len(matrix)}")
    print("scenario classes:", dict(Counter(r["scenario_class"] for r in matrix)))
    print("report roles:", dict(Counter(r["report_role"] for r in matrix)))
    print("outputs:")
    print(ROOT / "hongce_case_matrix.csv")
    print(ROOT / "hongce_case_matrix.json")
    print(DOCS / "hongce_mem_case_analysis.md")
    return 0


def load_case_rows() -> list[dict[str, str]]:
    rows = list(csv.DictReader((ROOT / "case_analysis.csv").open(encoding="utf-8-sig")))
    for row in rows:
        text_path = ROOT / "texts" / f"{Path(row['filename']).stem}.txt"
        row["text_path"] = str(text_path)
        row["text"] = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else ""
    return rows


def consolidate_by_title(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_title: dict[str, dict[str, str]] = {}
    for row in rows:
        title = normalize_title(row["title"])
        current = by_title.get(title)
        if current is None or len(row.get("text", "")) > len(current.get("text", "")):
            copy = dict(row)
            copy["title"] = title
            copy["source_files"] = row["filename"]
            by_title[title] = copy
        elif current is not None:
            current["source_files"] += f"; {row['filename']}"
    return sorted(by_title.values(), key=lambda r: (report_order(r["title"]), r["title"]))


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", "", title).replace("•", "·")


def report_order(title: str) -> int:
    if any(word in title for word in ["暴雨", "洪水", "洪涝", "滑坡", "山洪", "灾害"]):
        return 0
    if "整改" in title or "回头看" in title:
        return 2
    return 1


def build_record(row: dict[str, str]) -> dict[str, str]:
    text = compact_text(row.get("text", ""))
    title = row["title"]
    report_role = classify_report_role(title)
    numbers = {} if report_role == "整改评估/制度修复" else extract_numbers(text)
    process_scores = {name: keyword_count(text, words) for name, words in PROCESS_KEYWORDS.items()}
    indicator_scores = {name: keyword_count(text, words) for name, words in HONGCE_INDICATORS.items()}

    return {
        "title": title,
        "report_role": report_role,
        "scenario_class": classify_scenario(title, text),
        "hazard_or_trigger": infer_hazard(title, text),
        "affected_setting": infer_setting(title, text),
        "actual_deaths_or_dead_missing": numbers.get("deaths_or_dead_missing", ""),
        "actual_missing": numbers.get("missing", ""),
        "actual_injured": numbers.get("injured", ""),
        "actual_direct_loss": numbers.get("direct_loss", ""),
        "transfer_or_evacuation_data": extract_transfer_data(text),
        "process_nodes_present": join_nonzero(process_scores),
        "hongce_indicator_evidence": join_nonzero(indicator_scores),
        "key_process_summary": summarize_process(title, text),
        "hongce_modeling_use": modeling_use(title, text),
        "source_files": row.get("source_files", row["filename"]),
        "source_url": row.get("source_url", ""),
        "pdf_url": row.get("pdf_url", ""),
    }


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def keyword_count(text: str, words: list[str]) -> int:
    return sum(text.count(word) for word in words)


def classify_report_role(title: str) -> str:
    if "整改" in title or "回头看" in title or "落实情况评估" in title:
        return "整改评估/制度修复"
    if "调查" in title or "调查评估" in title:
        return "灾害事故调查"
    return "综合通报"


def classify_scenario(title: str, text: str) -> str:
    if any(w in title for w in ["暴雨", "洪水", "山洪", "桥梁垮塌"]):
        return "极端降雨洪涝/山洪及基础设施失效"
    if "滑坡" in title:
        return "地质灾害/堆填体滑坡"
    if any(w in title for w in ["医院", "养老", "培训", "店铺", "酒店", "宾馆"]):
        return "人员密集或脆弱机构场所"
    if any(w in title for w in ["化工", "危险品", "爆炸", "燃气"]):
        return "危化品/燃气爆炸火灾"
    if any(w in title for w in ["商贸", "有限公司"]) and "火灾" in title:
        return "工厂/仓储/企业火灾"
    if any(w in title for w in ["煤矿", "瓦斯", "露天煤矿"]):
        return "矿山事故/工矿场所"
    if any(w in title for w in ["自建房", "坍塌", "冷却塔", "施工平台"]):
        return "建筑坍塌/工地与城市空间"
    if any(w in title for w in ["高速", "道路交通"]):
        return "道路交通/通道安全"
    if "回头看" in title or "整改" in title:
        return "跨案例整改复盘"
    return "其他重大事故"


def infer_hazard(title: str, text: str) -> str:
    candidates = []
    mapping = [
        ("极端暴雨/洪水/山洪", ["暴雨", "洪水", "山洪", "洪涝"]),
        ("桥梁/道路受洪水冲毁或垮塌", ["桥梁垮塌", "桥梁", "坠河"]),
        ("滑坡/堆填体失稳", ["滑坡", "渣土", "堆填体"]),
        ("火灾/烟气/逃生受阻", ["火灾", "烟气", "逃生"]),
        ("爆炸/冲击波/危化品", ["爆炸", "危险品", "硝酸铵", "危化"]),
        ("瓦斯/矿山坍塌", ["瓦斯", "煤矿", "露天煤矿", "坍塌"]),
        ("建筑结构失效", ["自建房", "冷却塔", "施工平台", "坍塌"]),
        ("道路交通碰撞/客运风险", ["道路交通", "高速", "客车"]),
    ]
    for label, keys in mapping:
        if any(k in title or k in text[:3000] for k in keys):
            candidates.append(label)
    return "；".join(candidates[:3])


def infer_setting(title: str, text: str) -> str:
    if "郑州" in title and "暴雨" in title:
        return "城市内涝区；山丘区村镇；地铁/隧道；水库/河道；固定经营场所"
    if "密云" in title and "养老" in title:
        return "养老机构；村镇/社区；河道周边低洼区"
    if "商洛" in title and "桥梁垮塌" in title:
        return "高速公路/桥梁通道；流域村镇；水毁道路"
    if "深圳" in title and "滑坡" in title:
        return "渣土受纳场；周边工业园/企业；居民点"
    mapping = [
        ("养老机构", ["养老"]),
        ("医院", ["医院"]),
        ("学校/培训机构", ["学校", "培训", "学生"]),
        ("村镇/社区", ["村", "社区", "乡镇", "街道"]),
        ("高速公路/桥梁通道", ["高速", "桥梁", "道路"]),
        ("工厂/工地/园区", ["工厂", "工地", "园区", "企业", "施工"]),
        ("矿山", ["煤矿", "矿"]),
        ("商住综合体/店铺/餐饮", ["店铺", "烧烤", "商铺", "综合楼", "宾馆", "酒店"]),
        ("危化品仓储/化工企业", ["危险品", "化工", "仓库"]),
    ]
    found = []
    for label, keys in mapping:
        if any(k in title or k in text[:5000] for k in keys):
            found.append(label)
    return "；".join(found[:4])


def extract_numbers(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    first = text[:10000]

    patterns = [
        ("deaths_or_dead_missing", r"(?:全省|全市|郑州市)?(?:因灾)?死亡失踪\s*([0-9]+)\s*人"),
        ("deaths_or_dead_missing", r"造成\s*([0-9]+)\s*人(?:死亡失踪|死亡|遇难)"),
        ("deaths_or_dead_missing", r"([0-9]+)\s*人(?:死亡失踪|死亡|遇难)"),
        ("missing", r"([0-9]+)\s*人(?:失踪|失联|下落不明)"),
        ("injured", r"([0-9]+)\s*人(?:受伤|住院治疗|受伤住院治疗)"),
        ("direct_loss", r"直\s*接\s*经\s*济\s*损\s*失\s*(?:为)?\s*([0-9.]+)\s*余?\s*(亿元|万元)"),
        ("direct_loss", r"核定(?:事故)?造成直\s*接\s*经\s*济\s*损\s*失\s*(?:为)?\s*([0-9.]+)\s*余?\s*(亿元|万元)"),
        ("direct_loss", r"造成直\s*接\s*经\s*济\s*损\s*失\s*(?:为)?\s*([0-9.]+)\s*余?\s*(亿元|万元)"),
        ("direct_loss", r"经济损失\s*(?:为)?\s*([0-9.]+)\s*余?\s*(亿元|万元)"),
    ]
    for key, pattern in patterns:
        if key in out:
            continue
        match = re.search(pattern, first)
        if match:
            if key == "direct_loss":
                out[key] = f"{match.group(1)}{match.group(2)}"
            else:
                out[key] = f"{match.group(1)}人"

    return out


def extract_transfer_data(text: str) -> str:
    snippets = []
    patterns = [
        r"[0-9.]+\s*万?人安全撤出",
        r"转移(?:受威胁)?群众\s*[0-9.]+\s*万?人",
        r"疏散(?:救援)?[,，]?\s*[0-9.]+\s*万?人",
        r"[0-9.]+\s*万?人(?:紧急)?疏散",
        r"[0-9.]+\s*万?人(?:转移|撤离|安置)",
        r"转移后又返回[^。；]*",
        r"未包括[^。；]*养老照料中心[^。；]*",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text[:12000]):
            value = match.group(0).strip()
            if value not in snippets:
                snippets.append(value)
            if len(snippets) >= 4:
                return "；".join(snippets)
    return "未稳定抽取；需人工复核转移/疏散记录"


def join_nonzero(scores: dict[str, int]) -> str:
    pairs = [(key, value) for key, value in scores.items() if value > 0]
    pairs.sort(key=lambda kv: kv[1], reverse=True)
    return "；".join(f"{key}:{value}" for key, value in pairs)


def summarize_process(title: str, text: str) -> str:
    if "郑州" in title and "暴雨" in title:
        return "极端降雨形成城市内涝、山洪和中小河流洪水；预警与响应、转移和灾情报送之间存在断裂，部分人员未转移或转移后返回。"
    if "密云" in title and "养老" in title:
        return "特大洪水快速进入养老照料中心；风险台账和临灾撤离未覆盖机构，镇村与机构先期处置和报警救援延迟。"
    if "商洛" in title and "桥梁垮塌" in title:
        return "连续降雨与山洪冲刷、漂流物堵塞和桥梁结构问题叠加；交通管制、监测联动和应急响应启动存在不足。"
    if "滑坡" in title:
        return "堆填体长期超量超高、排水与监测不足，群众报告后现场核查与避险处置未能阻断重大伤亡。"
    if any(w in title for w in ["医院", "养老", "店铺", "酒店", "宾馆"]):
        return "人员密集或脆弱场所发生突发灾害事故，逃生、疏散、消防救援、行业监管和日常隐患治理是关键流程。"
    if any(w in title for w in ["化工", "危险品", "燃气", "爆炸"]):
        return "高危物质或燃气风险累积，监测监管和企业主体责任失效后引发爆炸/火灾，现场疏散和次生风险控制成为关键。"
    if any(w in title for w in ["煤矿", "瓦斯", "露天煤矿"]):
        return "工矿场所生产组织、监测预警、撤人停产和监管执法链条失灵，事故后救援和整改闭环是重点。"
    if any(w in title for w in ["高速", "道路交通"]):
        return "通道型风险中车辆、道路状态、交通管制、报警和救援响应共同决定伤亡规模。"
    if "整改" in title or "回头看" in title:
        return "用于提炼整改闭环、责任落实、隐患排查、制度执行和复盘评估指标。"
    return "可作为重大突发事件的组织协同、风险识别、应急处置和责任复盘样本。"


def modeling_use(title: str, text: str) -> str:
    uses = []
    if any(w in title for w in ["暴雨", "洪水", "山洪", "桥梁垮塌", "滑坡"]):
        uses.append("极端灾害统一危机类群")
    if any(w in title for w in ["养老", "医院", "学校", "培训", "店铺", "宾馆", "酒店"]):
        uses.append("脆弱/人员密集场所转移")
    if any(w in title for w in ["工厂", "工地", "矿", "化工", "危险品", "施工"]):
        uses.append("工厂/工地/园区主体补充")
    if any(w in text[:12000] for w in ["预警", "响应", "指挥部"]):
        uses.append("预警-响应-指挥状态机")
    if any(w in text[:12000] for w in ["转移", "撤离", "疏散", "安置"]):
        uses.append("人员转移/疏散指标")
    if any(w in text[:12000] for w in ["村", "社区", "乡镇", "基层"]):
        uses.append("基层闭环与自下而上报告")
    if "整改" in title or "回头看" in title:
        uses.append("整改完成率与制度学习指标")
    return "；".join(uses)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict[str, str]]) -> None:
    scenario_counts = Counter(r["scenario_class"] for r in rows)
    role_counts = Counter(r["report_role"] for r in rows)
    lines = [
        "# 洪策：应急管理部灾情/事故报告全案例分析",
        "",
        "本报告基于本地抓取的应急管理部 PDF 文本自动整理。数值字段为机器抽取结果，正式引用前应回到 PDF 原文逐项核对。",
        "",
        "## 语料概况",
        "",
        f"- 分析单位：{len(rows)} 个去重报告标题。",
        f"- 报告类型：{dict(role_counts)}。",
        f"- 情景类型：{dict(scenario_counts)}。",
        "",
        "## 全案例矩阵",
        "",
        "| # | 案例 | 情景 | 死亡/死失 | 失踪 | 受伤 | 直接损失 | 转移/疏散数据 | 洪策用途 |",
        "|---:|---|---|---:|---:|---:|---:|---|---|",
    ]
    for idx, row in enumerate(rows, 1):
        lines.append(
            "| {idx} | {title} | {scenario} | {deaths} | {missing} | {injured} | {loss} | {transfer} | {use} |".format(
                idx=idx,
                title=escape_md(row["title"]),
                scenario=escape_md(row["scenario_class"]),
                deaths=row["actual_deaths_or_dead_missing"] or "",
                missing=row["actual_missing"] or "",
                injured=row["actual_injured"] or "",
                loss=row["actual_direct_loss"] or "",
                transfer=escape_md(row["transfer_or_evacuation_data"]),
                use=escape_md(row["hongce_modeling_use"]),
            )
        )
    lines.extend(
        [
            "",
            "## 逐案流程拆解",
            "",
        ]
    )
    for idx, row in enumerate(rows, 1):
        data_bits = [
            f"死亡/死失：{row['actual_deaths_or_dead_missing'] or '未抽取'}",
            f"失踪/下落不明：{row['actual_missing'] or '未抽取'}",
            f"受伤/住院：{row['actual_injured'] or '未抽取'}",
            f"直接损失：{row['actual_direct_loss'] or '未抽取'}",
        ]
        lines.extend(
            [
                f"### {idx}. {row['title']}",
                "",
                f"- 情景归类：{row['scenario_class']}。",
                f"- 影响场所：{row['affected_setting'] or '未稳定识别'}。",
                f"- 致灾/触发机制：{row['hazard_or_trigger'] or '未稳定识别'}。",
                f"- 实际数据：{'；'.join(data_bits)}。",
                f"- 转移/疏散数据：{row['transfer_or_evacuation_data']}。",
                f"- 具体流程与断点：{row['key_process_summary']}",
                f"- 可转化为洪策指标：{row['hongce_indicator_evidence']}",
                f"- 模型用途：{row['hongce_modeling_use']}",
                "",
            ]
        )
    lines.extend(
        [
            "",
            "## 洪策指标池",
            "",
            "- 一级结果指标：人员伤亡率、财产损失率。",
            "- 二级过程指标：安全转移率、风险有效提前量、响应启动延迟、预警到行动转化率、基层确认闭环率、脆弱群体覆盖率、路线/桥梁阻断暴露度。",
            "- 组织指标：部门协同密度、指挥链闭环率、基层上报及时率、机构负责人执行率、整改完成率。",
            "- 行为指标：拒绝转移率、转移后返家率、社会确认触发率、邻里互助覆盖率、公众满意度、制度信任变化。",
            "",
            "## 状态机建议",
            "",
            "常态监测 -> 风险识别 -> 预警发布 -> 分级响应 -> 指挥调度 -> 基层/机构确认 -> 转移动员 -> 路线与安置 -> 救援处置 -> 损失核算 -> 复盘整改。",
            "",
            "同时保留自下而上支路：居民/网格员/机构负责人发现异常 -> 基层核实 -> 上报街镇/县区 -> 指挥部纳入任务派发。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
