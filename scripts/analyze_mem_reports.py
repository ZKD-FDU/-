"""Extract text and make a case-level analysis table for MEM report PDFs."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pdfplumber


ROOT = Path("data/raw/mem_reports")

KEYWORDS = {
    "自然灾害": ["暴雨", "洪水", "洪涝", "灾害", "桥梁垮塌", "山洪", "内涝", "台风", "滑坡", "崩塌"],
    "生产安全": ["爆炸", "火灾", "坍塌", "煤矿", "瓦斯", "燃气", "化工", "道路交通", "自建房"],
    "预警监测": ["预警", "气象", "水文", "监测", "会商", "响应", "红色", "橙色", "黄色", "蓝色"],
    "人员转移": ["转移", "撤离", "疏散", "避险", "安置", "搬迁", "救援"],
    "基层组织": ["村", "社区", "街道", "乡镇", "镇政府", "村委会", "居委会", "网格", "基层", "包保"],
    "部门协同": ["应急管理", "防汛", "指挥部", "气象", "水利", "公安", "交通", "民政", "卫健", "住建", "消防", "教育"],
    "脆弱群体": ["老人", "养老", "医院", "学校", "儿童", "学生", "病人", "群众", "居民"],
    "责任链条": ["责任", "职责", "落实", "履职", "监管", "报告", "值守", "巡查", "排查", "整改"],
    "财产损失": ["直接经济损失", "经济损失", "房屋", "车辆", "财产", "损失"],
    "伤亡": ["死亡", "失联", "受伤", "伤亡", "遇难"],
}


def main() -> int:
    texts = ROOT / "texts"
    texts.mkdir(exist_ok=True)
    rows = list(csv.DictReader(open(ROOT / "index_unique.csv", encoding="utf-8-sig")))
    case_rows = []
    for row in rows:
        pdf = ROOT / "pdfs" / row["filename"]
        out = texts / f"{pdf.stem}.txt"
        status = "ok"
        try:
            text = out.read_text(encoding="utf-8", errors="replace") if out.exists() else extract_pdf(pdf)
            if not out.exists():
                out.write_text(text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            text = ""
            status = f"failed:{exc}"

        compact = re.sub(r"\s+", " ", text)
        title = infer_title(row["source_title"], compact)
        counts = {key: sum(compact.count(word) for word in words) for key, words in KEYWORDS.items()}
        category = classify(title, counts)
        report_type = classify_report_type(title)
        case_rows.append(
            {
                "filename": row["filename"],
                "title": title,
                "report_type": report_type,
                "category": category,
                "chars": len(compact),
                "extract_status": status,
                **{f"kw_{key}": value for key, value in counts.items()},
                "source_url": row["source_url"],
                "pdf_url": row["pdf_url"],
            }
        )

    write_outputs(case_rows)
    print("cases", len(case_rows), "texts", len(list(texts.glob("*.txt"))))
    for row in case_rows:
        if row["category"] == "自然灾害" or row["kw_人员转移"] or row["kw_预警监测"]:
            print(
                row["title"],
                row["category"],
                "转移",
                row["kw_人员转移"],
                "预警",
                row["kw_预警监测"],
                "基层",
                row["kw_基层组织"],
            )
    return 0


def extract_pdf(path: Path) -> str:
    parts: list[str] = []
    with pdfplumber.open(path) as doc:
        for page in doc.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def infer_title(source_title: str, text: str) -> str:
    if source_title and not re.fullmatch(r"\d{4}", source_title):
        return source_title
    match = re.search(r"([^。\n]{6,90}?(?:调查报告|评估报告|通报))", text)
    return match.group(1).strip() if match else source_title


def classify(title: str, counts: dict[str, int]) -> str:
    natural_title = any(word in title for word in ["暴雨", "洪水", "洪涝", "灾害", "桥梁垮塌", "山洪", "台风"])
    return "自然灾害" if natural_title or counts["自然灾害"] >= 8 else "事故/生产安全"


def classify_report_type(title: str) -> str:
    if "回头看" in title or "整改和防范措施落实情况评估" in title:
        return "整改评估/回头看"
    if "调查" in title or "调查评估" in title:
        return "调查/调查评估"
    return "通报/其他"


def write_outputs(rows: list[dict[str, object]]) -> None:
    (ROOT / "case_analysis.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (ROOT / "case_analysis.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
