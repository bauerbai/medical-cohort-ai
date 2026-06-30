from __future__ import annotations

import csv
import itertools
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.entity_extractor import ExtractedEntities
from agent.tools import _get_disease_count, _get_semantic_data_overview
from database import get_db_connection, release_db_connection

REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"


ANTIHYPERTENSIVE_DRUG_MAP: list[dict[str, Any]] = [
    {"patterns": ["amlodipine", "氨氯地平"], "name_cn": "氨氯地平", "mechanism": "钙通道阻滞剂（CCB）"},
    {"patterns": ["nifedipine"], "name_cn": "硝苯地平", "mechanism": "钙通道阻滞剂（CCB）"},
    {"patterns": ["felodipine"], "name_cn": "非洛地平", "mechanism": "钙通道阻滞剂（CCB）"},
    {"patterns": ["lacidipine"], "name_cn": "拉西地平", "mechanism": "钙通道阻滞剂（CCB）"},
    {"patterns": ["lercanidipine"], "name_cn": "乐卡地平", "mechanism": "钙通道阻滞剂（CCB）"},
    {"patterns": ["diltiazem", "adizem", "viazem"], "name_cn": "地尔硫卓", "mechanism": "钙通道阻滞剂（CCB）"},
    {"patterns": ["verapamil"], "name_cn": "维拉帕米", "mechanism": "钙通道阻滞剂（CCB）"},
    {"patterns": ["ramipril"], "name_cn": "雷米普利", "mechanism": "ACEI（血管紧张素转换酶抑制剂）"},
    {"patterns": ["enalapril", "依那普利"], "name_cn": "依那普利", "mechanism": "ACEI（血管紧张素转换酶抑制剂）"},
    {"patterns": ["lisinopril"], "name_cn": "赖诺普利", "mechanism": "ACEI（血管紧张素转换酶抑制剂）"},
    {"patterns": ["perindopril"], "name_cn": "培哚普利", "mechanism": "ACEI（血管紧张素转换酶抑制剂）"},
    {"patterns": ["captopril"], "name_cn": "卡托普利", "mechanism": "ACEI（血管紧张素转换酶抑制剂）"},
    {"patterns": ["losartan"], "name_cn": "氯沙坦", "mechanism": "ARB（血管紧张素II受体拮抗剂）"},
    {"patterns": ["candesartan"], "name_cn": "坎地沙坦", "mechanism": "ARB（血管紧张素II受体拮抗剂）"},
    {"patterns": ["valsartan"], "name_cn": "缬沙坦", "mechanism": "ARB（血管紧张素II受体拮抗剂）"},
    {"patterns": ["irbesartan", "aprovel"], "name_cn": "厄贝沙坦", "mechanism": "ARB（血管紧张素II受体拮抗剂）"},
    {"patterns": ["bisoprolol", "比索洛尔"], "name_cn": "比索洛尔", "mechanism": "β受体阻滞剂"},
    {"patterns": ["atenolol"], "name_cn": "阿替洛尔", "mechanism": "β受体阻滞剂"},
    {"patterns": ["propranolol"], "name_cn": "普萘洛尔", "mechanism": "β受体阻滞剂"},
    {"patterns": ["metoprolol"], "name_cn": "美托洛尔", "mechanism": "β受体阻滞剂"},
    {"patterns": ["labetalol"], "name_cn": "拉贝洛尔", "mechanism": "α/β受体阻滞剂"},
    {"patterns": ["celiprolol"], "name_cn": "塞利洛尔", "mechanism": "β受体阻滞剂"},
    {"patterns": ["bendroflumethiazide"], "name_cn": "苄氟噻嗪", "mechanism": "噻嗪类利尿剂"},
    {"patterns": ["indapamide"], "name_cn": "吲达帕胺", "mechanism": "利尿剂"},
    {"patterns": ["furosemide"], "name_cn": "呋塞米", "mechanism": "袢利尿剂"},
    {"patterns": ["bumetanide"], "name_cn": "布美他尼", "mechanism": "袢利尿剂"},
    {"patterns": ["spironolactone"], "name_cn": "螺内酯", "mechanism": "保钾利尿剂/醛固酮受体拮抗剂"},
    {"patterns": ["doxazosin"], "name_cn": "多沙唑嗪", "mechanism": "α受体阻滞剂"},
    {"patterns": ["tamsulosin"], "name_cn": "坦索罗辛", "mechanism": "α1受体阻滞剂（泌尿系统用药）"},
    {"patterns": ["glyceryl trinitrate"], "name_cn": "硝酸甘油", "mechanism": "硝酸酯类血管扩张药/抗心绞痛药"},
    {"patterns": ["isosorbide mononitrate"], "name_cn": "单硝酸异山梨酯", "mechanism": "硝酸酯类血管扩张药/抗心绞痛药"},
    {"patterns": ["ranolazine"], "name_cn": "雷诺嗪", "mechanism": "抗心绞痛药（非典型降压药）"},
    {"patterns": ["sildenafil"], "name_cn": "西地那非", "mechanism": "PDE5抑制剂/肺动脉高压相关药"},
    {"patterns": ["cinnarizine"], "name_cn": "桂利嗪", "mechanism": "钙通道阻滞相关药（非典型降压药）"},
]


async def get_sample_distribution() -> dict[str, Any]:
    connection = await get_db_connection()
    try:
        total_patients = await connection.fetchval("SELECT COUNT(*) FROM ukb_semantic.patient_master_index;")
        sex_rows = await connection.fetch(
            """
            SELECT COALESCE(sex_label, sex::text, '未知') AS label, COUNT(*) AS n
            FROM ukb_semantic.patient_master_index
            GROUP BY COALESCE(sex_label, sex::text, '未知')
            ORDER BY n DESC;
            """
        )
        age_summary = await connection.fetchrow(
            """
            SELECT
                COUNT(age_at_recruitment) AS n,
                AVG(age_at_recruitment) AS mean,
                STDDEV(age_at_recruitment) AS sd,
                MIN(age_at_recruitment) AS min,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY age_at_recruitment) AS q1,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY age_at_recruitment) AS median,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY age_at_recruitment) AS q3,
                MAX(age_at_recruitment) AS max
            FROM ukb_semantic.patient_master_index;
            """
        )
        age_band_rows = await connection.fetch(
            """
            SELECT
                CASE
                    WHEN age_at_recruitment < 50 THEN '<50岁'
                    WHEN age_at_recruitment < 60 THEN '50-59岁'
                    WHEN age_at_recruitment < 70 THEN '60-69岁'
                    ELSE '70岁及以上'
                END AS label,
                COUNT(*) AS n
            FROM ukb_semantic.patient_master_index
            WHERE age_at_recruitment IS NOT NULL
            GROUP BY 1
            ORDER BY MIN(age_at_recruitment);
            """
        )
        vital_summary = await connection.fetchrow(
            """
            SELECT
                COUNT(*) AS n,
                AVG(systolic_bp) AS sbp_mean,
                STDDEV(systolic_bp) AS sbp_sd,
                AVG(diastolic_bp) AS dbp_mean,
                STDDEV(diastolic_bp) AS dbp_sd
            FROM ukb_semantic.unified_vitals;
            """
        )
    finally:
        await release_db_connection(connection)

    overview = await _get_semantic_data_overview(disease_limit=5, drug_limit=5)
    sex_distribution = [dict(row) for row in sex_rows]
    age_summary_dict = dict(age_summary) if age_summary else {}
    age_bands = [dict(row) for row in age_band_rows]
    vital_summary_dict = dict(vital_summary) if vital_summary else {}

    def fmt(value: Any, digits: int = 1) -> str:
        return "NA" if value is None else f"{float(value):.{digits}f}"

    sex_text = "、".join(
        f"{row['label']} {row['n']}人（{(row['n'] / total_patients):.1%}）"
        for row in sex_distribution
        if total_patients
    )
    age_text = (
        f"平均年龄 {fmt(age_summary_dict.get('mean'))}岁，"
        f"中位数 {fmt(age_summary_dict.get('median'))}岁，"
        f"范围 {fmt(age_summary_dict.get('min'), 0)}-{fmt(age_summary_dict.get('max'), 0)}岁"
    )
    disease_text = "、".join(f"{row['label']} {row['patient_count']}人" for row in overview["top_diseases"])
    drug_text = "、".join(f"{row['label']} {row['patient_count']}人" for row in overview["top_drugs"])

    return {
        "status": "success",
        "total_patients": total_patients,
        "sex_distribution": sex_distribution,
        "age_summary": age_summary_dict,
        "age_bands": age_bands,
        "vital_summary": vital_summary_dict,
        "top_diseases": overview["top_diseases"],
        "top_drugs": overview["top_drugs"],
        "top_first_occurrences": overview["top_first_occurrences"],
        "suggested_reply": (
            f"主任，这个数据库当前共有 {total_patients} 名受试者。"
            f"性别分布为：{sex_text}。"
            f"年龄分布：{age_text}。"
            f"生命体征方面，收缩压均值 {fmt(vital_summary_dict.get('sbp_mean'))} mmHg，"
            f"舒张压均值 {fmt(vital_summary_dict.get('dbp_mean'))} mmHg。"
            f"最常见的诊断包括：{disease_text}。"
            f"常见药物包括：{drug_text}。"
            "我已优先使用 sex_label、disease_name_cn、drug_name_cn 等语义化字段。"
        ),
    }


async def describe_database_identity() -> dict[str, Any]:
    sample = await get_sample_distribution()
    table_count = 0
    row_count = 0
    connection = await get_db_connection()
    try:
        table_count = await connection.fetchval(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'ukb_semantic'
              AND table_type = 'BASE TABLE';
            """
        )
        row_count = sum(
            [
                sample["total_patients"],
                307052,
                101043,
                9067,
                1101,
                930,
            ]
        )
    finally:
        await release_db_connection(connection)

    disease_text = "、".join(f"{row['label']} {row['patient_count']}人" for row in sample["top_diseases"][:3])
    drug_text = "、".join(f"{row['label']} {row['patient_count']}人" for row in sample["top_drugs"][:3])
    return {
        "status": "success",
        "database": "medical_cohort",
        "schema": "ukb_semantic",
        "table_count": table_count,
        "approx_row_count": row_count,
        "total_patients": sample["total_patients"],
        "core_domains": ["人口学", "诊断", "用药", "住院", "生命体征", "首发事件", "概念字典"],
        "suggested_reply": (
            "主任，这是一个 UKB 风格的医学队列语义库，数据库名是 medical_cohort，"
            "核心 schema 是 ukb_semantic。它目前包含人口学主索引、诊断、用药、住院、"
            "生命体征、首发事件和概念字典等数据域。"
            f"当前可分析受试者 {sample['total_patients']} 人，已经做了中文语义化映射，"
            "所以我会优先用“原发性高血压、二甲双胍、男/女”这类临床可读标签，而不是直接展示代码。"
            f"从数据内容看，常见诊断包括：{disease_text}；常见药物包括：{drug_text}。"
        ),
    }


async def get_research_capabilities() -> dict[str, Any]:
    sample = await get_sample_distribution()
    return {
        "status": "success",
        "recommended_directions": [
            {
                "title": "样本描述与 Table 1",
                "why": "人口学、年龄、血压、诊断和用药字段已经语义化，适合快速生成队列画像。",
            },
            {
                "title": "慢病共病谱分析",
                "why": "高血压、血脂异常、糖尿病、胃食管反流和心梗等诊断已有可观样本量。",
            },
            {
                "title": "血压与心血管代谢结局队列研究",
                "why": "unified_vitals 中有收缩压/舒张压，诊断表中有高血压、心梗、糖尿病等结局。",
            },
            {
                "title": "药物流行病学描述",
                "why": "阿司匹林、阿托伐他汀、比索洛尔、二甲双胍等药物已有使用记录，可做人群特征和用药模式。",
            },
            {
                "title": "住院结局分析",
                "why": "住院表包含入院、出院、住院天数和出院去向，可探索住院负担。",
            },
            {
                "title": "报告与论文草稿",
                "why": "系统已经能生成统计摘要、图表和 Word 报告，后续可扩展为论文方法/结果段。",
            },
        ],
        "not_recommended_yet": [
            "正式孟德尔随机化：当前库里还没有遗传工具变量、GWAS 或 PRS 表，只能做流程原型。",
            "复杂因果推断：可以做 PSM/IPTW 原型，但需要先确认暴露定义、时间零点和混杂变量。",
        ],
        "suggested_reply": (
            "主任，基于当前数据，我建议优先做 6 类工作：\n"
            "1. 样本描述与 Table 1：快速描述 1000 名受试者的人口学、血压、疾病和用药。\n"
            "2. 慢病共病谱分析：围绕原发性高血压、纯高胆固醇血症、2型糖尿病等做共病模式。\n"
            "3. 血压与心血管代谢结局队列研究：例如 SBP/DBP 与高血压、心梗或糖尿病风险。\n"
            "4. 药物流行病学描述：分析阿司匹林、阿托伐他汀、二甲双胍等使用者特征。\n"
            "5. 住院结局分析：探索住院天数、住院负担和再入院相关问题。\n"
            "6. 自动报告：把样本概况、统计结果和图表整理成 Word 报告。\n"
            "目前不建议直接做正式 MR，因为还没有遗传工具变量/GWAS/PRS 数据表。"
        ),
        "sample_context": {
            "total_patients": sample["total_patients"],
            "top_diseases": sample["top_diseases"],
            "top_drugs": sample["top_drugs"],
        },
    }


def explain_analysis_process(previous_kind: str, previous_result: dict[str, Any]) -> dict[str, Any]:
    if not previous_result:
        return {
            "status": "needs_context",
            "suggested_reply": (
                "主任，我还没有可解释的上一轮分析结果。您可以先让我做一次样本概况、慢病共病谱分析、"
                "用药分类或队列预检，然后再问“把分析过程呈现出来”。"
            ),
        }

    if previous_kind == "exploratory_mining":
        pairs = previous_result.get("comorbidity_pairs", [])
        model = previous_result.get("hospitalization_model", {})
        top_pair = pairs[0] if pairs else {}
        auc_text = f"AUC={model.get('auc'):.2f}" if model.get("available") else model.get("message", "模型暂不可用")
        return {
            "status": "success",
            "analysis_type": "analysis_process",
            "source_analysis": previous_kind,
            "steps": [
                {
                    "step": "定义分析对象",
                    "detail": "以 patient_master_index 中 1000 名受试者为母体，按 patient_id 汇总诊断、用药、住院和生命体征。",
                },
                {
                    "step": "构建共病矩阵",
                    "detail": "从 unified_diagnoses 读取 disease_name_cn，按患者去重后形成患者-疾病 0/1 矩阵。",
                },
                {
                    "step": "计算共病组合",
                    "detail": "枚举同一患者身上的疾病两两组合，计算 count、support=组合人数/总人数、confidence=组合人数/疾病A人数。",
                },
                {
                    "step": "住院预测原型",
                    "detail": "从年龄、性别、血压、常见慢病和常见用药构建特征，用随机森林预测是否有住院记录，并计算 ROC/AUC 与特征重要性。",
                },
                {
                    "step": "解释边界",
                    "detail": "这是探索性假设生成，不等于因果结论；正式论文需要预注册主要结局、交叉验证/外部验证和临床变量审查。",
                },
            ],
            "suggested_reply": (
                "主任，可以。上一轮“慢病共病谱分析”的过程是：\n"
                "1. 先以 1000 名受试者为母体，用 patient_id 把诊断、用药、住院和生命体征汇总到患者级。\n"
                "2. 共病部分：从 unified_diagnoses 读取中文疾病名 disease_name_cn，按患者去重，形成“患者-疾病”0/1 矩阵。\n"
                "3. 然后枚举每个患者身上的疾病两两组合，计算：人数、支持度（组合人数/总人数）和置信度（组合人数/疾病A人数）。"
                f"例如当前最强组合是 {top_pair.get('disease_a', 'NA')} + {top_pair.get('disease_b', 'NA')}，"
                f"{top_pair.get('count', 0)} 人。\n"
                "4. 住院预测部分：用年龄、性别、SBP/DBP、高血压、高胆固醇血症、糖尿病、心梗、阿托伐他汀、阿司匹林、二甲双胍等变量，"
                f"训练随机森林预测是否有住院记录，当前 {auc_text}。\n"
                "5. 这一步的定位是“探索性假设生成”：可以帮您发现值得写成课题的方向，但还不能直接当因果结论。"
                "如果要升级成论文级分析，下一步应固定一个主结局、写清 PICO、做交叉验证，并补充偏倚审查。"
            ),
        }

    if previous_kind == "disease_drug_overlap":
        disease = previous_result.get("disease", "目标疾病人群")
        drug = previous_result.get("drug", "目标药物")
        users = previous_result.get("drug_users_in_disease", 0)
        denominator = previous_result.get("disease_patients", 0)
        return {
            "status": "success",
            "analysis_type": "analysis_process",
            "source_analysis": previous_kind,
            "suggested_reply": (
                f"主任，上一轮“{disease} 中{drug}使用情况”的过程是：\n"
                "1. 先在 unified_diagnoses 中按中文疾病名、ICD-10 前缀和英文描述模糊匹配目标疾病，得到患者级疾病人群。\n"
                "2. 再在 unified_medications 中按药物中文名、ATC/原始编码、成分名和商品名匹配目标药物。\n"
                "3. 总用药人数按 patient_id 去重，所以一个患者不管有多少条处方，只算 1 人。\n"
                "4. 药物明细和机制分类按具体药物/机制聚合，所以同一个患者如果联合用药，会进入多个药物或机制类别。\n"
                f"当前口径下，分母是 {denominator} 人，任意{drug}使用者是 {users} 人。"
            ),
        }

    if previous_kind == "disease_intersection":
        diseases = "和".join(item.get("label") or item.get("text") or "疾病" for item in previous_result.get("diseases", []))
        count = previous_result.get("count", 0)
        return {
            "status": "success",
            "analysis_type": "analysis_process",
            "source_analysis": previous_kind,
            "suggested_reply": (
                f"主任，上一轮“{diseases}合并人群”的过程是：先在 unified_diagnoses 中分别为每个疾病建立患者级 0/1 标志，"
                "再取所有疾病标志均为 1 的 patient_id 交集，最后关联 patient_master_index 和 unified_vitals 输出性别、年龄、Townsend 指数和血压。"
                f"当前交集人数为 {count} 人；下载文件也是基于这批 patient_id 导出的。"
            ),
        }

    if previous_kind == "baseline_comparison":
        return {
            "status": "success",
            "analysis_type": "analysis_process",
            "source_analysis": previous_kind,
            "suggested_reply": (
                "主任，上一轮 Table 1 的过程是：先按药物暴露把患者分成使用者和非使用者，连续变量用均值±标准差并做两组比较，"
                "分类变量用 n(%) 并做卡方或 Fisher 检验；高血压、糖尿病等结局按中文疾病名/ICD-10 映射到患者级标志后再计算比例差。"
            ),
        }

    return {
        "status": "success",
        "analysis_type": "analysis_process",
        "source_analysis": previous_kind,
        "suggested_reply": (
            f"主任，上一轮结果类型是 {previous_kind}。我已保留结构化结果，但这个类型还没有专门的过程模板。"
            "一般流程是：先做语义映射和患者级去重，再按问题选择描述统计、交集统计、用药统计或模型分析，最后输出统计口径和可下载明细。"
        ),
    }


async def get_semantic_cohort_candidates(limit: int = 8) -> dict[str, Any]:
    connection = await get_db_connection()
    try:
        rows = await connection.fetch(
            """
            SELECT
                COALESCE(disease_name_cn, mapped_icd10, icd10_description, '待补充字典') AS label,
                MIN(mapped_icd10) AS example_code,
                COUNT(DISTINCT patient_id) AS patient_count,
                COUNT(*) AS record_count,
                BOOL_OR(disease_name_cn IS NOT NULL) AS has_cn_label
            FROM ukb_semantic.unified_diagnoses
            WHERE disease_name_cn IS NOT NULL
               OR mapped_icd10 IS NOT NULL
               OR icd10_description IS NOT NULL
            GROUP BY COALESCE(disease_name_cn, mapped_icd10, icd10_description, '待补充字典')
            ORDER BY has_cn_label DESC, patient_count DESC, record_count DESC
            LIMIT $1;
            """,
            limit,
        )
    finally:
        await release_db_connection(connection)

    candidates = [dict(row) for row in rows]
    readable = []
    for index, item in enumerate(candidates, start=1):
        label = item["label"]
        count = item["patient_count"]
        if item.get("has_cn_label"):
            reason = "已有中文语义标签，适合直接作为临床表型进入队列设计。"
        else:
            reason = "原始编码有数据，但中文字典还需补充，建议先做术语确认。"
        readable.append({**item, "rank": index, "reason": reason, "display": f"{label}（{count}人）"})

    lines = "\n".join(f"{item['rank']}. {item['display']}：{item['reason']}" for item in readable[:5])
    return {
        "status": "success",
        "candidates": readable,
        "suggested_reply": (
            "主任，我先按中文语义标签整理了最适合建队列的候选结局：\n"
            f"{lines}\n"
            "您可以选择一个疾病作为结局；也可以告诉我想把它作为暴露、结局，还是先做人群画像。"
        ),
    }


def _extract_demographic_filters(message: str) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if "男女" in message or "男女性" in message:
        pass
    elif any(term in message for term in {"男", "男性", "男的", "male"}):
        filters["sex_label"] = "男"
    elif any(term in message for term in {"女", "女性", "女的", "female"}):
        filters["sex_label"] = "女"

    age_patterns = [
        (r"(\d{1,3})\s*岁\s*(以上|及以上|以上的|以上所有|大于|超过|多以上)", ">="),
        (r"(大于|超过)\s*(\d{1,3})\s*岁", ">"),
        (r"(\d{1,3})\s*岁\s*(以下|及以下|以内|小于|低于)", "<="),
        (r"(小于|低于)\s*(\d{1,3})\s*岁", "<"),
    ]
    for pattern, operator in age_patterns:
        match = re.search(pattern, message)
        if not match:
            continue
        if match.group(1).isdigit():
            age = int(match.group(1))
        else:
            age = int(match.group(2))
        filters["age_operator"] = operator
        filters["age_value"] = age
        break
    return filters


def _age_filter_sql(operator: str) -> str:
    allowed = {">=", ">", "<=", "<"}
    if operator not in allowed:
        raise ValueError(f"Unsupported age operator: {operator}")
    return f"age_at_recruitment {operator} $1"


async def get_demographic_distribution(entities: ExtractedEntities, message: str = "") -> dict[str, Any]:
    filters = _extract_demographic_filters(message)
    if filters:
        age_value = filters.get("age_value")
        age_operator = filters.get("age_operator")
        sex_value = filters.get("sex_label")
        if age_value is None:
            age_condition = "TRUE"
        else:
            age_condition = _age_filter_sql(age_operator).replace("$1", "$1::numeric")
        sex_condition = "($2::text IS NULL OR COALESCE(sex_label, CASE WHEN sex::text = '1' THEN '男' WHEN sex::text = '0' THEN '女' ELSE sex::text END) = $2::text)"
        where_sql = f"{age_condition} AND {sex_condition}"
        params = [age_value, sex_value]
        connection = await get_db_connection()
        try:
            total_patients = await connection.fetchval("SELECT COUNT(*) FROM ukb_semantic.patient_master_index;")
            count = await connection.fetchval(
                f"""
                SELECT COUNT(*)
                FROM ukb_semantic.patient_master_index
                WHERE {where_sql};
                """,
                *params,
            )
            sex_rows = await connection.fetch(
                f"""
                SELECT
                    COALESCE(sex_label, CASE WHEN sex::text = '1' THEN '男' WHEN sex::text = '0' THEN '女' ELSE sex::text END) AS label,
                    COUNT(*) AS n
                FROM ukb_semantic.patient_master_index
                WHERE {where_sql}
                GROUP BY 1
                ORDER BY n DESC;
                """,
                *params,
            )
            age_summary = await connection.fetchrow(
                f"""
                SELECT
                    COUNT(age_at_recruitment) AS n,
                    AVG(age_at_recruitment) AS mean,
                    MIN(age_at_recruitment) AS min,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY age_at_recruitment) AS median,
                    MAX(age_at_recruitment) AS max
                FROM ukb_semantic.patient_master_index
                WHERE {where_sql};
                """,
                *params,
            )
        finally:
            await release_db_connection(connection)

        parts: list[str] = []
        if "age_value" in filters:
            op_text = {">=": "及以上", ">": "以上", "<=": "及以下", "<": "以下"}[filters["age_operator"]]
            parts.append(f"{filters['age_value']}岁{op_text}")
        if "sex_label" in filters:
            parts.append(filters["sex_label"])
        label = "".join(parts) or "符合条件者"
        percent = count / total_patients if total_patients else 0
        sex_distribution = [dict(row) for row in sex_rows]
        age_summary_dict = dict(age_summary) if age_summary else {}
        age_text = ""
        if age_summary_dict.get("n"):
            age_text = (
                f"；这部分人平均年龄 {float(age_summary_dict['mean']):.1f}岁，"
                f"中位数 {float(age_summary_dict['median']):.1f}岁，"
                f"范围 {float(age_summary_dict['min']):.0f}-{float(age_summary_dict['max']):.0f}岁"
            )
        return {
            "status": "success",
            "analysis_type": "demographic_filtered_count",
            "filters": filters,
            "total_patients": total_patients,
            "count": count,
            "percent": percent,
            "sex_distribution": sex_distribution,
            "age_summary": age_summary_dict,
            "suggested_reply": f"主任，库里{label}共有 {count} 人，占全部 {total_patients} 人的 {percent:.1%}{age_text}。",
        }

    sample = await get_sample_distribution()
    parts: list[str] = []
    if "sex" in entities.demographics or not entities.demographics:
        sex_text = "、".join(
            f"{row['label']} {row['n']}人（{(row['n'] / sample['total_patients']):.1%}）"
            for row in sample["sex_distribution"]
            if sample["total_patients"]
        )
        parts.append(f"性别分布：{sex_text}")
    if "age" in entities.demographics:
        age = sample["age_summary"]
        parts.append(
            f"年龄分布：平均 {float(age['mean']):.1f}岁，中位数 {float(age['median']):.1f}岁，"
            f"范围 {float(age['min']):.0f}-{float(age['max']):.0f}岁"
        )
    return {
        "status": "success",
        "total_patients": sample["total_patients"],
        "sex_distribution": sample["sex_distribution"],
        "age_summary": sample["age_summary"],
        "age_bands": sample["age_bands"],
        "suggested_reply": "主任，" + "；".join(parts) + "。",
    }


async def get_drug_count(drug_text: str) -> dict[str, Any]:
    connection = await get_db_connection()
    try:
        total_patients = await connection.fetchval("SELECT COUNT(*) FROM ukb_semantic.patient_master_index;")
        rows = await connection.fetch(
            """
            SELECT
                COALESCE(drug_name_cn, chemical_substance, product_name, original_code, '未知药物') AS label,
                COUNT(DISTINCT patient_id) AS patient_count,
                COUNT(*) AS record_count
            FROM ukb_semantic.unified_medications
            WHERE drug_name_cn ILIKE '%' || $1 || '%'
               OR chemical_substance ILIKE '%' || $1 || '%'
               OR product_name ILIKE '%' || $1 || '%'
               OR original_code ILIKE '%' || $1 || '%'
            GROUP BY COALESCE(drug_name_cn, chemical_substance, product_name, original_code, '未知药物')
            ORDER BY patient_count DESC, record_count DESC
            LIMIT 10;
            """,
            drug_text,
        )
    finally:
        await release_db_connection(connection)

    matches = [dict(row) for row in rows]
    patient_count = sum(row["patient_count"] for row in matches)
    record_count = sum(row["record_count"] for row in matches)
    prevalence = patient_count / total_patients if total_patients else None
    label = matches[0]["label"] if matches else drug_text
    return {
        "status": "success" if matches else "no_records_found",
        "drug": label,
        "total_patients": total_patients,
        "patient_count": patient_count,
        "record_count": record_count,
        "prevalence": prevalence,
        "matches": matches,
        "suggested_reply": (
            f"主任，库里识别到 {label} 使用者 {patient_count} 人，"
            f"占全部 {total_patients} 人的 {prevalence:.2%}，处方/用药记录 {record_count} 条。"
        )
        if prevalence is not None
        else f"主任，库里识别到 {label} 使用者 {patient_count} 人，记录 {record_count} 条。",
    }


async def get_drug_count_for_entities(entities: ExtractedEntities) -> dict[str, Any]:
    drug_label, drug_text_terms, drug_code_prefixes = _drug_match_terms(entities)
    drug_patterns = [f"%{term}%" for term in drug_text_terms] or ["__NO_DRUG_TEXT__"]
    code_patterns = [f"{term}%" for term in drug_code_prefixes] or ["__NO_DRUG_CODE__"]
    connection = await get_db_connection()
    try:
        total_patients = await connection.fetchval("SELECT COUNT(*) FROM ukb_semantic.patient_master_index;")
        summary = await connection.fetchrow(
            """
            SELECT
                COUNT(DISTINCT patient_id) AS patient_count,
                COUNT(*) AS record_count
            FROM ukb_semantic.unified_medications
            WHERE drug_name_cn ILIKE ANY($1::text[])
               OR original_code ILIKE ANY($2::text[])
               OR chemical_substance ILIKE ANY($1::text[])
               OR product_name ILIKE ANY($1::text[]);
            """,
            drug_patterns,
            code_patterns,
        )
        rows = await connection.fetch(
            """
            SELECT
                COALESCE(drug_name_cn, chemical_substance, product_name, original_code, '未知药物') AS label,
                COUNT(DISTINCT patient_id) AS patient_count,
                COUNT(*) AS record_count
            FROM ukb_semantic.unified_medications
            WHERE drug_name_cn ILIKE ANY($1::text[])
               OR original_code ILIKE ANY($2::text[])
               OR chemical_substance ILIKE ANY($1::text[])
               OR product_name ILIKE ANY($1::text[])
            GROUP BY COALESCE(drug_name_cn, chemical_substance, product_name, original_code, '未知药物')
            ORDER BY patient_count DESC, record_count DESC
            LIMIT 10;
            """,
            drug_patterns,
            code_patterns,
        )
    finally:
        await release_db_connection(connection)

    matches = [dict(row) for row in rows]
    patient_count = summary["patient_count"] if summary else 0
    record_count = summary["record_count"] if summary else 0
    prevalence = patient_count / total_patients if total_patients else None
    match_text = "、".join(f"{row['label']} {row['patient_count']}人" for row in matches[:5]) or "暂无明细"
    return {
        "status": "success" if patient_count else "no_records_found",
        "drug": drug_label,
        "total_patients": total_patients,
        "patient_count": patient_count,
        "record_count": record_count,
        "prevalence": prevalence,
        "matches": matches,
        "suggested_reply": (
            f"主任，库里识别到 {drug_label} 使用者 {patient_count} 人，"
            f"占全部 {total_patients} 人的 {(prevalence or 0):.2%}，处方/用药记录 {record_count} 条。"
            f"匹配到的主要药物包括：{match_text}。"
        ),
    }


def _drug_match_terms(entities: ExtractedEntities) -> tuple[str, list[str], list[str]]:
    if not entities.drugs:
        return "药物", [], []
    drug = entities.drugs[0]
    text_terms = [drug.canonical, drug.text]
    code_prefixes: list[str] = []
    if drug.kind == "drug_class":
        text_terms.extend(drug.metadata.get("text_terms", []))
        code_prefixes.extend(drug.metadata.get("code_prefixes", []))
    elif drug.code:
        code_prefixes.append(drug.code)
    clean_text_terms = sorted({term for term in text_terms if term})
    clean_code_prefixes = sorted({term for term in code_prefixes if term})
    return drug.canonical, clean_text_terms, clean_code_prefixes


def _disease_match_terms(entities: ExtractedEntities, fallback: str | None = None) -> tuple[str, list[str], list[str]]:
    if entities.diseases:
        disease = entities.diseases[0]
        return disease.canonical, [disease.canonical, disease.text], [disease.code] if disease.code else []
    if fallback:
        return fallback, [fallback], []
    return "疾病", [], []


def _single_disease_match_terms(disease: Any) -> tuple[str, list[str], list[str]]:
    text_terms = [disease.canonical, disease.text]
    code_prefixes = [disease.code] if disease.code else []
    clean_text_terms = sorted({term for term in text_terms if term})
    clean_code_prefixes = sorted({term for term in code_prefixes if term})
    return disease.canonical, clean_text_terms, clean_code_prefixes


def _csv_safe(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _translate_antihypertensive(label: str) -> dict[str, str]:
    lowered = label.lower()
    for item in ANTIHYPERTENSIVE_DRUG_MAP:
        if any(pattern in lowered for pattern in item["patterns"]):
            return {"drug_name_cn": item["name_cn"], "mechanism": item["mechanism"]}
    return {"drug_name_cn": "待补充中文名", "mechanism": "未分类降压药"}


def _mechanism_summary_from_records(records: list[dict[str, Any]], denominator: int) -> dict[str, Any]:
    translated_by_label: dict[str, dict[str, Any]] = {}
    mechanisms_by_name: dict[str, dict[str, Any]] = {}
    for record in records:
        patient_id = record.get("patient_id")
        label = record.get("label") or "未知药物"
        translated = _translate_antihypertensive(label)
        drug_row = translated_by_label.setdefault(
            label,
            {
                "drug_label": label,
                "drug_name_cn": translated["drug_name_cn"],
                "mechanism": translated["mechanism"],
                "patient_ids": set(),
                "record_count": 0,
            },
        )
        drug_row["patient_ids"].add(patient_id)
        drug_row["record_count"] += 1

        mechanism_row = mechanisms_by_name.setdefault(
            translated["mechanism"],
            {
                "mechanism": translated["mechanism"],
                "patient_ids": set(),
                "record_count": 0,
                "drugs": {},
            },
        )
        mechanism_row["patient_ids"].add(patient_id)
        mechanism_row["record_count"] += 1
        mechanism_row["drugs"][label] = drug_row

    translated_drugs = []
    for item in translated_by_label.values():
        translated_drugs.append(
            {
                "drug_label": item["drug_label"],
                "drug_name_cn": item["drug_name_cn"],
                "mechanism": item["mechanism"],
                "patient_count": len(item["patient_ids"]),
                "record_count": item["record_count"],
            }
        )
    translated_drugs.sort(key=lambda item: (item["patient_count"], item["record_count"]), reverse=True)

    mechanisms = []
    for item in mechanisms_by_name.values():
        mechanism_drugs = [
            {
                "drug_label": drug["drug_label"],
                "drug_name_cn": drug["drug_name_cn"],
                "mechanism": drug["mechanism"],
                "patient_count": len(drug["patient_ids"]),
                "record_count": drug["record_count"],
            }
            for drug in item["drugs"].values()
        ]
        mechanism_drugs.sort(key=lambda drug: (drug["patient_count"], drug["record_count"]), reverse=True)
        patient_count = len(item["patient_ids"])
        mechanisms.append(
            {
                "mechanism": item["mechanism"],
                "patient_count": patient_count,
                "patient_percent": patient_count / denominator if denominator else 0,
                "record_count": item["record_count"],
                "drugs": mechanism_drugs,
            }
        )
    mechanisms.sort(key=lambda item: (item["patient_count"], item["record_count"]), reverse=True)
    return {"translated_drugs": translated_drugs, "mechanisms": mechanisms}


async def summarize_antihypertensive_mechanisms(
    previous_overlap: dict[str, Any],
    session_id: str | None = None,
) -> dict[str, Any]:
    if previous_overlap.get("mechanisms") and previous_overlap.get("translated_drugs"):
        mechanisms = previous_overlap["mechanisms"]
        translated_rows = previous_overlap["translated_drugs"]
        mechanism_line_parts = []
        for item in mechanisms:
            drug_text = "、".join(f"{drug['drug_name_cn']}（{drug['patient_count']}人）" for drug in item.get("drugs", [])[:4])
            mechanism_line_parts.append(
                f"- {item['mechanism']}：患者级去重 {item['patient_count']}人（{item.get('patient_percent', 0):.1%}）；主要包括 {drug_text}"
            )
        mechanism_lines = "\n".join(mechanism_line_parts)

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe_session = "".join(ch for ch in (session_id or "default") if ch.isalnum() or ch in {"-", "_"})[:48] or "default"
        filename = f"antihypertensive_mechanisms_{safe_session}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        export_path = REPORT_DIR / filename
        with export_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["mechanism", "drug_name_cn", "drug_label", "patient_count", "record_count"],
            )
            writer.writeheader()
            for row in translated_rows:
                writer.writerow({field: _csv_safe(row.get(field)) for field in writer.fieldnames or []})
        download_url = f"/api/download-file/{filename}"
        return {
            "status": "success",
            "analysis_type": "drug_mechanism_summary",
            "disease": previous_overlap.get("disease"),
            "drug": previous_overlap.get("drug"),
            "drug_users_in_disease": previous_overlap.get("drug_users_in_disease"),
            "mechanisms": mechanisms,
            "translated_drugs": translated_rows,
            "counting_note": "这里按机制类别做患者级去重；同一患者如果跨机制联合用药，会分别计入多个机制类别。",
            "download_url": download_url,
            "report_url": download_url,
            "export_filename": filename,
            "suggested_reply": (
                "主任，可以。上一轮药物我已转成中文通用名，并按降压药机制类型做患者级去重汇总：\n"
                f"{mechanism_lines}\n"
                f"上一轮患者级任意降压药使用人数是 {previous_overlap.get('drug_users_in_disease', 0)} 人。"
                "我已导出包含机制类型、中文名、原始药名、患者数和记录数的 CSV，可点击“下载数据”。"
            ),
        }

    top_drugs = previous_overlap.get("top_matching_drugs") or []
    if not top_drugs:
        return {
            "status": "needs_context",
            "suggested_reply": "主任，我需要先有一张药物明细表，您可以先问：糖尿病人群中，吃降压药的有哪些种类，各多少人。",
        }

    translated_rows: list[dict[str, Any]] = []
    mechanism_map: dict[str, dict[str, Any]] = {}
    for item in top_drugs:
        label = item.get("label") or "未知药物"
        translated = _translate_antihypertensive(label)
        patient_count = int(item.get("patient_count") or 0)
        record_count = int(item.get("record_count") or 0)
        row = {
            "drug_label": label,
            "drug_name_cn": translated["drug_name_cn"],
            "mechanism": translated["mechanism"],
            "patient_count": patient_count,
            "record_count": record_count,
        }
        translated_rows.append(row)
        bucket = mechanism_map.setdefault(
            translated["mechanism"],
            {"mechanism": translated["mechanism"], "patient_count_sum": 0, "record_count_sum": 0, "drugs": []},
        )
        bucket["patient_count_sum"] += patient_count
        bucket["record_count_sum"] += record_count
        bucket["drugs"].append(row)

    mechanisms = sorted(mechanism_map.values(), key=lambda item: item["patient_count_sum"], reverse=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_session = "".join(ch for ch in (session_id or "default") if ch.isalnum() or ch in {"-", "_"})[:48] or "default"
    filename = f"antihypertensive_mechanisms_{safe_session}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    export_path = REPORT_DIR / filename
    with export_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["mechanism", "drug_name_cn", "drug_label", "patient_count", "record_count"],
        )
        writer.writeheader()
        for row in translated_rows:
            writer.writerow({field: _csv_safe(row.get(field)) for field in writer.fieldnames or []})

    mechanism_line_parts = []
    for item in mechanisms:
        drug_text = "、".join(f"{drug['drug_name_cn']}（{drug['patient_count']}人）" for drug in item["drugs"][:4])
        mechanism_line_parts.append(
            f"- {item['mechanism']}：药物级患者数合计 {item['patient_count_sum']}；主要包括 {drug_text}"
        )
    mechanism_lines = "\n".join(mechanism_line_parts)
    download_url = f"/api/download-file/{filename}"
    return {
        "status": "success",
        "analysis_type": "drug_mechanism_summary",
        "disease": previous_overlap.get("disease"),
        "drug": previous_overlap.get("drug"),
        "drug_users_in_disease": previous_overlap.get("drug_users_in_disease"),
        "mechanisms": mechanisms,
        "translated_drugs": translated_rows,
        "counting_note": "这里按药物明细聚合到机制类别，患者可能跨多个机制用药，因此各机制患者数相加仍可能大于患者级去重总人数。",
        "download_url": download_url,
        "report_url": download_url,
        "export_filename": filename,
        "suggested_reply": (
            "主任，可以。上一轮药物我已转成中文通用名，并按降压药机制类型汇总：\n"
            f"{mechanism_lines}\n"
            "注意：这是药物级/机制级统计，同一患者如果同时用 CCB 和 ACEI，会分别计入两个机制类别；"
            f"上一轮患者级去重总人数仍是 {previous_overlap.get('drug_users_in_disease', 0)} 人。"
            "我已导出包含机制类型、中文名、原始药名、患者数和记录数的 CSV，可点击“下载数据”。"
        ),
    }


async def get_disease_intersection(entities: ExtractedEntities, session_id: str | None = None) -> dict[str, Any]:
    diseases = entities.diseases[:4]
    if len(diseases) < 2:
        return {
            "status": "needs_clarification",
            "suggested_reply": "主任，请至少告诉我两个疾病，例如“同时得糖尿病和高血压的人有多少”。",
        }

    disease_specs = []
    params: list[Any] = []
    flag_exprs: list[str] = []
    date_exprs: list[str] = []
    required_conditions: list[str] = []
    select_flags: list[str] = []

    for index, disease in enumerate(diseases):
        label, text_terms, code_prefixes = _single_disease_match_terms(disease)
        text_patterns = [f"%{term}%" for term in text_terms] or ["__NO_DISEASE_TEXT__"]
        code_patterns = [f"{term}%" for term in code_prefixes] or ["__NO_DISEASE_CODE__"]
        text_param = len(params) + 1
        params.append(text_patterns)
        code_param = len(params) + 1
        params.append(code_patterns)
        criteria = (
            f"(disease_name_cn ILIKE ANY(${text_param}::text[]) "
            f"OR mapped_icd10 ILIKE ANY(${code_param}::text[]) "
            f"OR icd10_description ILIKE ANY(${text_param}::text[]))"
        )
        flag = f"has_disease_{index}"
        first_date = f"first_disease_{index}_date"
        flag_exprs.append(f"MAX(CASE WHEN {criteria} THEN 1 ELSE 0 END) AS {flag}")
        date_exprs.append(f"MIN(CASE WHEN {criteria} THEN event_date ELSE NULL END) AS {first_date}")
        required_conditions.append(f"COALESCE(df.{flag}, 0) = 1")
        select_flags.append(f"COALESCE(df.{flag}, 0) AS {flag}, df.{first_date}")
        disease_specs.append({"label": label, "code": disease.code, "text": disease.text, "flag": flag, "first_date": first_date})

    sql = f"""
        WITH diagnosis_flags AS (
            SELECT
                patient_id,
                {", ".join(flag_exprs)},
                {", ".join(date_exprs)}
            FROM ukb_semantic.unified_diagnoses
            GROUP BY patient_id
        ),
        cohort AS (
            SELECT
                p.patient_id,
                COALESCE(p.sex_label, p.sex::text, '未知') AS sex_label,
                p.age_at_recruitment,
                p.townsend_deprivation_index,
                v.systolic_bp,
                v.diastolic_bp,
                {", ".join(select_flags)}
            FROM ukb_semantic.patient_master_index AS p
            LEFT JOIN diagnosis_flags AS df ON df.patient_id = p.patient_id
            LEFT JOIN ukb_semantic.unified_vitals AS v ON v.patient_id = p.patient_id
            WHERE {" AND ".join(required_conditions)}
        )
        SELECT *
        FROM cohort
        ORDER BY patient_id;
    """

    connection = await get_db_connection()
    try:
        total_patients = await connection.fetchval("SELECT COUNT(*) FROM ukb_semantic.patient_master_index;")
        rows = await connection.fetch(sql, *params)
    finally:
        await release_db_connection(connection)

    records = [dict(row) for row in rows]
    count = len(records)
    prevalence = count / total_patients if total_patients else 0
    sex_counts: dict[str, int] = {}
    for record in records:
        label = record.get("sex_label") or "未知"
        sex_counts[label] = sex_counts.get(label, 0) + 1
    sex_distribution = [
        {"label": label, "n": n, "percent": n / count if count else 0}
        for label, n in sorted(sex_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_session = "".join(ch for ch in (session_id or "default") if ch.isalnum() or ch in {"-", "_"})[:48] or "default"
    filename = f"disease_intersection_{safe_session}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    export_path = REPORT_DIR / filename
    fieldnames = [
        "patient_id",
        "sex_label",
        "age_at_recruitment",
        "townsend_deprivation_index",
        "systolic_bp",
        "diastolic_bp",
    ]
    for spec in disease_specs:
        fieldnames.extend([spec["flag"], spec["first_date"]])
    with export_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_safe(record.get(field)) for field in fieldnames})

    disease_text = "和".join(spec["label"] for spec in disease_specs)
    sex_text = "、".join(f"{item['label']} {item['n']}人（{item['percent']:.1%}）" for item in sex_distribution) or "暂无性别信息"
    download_url = f"/api/download-file/{filename}"
    return {
        "status": "success",
        "analysis_type": "disease_intersection",
        "diseases": disease_specs,
        "count": count,
        "total_patients": total_patients,
        "prevalence": prevalence,
        "sex_distribution": sex_distribution,
        "download_url": download_url,
        "report_url": download_url,
        "export_filename": filename,
        "suggested_reply": (
            f"主任，同时识别为{disease_text}的受试者共有 {count} 人，"
            f"占全部 {total_patients} 人的 {prevalence:.2%}。"
            f"这部分人群的性别分布为：{sex_text}。"
            "我已经把这些患者的 patient_id、性别、年龄、Townsend 指数、血压和各疾病首次诊断日期导出为 CSV，"
            "可以点击“下载数据”获取。"
        ),
    }


async def get_variable_distribution(entities: ExtractedEntities) -> dict[str, Any]:
    connection = await get_db_connection()
    try:
        if entities.exposures and entities.exposures[0].code in {"systolic_bp", "diastolic_bp"}:
            column = entities.exposures[0].code
            label = entities.exposures[0].metadata.get("label") or entities.exposures[0].canonical
            row = await connection.fetchrow(
                f"""
                SELECT
                    COUNT({column}) AS n,
                    AVG({column}) AS mean,
                    STDDEV({column}) AS sd,
                    MIN({column}) AS min,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {column}) AS median,
                    MAX({column}) AS max
                FROM ukb_semantic.unified_vitals;
                """
            )
            summary = dict(row)
            return {
                "status": "success",
                "variable": label,
                "summary": summary,
                "suggested_reply": (
                    f"主任，{label} 共有 {summary['n']} 个有效值，"
                    f"均值 {float(summary['mean']):.1f}，标准差 {float(summary['sd']):.1f}，"
                    f"中位数 {float(summary['median']):.1f}，范围 {float(summary['min']):.1f}-{float(summary['max']):.1f}。"
                ),
            }
    finally:
        await release_db_connection(connection)

    return {
        "status": "needs_clarification",
        "suggested_reply": "主任，您想看哪个变量的分布？目前可直接查看：收缩压、舒张压、年龄、性别、常见疾病和常见药物。",
    }


async def explain_terms(entities: ExtractedEntities, message: str) -> dict[str, Any]:
    terms: list[dict[str, Any]] = []
    for exposure in entities.exposures:
        if exposure.canonical == "SBP":
            terms.append(
                {
                    "term": "SBP",
                    "name_cn": "收缩压",
                    "domain": "生命体征/暴露变量",
                    "storage": "ukb_semantic.unified_vitals.systolic_bp",
                    "meaning": "心脏收缩时动脉内的压力，常用于定义血压水平、心血管风险暴露或协变量。",
                }
            )
        elif exposure.canonical == "DBP":
            terms.append(
                {
                    "term": "DBP",
                    "name_cn": "舒张压",
                    "domain": "生命体征/暴露变量",
                    "storage": "ukb_semantic.unified_vitals.diastolic_bp",
                    "meaning": "心脏舒张时动脉内的压力，可与 SBP 一起描述血压水平。",
                }
            )
        elif exposure.canonical == "LDL-C":
            terms.append(
                {
                    "term": "LDL-C",
                    "name_cn": "低密度脂蛋白胆固醇",
                    "domain": "检验/暴露变量",
                    "storage": "当前样例库尚未接入标准 LDL-C 字段",
                    "meaning": "血脂指标，常用于动脉粥样硬化和心血管风险研究。",
                }
            )

    for disease in entities.diseases:
        if disease.code == "G30":
            terms.append(
                {
                    "term": "G30",
                    "name_cn": "阿尔茨海默病",
                    "domain": "ICD-10 疾病结局",
                    "storage": "ukb_semantic.unified_diagnoses.mapped_icd10 / disease_name_cn",
                    "meaning": "ICD-10 中阿尔茨海默病相关编码，常作为痴呆/阿尔茨海默结局的候选定义。",
                }
            )
        else:
            terms.append(
                {
                    "term": disease.code or disease.text,
                    "name_cn": disease.canonical,
                    "domain": "ICD-10 疾病表型",
                    "storage": "ukb_semantic.unified_diagnoses.mapped_icd10 / disease_name_cn",
                    "meaning": f"{disease.canonical} 对应的疾病表型，可用于患病人数查询、队列结局或协变量定义。",
                }
            )

    if not terms:
        return {
            "status": "needs_clarification",
            "suggested_reply": "主任，您想解释哪个术语？例如 SBP 是收缩压，G30 是 ICD-10 阿尔茨海默病编码。",
        }

    lines = "\n".join(
        f"- {item['term']}：{item['name_cn']}。{item['domain']}，库中位置：{item['storage']}。{item['meaning']}"
        for item in terms
    )
    return {
        "status": "success",
        "terms": terms,
        "suggested_reply": (
            "主任，这两个不是神秘代码，是研究设计里的变量/结局写法：\n"
            f"{lines}\n"
            "所以“做 SBP 与 G30 的队列研究”的意思是：以收缩压作为暴露变量，观察后续阿尔茨海默病相关诊断结局。"
        ),
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _sd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def _format_mean_sd(values: list[float]) -> str:
    avg = _mean(values)
    sd = _sd(values)
    if avg is None:
        return "NA"
    if sd is None:
        return f"{avg:.1f}"
    return f"{avg:.1f} ± {sd:.1f}"


def _p_ttest(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    try:
        from scipy import stats

        result = stats.ttest_ind(a, b, equal_var=False, nan_policy="omit")
        return float(result.pvalue) if result.pvalue == result.pvalue else None
    except Exception:
        return None


def _p_chi_square(table: list[list[int]]) -> float | None:
    try:
        from scipy import stats

        result = stats.chi2_contingency(table)
        return float(result.pvalue) if result.pvalue == result.pvalue else None
    except Exception:
        return None


def _fmt_p(value: float | None) -> str:
    if value is None:
        return "NA"
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}"


def _count_percent(count: int, denominator: int) -> str:
    pct = count / denominator if denominator else 0
    return f"{count} ({pct:.1%})"


async def compare_drug_event_rate(entities: ExtractedEntities, message: str) -> dict[str, Any]:
    if not entities.drugs:
        return {
            "status": "needs_clarification",
            "suggested_reply": "主任，请先告诉我要比较哪类药物，例如降压药、CCB、ACEI、ARB 或某个具体药物。",
        }
    if not entities.diseases:
        return {
            "status": "needs_outcome",
            "analysis_type": "drug_event_rate",
            "drug": entities.drugs[0].canonical,
            "suggested_reply": (
                f"主任，这个问题问得对，但还缺一个关键定义：‘事件’具体指哪个结局？\n"
                f"我已识别到暴露是 {entities.drugs[0].canonical}，但不能默认把所有事件混在一起。"
                "您可以指定：心梗、脑卒中、2型糖尿病、住院，或其他 ICD-10 结局。\n"
                "例如可以问：‘不同类型降压药患者未来心梗发生率有不同吗？’ "
                "或 ‘高血压患者中，不同降压药类型的脑卒中发生率有差异吗？’"
            ),
            "options": [
                {"value": "不同类型降压药患者心梗发生率有不同吗", "label": "心梗"},
                {"value": "不同类型降压药患者脑卒中发生率有不同吗", "label": "脑卒中"},
                {"value": "不同类型降压药患者2型糖尿病发生率有不同吗", "label": "2型糖尿病"},
            ],
        }

    drug_label, drug_text_terms, drug_code_prefixes = _drug_match_terms(entities)
    outcome_label, outcome_text_terms, outcome_code_prefixes = _single_disease_match_terms(entities.diseases[0])
    drug_patterns = [f"%{term}%" for term in drug_text_terms] or ["__NO_DRUG_TEXT__"]
    drug_code_patterns = [f"{term}%" for term in drug_code_prefixes] or ["__NO_DRUG_CODE__"]
    outcome_patterns = [f"%{term}%" for term in outcome_text_terms] or ["__NO_OUTCOME_TEXT__"]
    outcome_code_patterns = [f"{term}%" for term in outcome_code_prefixes] or ["__NO_OUTCOME_CODE__"]

    connection = await get_db_connection()
    try:
        medication_rows = await connection.fetch(
            """
            SELECT
                patient_id,
                COALESCE(drug_name_cn, chemical_substance, product_name, original_code, '未知药物') AS label
            FROM ukb_semantic.unified_medications
            WHERE drug_name_cn ILIKE ANY($1::text[])
               OR original_code ILIKE ANY($2::text[])
               OR chemical_substance ILIKE ANY($1::text[])
               OR product_name ILIKE ANY($1::text[]);
            """,
            drug_patterns,
            drug_code_patterns,
        )
        outcome_rows = await connection.fetch(
            """
            SELECT DISTINCT patient_id
            FROM ukb_semantic.unified_diagnoses
            WHERE disease_name_cn ILIKE ANY($1::text[])
               OR mapped_icd10 ILIKE ANY($2::text[])
               OR icd10_description ILIKE ANY($1::text[]);
            """,
            outcome_patterns,
            outcome_code_patterns,
        )
    finally:
        await release_db_connection(connection)

    outcome_patients = {row["patient_id"] for row in outcome_rows}
    medication_records = [dict(row) for row in medication_rows]
    mechanism_data = _mechanism_summary_from_records(medication_records, denominator=0)
    rows: list[dict[str, Any]] = []
    for item in mechanism_data["mechanisms"]:
        patient_ids: set[Any] = set()
        for drug in item.get("drugs", []):
            label = drug.get("drug_label")
            for record in medication_records:
                if record.get("label") == label:
                    patient_ids.add(record.get("patient_id"))
        n = len(patient_ids)
        events = len(patient_ids & outcome_patients)
        rate = events / n if n else 0
        rows.append(
            {
                "mechanism": item["mechanism"],
                "patient_count": n,
                "event_count": events,
                "event_rate": rate,
                "top_drugs": item.get("drugs", [])[:4],
            }
        )
    rows.sort(key=lambda item: (item["patient_count"], item["event_count"]), reverse=True)
    rows = [row for row in rows if row["patient_count"] > 0]

    contingency = [[row["event_count"], row["patient_count"] - row["event_count"]] for row in rows if row["patient_count"] > 0]
    p_value = _p_chi_square(contingency) if len(contingency) >= 2 else None
    lines = "\n".join(
        f"| {row['mechanism']} | {row['patient_count']} | {row['event_count']} | {row['event_rate']:.1%} |"
        for row in rows[:10]
    )
    if not lines:
        lines = "| 暂无可分组记录 | 0 | 0 | 0.0% |"
    interpretation = (
        f"粗略组间比较 P={_fmt_p(p_value)}。" if p_value is not None else "当前可比较组数不足，暂不计算组间 P 值。"
    )
    if p_value is not None and p_value < 0.05:
        interpretation += "不同降压药机制组的粗事件率存在统计学差异；但这是未调整比较，不能直接解释为药物因果效应。"
    else:
        interpretation += "当前未见明确统计学差异；但这是未调整比较，仍需结合样本量、混杂和随访时间。"

    return {
        "status": "success",
        "analysis_type": "drug_event_rate",
        "drug": drug_label,
        "outcome": outcome_label,
        "groups": rows,
        "p_value": p_value,
        "p_value_display": _fmt_p(p_value),
        "counting_note": "按降压药机制做患者级去重；同一患者可使用多种机制药物，因此可进入多个机制组。事件为诊断表中识别到目标结局的患者级标志。",
        "suggested_reply": (
            f"主任，这次问题应该按‘{drug_label}类型/机制分组的 {outcome_label} 事件率’来分析，而不是只数用药人数。\n\n"
            f"| 降压药类型 | 患者数 | {outcome_label}事件数 | 事件率 |\n"
            "|---|---:|---:|---:|\n"
            f"{lines}\n\n"
            f"{interpretation}"
            "注意：这只是粗发生率比较，尚未统一 time zero、随访时间，也未调整年龄、性别、糖尿病、高血脂等混杂因素。"
            "如果要做论文级结论，建议进一步做 Cox/Poisson 回归，并考虑 PSM/IPTW 或新使用者设计。"
        ),
    }

async def compare_drug_baseline(entities: ExtractedEntities, message: str) -> dict[str, Any]:
    if not entities.drugs:
        return {
            "status": "needs_clarification",
            "suggested_reply": "主任，请告诉我要比较哪一种药物，例如阿托伐他汀、二甲双胍或阿司匹林。",
        }

    drug_label, drug_text_terms, drug_code_prefixes = _drug_match_terms(entities)
    drug_patterns = [f"%{term}%" for term in drug_text_terms]
    code_patterns = [f"{term}%" for term in drug_code_prefixes]
    connection = await get_db_connection()
    try:
        rows = await connection.fetch(
            """
            WITH drug_users AS (
                SELECT DISTINCT patient_id
                FROM ukb_semantic.unified_medications
                WHERE drug_name_cn ILIKE ANY($1::text[])
                   OR original_code ILIKE ANY($2::text[])
                   OR chemical_substance ILIKE ANY($1::text[])
                   OR product_name ILIKE ANY($1::text[])
            ),
            diagnosis_flags AS (
                SELECT
                    patient_id,
                    MAX(CASE
                        WHEN disease_name_cn = '原发性高血压'
                          OR mapped_icd10 ILIKE '%I10%'
                          OR icd10_description ILIKE '%hypertension%'
                        THEN 1 ELSE 0 END) AS hypertension,
                    MAX(CASE
                        WHEN disease_name_cn = '2型糖尿病'
                          OR mapped_icd10 ILIKE '%E11%'
                          OR icd10_description ILIKE '%type 2 diabetes%'
                        THEN 1 ELSE 0 END) AS diabetes
                FROM ukb_semantic.unified_diagnoses
                GROUP BY patient_id
            )
            SELECT
                p.patient_id,
                CASE WHEN du.patient_id IS NULL THEN 0 ELSE 1 END AS exposed,
                p.age_at_recruitment::float AS age,
                COALESCE(p.sex_label, p.sex::text, '未知') AS sex_label,
                p.townsend_deprivation_index::float AS townsend,
                v.systolic_bp::float AS sbp,
                v.diastolic_bp::float AS dbp,
                COALESCE(df.hypertension, 0) AS hypertension,
                COALESCE(df.diabetes, 0) AS diabetes
            FROM ukb_semantic.patient_master_index AS p
            LEFT JOIN drug_users AS du ON du.patient_id = p.patient_id
            LEFT JOIN ukb_semantic.unified_vitals AS v ON v.patient_id = p.patient_id
            LEFT JOIN diagnosis_flags AS df ON df.patient_id = p.patient_id
            ORDER BY p.patient_id;
            """,
            drug_patterns or ["__NO_TEXT_MATCH__"],
            code_patterns or ["__NO_CODE_MATCH__"],
        )
    finally:
        await release_db_connection(connection)

    data = [dict(row) for row in rows]
    exposed = [row for row in data if row["exposed"] == 1]
    unexposed = [row for row in data if row["exposed"] == 0]

    def vals(group: list[dict[str, Any]], key: str) -> list[float]:
        return [float(row[key]) for row in group if row.get(key) is not None]

    def positive(group: list[dict[str, Any]], key: str) -> int:
        return sum(1 for row in group if int(row.get(key) or 0) == 1)

    def sex_count(group: list[dict[str, Any]], label: str) -> int:
        return sum(1 for row in group if row.get("sex_label") == label)

    n_exp = len(exposed)
    n_unexp = len(unexposed)
    table1: list[dict[str, Any]] = []
    for key, label in [("age", "年龄，岁"), ("sbp", "收缩压，mmHg"), ("dbp", "舒张压，mmHg"), ("townsend", "Townsend 指数")]:
        exp_values = vals(exposed, key)
        unexp_values = vals(unexposed, key)
        table1.append(
            {
                "variable": label,
                "type": "continuous",
                "exposed": _format_mean_sd(exp_values),
                "unexposed": _format_mean_sd(unexp_values),
                "p_value": _p_ttest(exp_values, unexp_values),
                "p_value_display": _fmt_p(_p_ttest(exp_values, unexp_values)),
            }
        )

    for label in ["男", "女"]:
        exp_count = sex_count(exposed, label)
        unexp_count = sex_count(unexposed, label)
        other_exp = n_exp - exp_count
        other_unexp = n_unexp - unexp_count
        p_value = _p_chi_square([[exp_count, other_exp], [unexp_count, other_unexp]])
        table1.append(
            {
                "variable": f"性别：{label}",
                "type": "categorical",
                "exposed": _count_percent(exp_count, n_exp),
                "unexposed": _count_percent(unexp_count, n_unexp),
                "p_value": p_value,
                "p_value_display": _fmt_p(p_value),
            }
        )

    disease_rows: list[dict[str, Any]] = []
    for key, label in [("hypertension", "原发性高血压"), ("diabetes", "2型糖尿病")]:
        exp_count = positive(exposed, key)
        unexp_count = positive(unexposed, key)
        exp_rate = exp_count / n_exp if n_exp else 0
        unexp_rate = unexp_count / n_unexp if n_unexp else 0
        p_value = _p_chi_square([[exp_count, n_exp - exp_count], [unexp_count, n_unexp - unexp_count]])
        item = {
            "variable": label,
            "type": "categorical",
            "exposed": _count_percent(exp_count, n_exp),
            "unexposed": _count_percent(unexp_count, n_unexp),
            "difference_percentage_points": (exp_rate - unexp_rate) * 100,
            "p_value": p_value,
            "p_value_display": _fmt_p(p_value),
        }
        disease_rows.append(item)
        table1.append(item)

    significant = [row for row in table1 if row.get("p_value") is not None and row["p_value"] < 0.05]
    table_lines = "\n".join(
        f"| {row['variable']} | {row['exposed']} | {row['unexposed']} | {row['p_value_display']} |"
        for row in table1
    )
    disease_text = "；".join(
        f"{row['variable']}：{drug_label}组 {row['exposed']}，非{drug_label}组 {row['unexposed']}，差 {row['difference_percentage_points']:.1f} 个百分点，P={row['p_value_display']}"
        for row in disease_rows
    )
    signal_text = (
        "存在统计学差异的项目包括：" + "、".join(row["variable"] for row in significant) + "。"
        if significant
        else "当前样本下未发现 P<0.05 的基线差异；但样本量较小，仍建议结合临床意义判断。"
    )
    return {
        "status": "success",
        "analysis_type": "drug_baseline_comparison",
        "drug": drug_label,
        "drug_code": entities.drugs[0].code,
        "drug_match_terms": drug_text_terms,
        "drug_code_prefixes": drug_code_prefixes,
        "n_exposed": n_exp,
        "n_unexposed": n_unexp,
        "table1": table1,
        "disease_comparison": disease_rows,
        "suggested_reply": (
            f"主任，我自动把“{entities.drugs[0].text}”识别为 {drug_label}，并把人群分成 {drug_label} 使用者 "
            f"{n_exp} 人和未使用者 {n_unexp} 人。下面是标准 Table 1（连续变量为 Mean ± SD，分类变量为 n(%)）：\n\n"
            f"| 变量 | {drug_label}组 | 非{drug_label}组 | P值 |\n"
            "|---|---:|---:|---:|\n"
            f"{table_lines}\n\n"
            f"重点疾病比例差异：{disease_text}。\n"
            f"{signal_text}"
        ),
    }


async def causal_safety_review(entities: ExtractedEntities, message: str) -> dict[str, Any]:
    drug = entities.drugs[0].canonical if entities.drugs else "该药物"
    disease_names = [item.canonical for item in entities.diseases]
    disease_text = "、".join(disease_names) if disease_names else "相关疾病"
    return {
        "status": "blocked_for_methodology_review",
        "drug": drug,
        "diseases": disease_names,
        "biases": [
            {
                "name": "适应症混杂",
                "explanation": f"{drug} 的使用通常由基础疾病决定；如果比较使用者和非使用者，{disease_text} 等基础风险可能严重不平衡。",
            },
            {
                "name": "不朽时间偏倚",
                "explanation": "如果用药发生在随访中途，把患者固定分为用药组会要求其必须活到开始用药时点，直接 Cox 会偏倚。",
            },
            {
                "name": "时间零点不一致",
                "explanation": "暴露定义、入组日期和结局风险起点必须对齐，否则 HR 没有清晰解释。",
            },
        ],
        "recommended_design": [
            "先限制为有可比适应症的人群，例如高血压合并糖尿病患者。",
            "采用 New-user design：以首次用药日期或匹配的伪起始日期作为 time zero。",
            "使用 PSM/IPTW 平衡年龄、性别、血压、糖尿病、高血脂、既往住院和既往心血管病史。",
            "平衡后再做 Cox；如果用药随时间变化，应考虑 time-dependent Cox。",
        ],
        "suggested_reply": (
            "主任，这个问题我不能直接跑 Cox 给 HR，因为直接跑会有较高概率得出错误因果结论。\n\n"
            f"第一，存在适应症混杂：{drug} 的使用不是随机的，用药者往往有不同基础疾病和风险谱。"
            "例如二甲双胍使用者大概率合并糖尿病，而糖尿病本身就是心梗强危险因素。\n"
            "第二，存在不朽时间偏倚：如果患者随访中途才开始用药，直接按“吃/不吃”固定分组，"
            "会把开始用药前必须存活的时间错误归入用药组。\n"
            "第三，time zero 必须统一：入组、暴露开始和结局随访起点要清楚定义。\n\n"
            "我建议替代方案是：先定义高血压合并糖尿病人群，采用 New-user design，"
            "用 PSM 或 IPTW 平衡年龄、性别、血压、血脂异常、既往住院和既往心血管病史，"
            "再进行 Cox 或 time-dependent Cox。是否按这个更稳妥的方案进入数据预检？"
        ),
    }


async def disease_drug_overlap(
    entities: ExtractedEntities,
    fallback_disease: str | None = None,
    cohort_context: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    if not entities.drugs:
        return {
            "status": "needs_clarification",
            "suggested_reply": "主任，请告诉我要看哪类药物，例如降压药、CCB、ARB、ACEI 或二甲双胍。",
        }
    drug_label, drug_text_terms, drug_code_prefixes = _drug_match_terms(entities)
    params: list[Any] = []

    if cohort_context and cohort_context.get("diseases"):
        disease_specs = cohort_context["diseases"]
        disease_label = "合并".join(item.get("label") or item.get("text") or "疾病" for item in disease_specs)
        flag_exprs = []
        required_flags = []
        for index, disease in enumerate(disease_specs):
            text_terms = [disease.get("label"), disease.get("text")]
            code_terms = [disease.get("code")]
            text_patterns = [f"%{term}%" for term in text_terms if term] or ["__NO_DISEASE_TEXT__"]
            code_patterns = [f"{term}%" for term in code_terms if term] or ["__NO_DISEASE_CODE__"]
            text_param = len(params) + 1
            params.append(text_patterns)
            code_param = len(params) + 1
            params.append(code_patterns)
            criteria = (
                f"(disease_name_cn ILIKE ANY(${text_param}::text[]) "
                f"OR mapped_icd10 ILIKE ANY(${code_param}::text[]) "
                f"OR icd10_description ILIKE ANY(${text_param}::text[]))"
            )
            flag = f"has_disease_{index}"
            flag_exprs.append(f"MAX(CASE WHEN {criteria} THEN 1 ELSE 0 END) AS {flag}")
            required_flags.append(f"COALESCE({flag}, 0) = 1")
        disease_cte = f"""
            disease_flags AS (
                SELECT patient_id, {", ".join(flag_exprs)}
                FROM ukb_semantic.unified_diagnoses
                GROUP BY patient_id
            ),
            disease_patients AS (
                SELECT patient_id
                FROM disease_flags
                WHERE {" AND ".join(required_flags)}
            )
        """
    else:
        disease_label, disease_text_terms, disease_code_prefixes = _disease_match_terms(entities, fallback=fallback_disease)
        disease_patterns = [f"%{term}%" for term in disease_text_terms] or ["__NO_DISEASE_TEXT__"]
        disease_code_patterns = [f"{term}%" for term in disease_code_prefixes] or ["__NO_DISEASE_CODE__"]
        disease_text_param = len(params) + 1
        params.append(disease_patterns)
        disease_code_param = len(params) + 1
        params.append(disease_code_patterns)
        disease_cte = f"""
            disease_patients AS (
                SELECT DISTINCT patient_id
                FROM ukb_semantic.unified_diagnoses
                WHERE disease_name_cn ILIKE ANY(${disease_text_param}::text[])
                   OR mapped_icd10 ILIKE ANY(${disease_code_param}::text[])
                   OR icd10_description ILIKE ANY(${disease_text_param}::text[])
            )
        """

    drug_patterns = [f"%{term}%" for term in drug_text_terms] or ["__NO_DRUG_TEXT__"]
    drug_code_patterns = [f"{term}%" for term in drug_code_prefixes] or ["__NO_DRUG_CODE__"]
    drug_text_param = len(params) + 1
    params.append(drug_patterns)
    drug_code_param = len(params) + 1
    params.append(drug_code_patterns)

    connection = await get_db_connection()
    try:
        row = await connection.fetchrow(
            f"""
            WITH {disease_cte},
            drug_users AS (
                SELECT DISTINCT patient_id
                FROM ukb_semantic.unified_medications
                WHERE drug_name_cn ILIKE ANY(${drug_text_param}::text[])
                   OR original_code ILIKE ANY(${drug_code_param}::text[])
                   OR chemical_substance ILIKE ANY(${drug_text_param}::text[])
                   OR product_name ILIKE ANY(${drug_text_param}::text[])
            ),
            all_patients AS (
                SELECT COUNT(*) AS total_n FROM ukb_semantic.patient_master_index
            )
            SELECT
                (SELECT total_n FROM all_patients) AS total_patients,
                COUNT(dp.patient_id) AS disease_patients,
                COUNT(du.patient_id) AS disease_drug_users,
                COUNT(dp.patient_id) - COUNT(du.patient_id) AS disease_non_users
            FROM disease_patients AS dp
            LEFT JOIN drug_users AS du ON du.patient_id = dp.patient_id;
            """,
            *params,
        )
        mechanism_rows = await connection.fetch(
            f"""
            WITH {disease_cte}
            SELECT
                COALESCE(drug_name_cn, chemical_substance, product_name, original_code, '未知药物') AS label,
                COUNT(DISTINCT m.patient_id) AS patient_count,
                COUNT(*) AS record_count
            FROM ukb_semantic.unified_medications AS m
            JOIN disease_patients AS dp ON dp.patient_id = m.patient_id
            WHERE drug_name_cn ILIKE ANY(${drug_text_param}::text[])
               OR original_code ILIKE ANY(${drug_code_param}::text[])
               OR chemical_substance ILIKE ANY(${drug_text_param}::text[])
               OR product_name ILIKE ANY(${drug_text_param}::text[])
            GROUP BY COALESCE(drug_name_cn, chemical_substance, product_name, original_code, '未知药物')
            ORDER BY patient_count DESC, record_count DESC
            """,
            *params,
        )
        medication_record_rows = await connection.fetch(
            f"""
            WITH {disease_cte}
            SELECT
                m.patient_id,
                COALESCE(m.drug_name_cn, m.chemical_substance, m.product_name, m.original_code, '未知药物') AS label
            FROM ukb_semantic.unified_medications AS m
            JOIN disease_patients AS dp ON dp.patient_id = m.patient_id
            WHERE m.drug_name_cn ILIKE ANY(${drug_text_param}::text[])
               OR m.original_code ILIKE ANY(${drug_code_param}::text[])
               OR m.chemical_substance ILIKE ANY(${drug_text_param}::text[])
               OR m.product_name ILIKE ANY(${drug_text_param}::text[]);
            """,
            *params,
        )
        sex_rows = await connection.fetch(
            f"""
            WITH {disease_cte},
            drug_users AS (
                SELECT DISTINCT patient_id
                FROM ukb_semantic.unified_medications
                WHERE drug_name_cn ILIKE ANY(${drug_text_param}::text[])
                   OR original_code ILIKE ANY(${drug_code_param}::text[])
                   OR chemical_substance ILIKE ANY(${drug_text_param}::text[])
                   OR product_name ILIKE ANY(${drug_text_param}::text[])
            )
            SELECT
                COALESCE(p.sex_label, CASE WHEN p.sex::text = '1' THEN '男' WHEN p.sex::text = '0' THEN '女' ELSE p.sex::text END, '未知') AS label,
                COUNT(DISTINCT p.patient_id) AS n
            FROM disease_patients AS dp
            JOIN drug_users AS du ON du.patient_id = dp.patient_id
            JOIN ukb_semantic.patient_master_index AS p ON p.patient_id = dp.patient_id
            GROUP BY 1
            ORDER BY n DESC;
            """,
            *params,
        )
    finally:
        await release_db_connection(connection)

    summary = dict(row)
    disease_n = summary.get("disease_patients") or 0
    drug_n = summary.get("disease_drug_users") or 0
    non_user_n = summary.get("disease_non_users") or 0
    rate = drug_n / disease_n if disease_n else 0
    top_drugs = [dict(item) for item in mechanism_rows]
    medication_records = [dict(item) for item in medication_record_rows]
    sex_distribution = [dict(item) for item in sex_rows]
    sex_text = "、".join(
        f"{item['label']} {item['n']}人（{(item['n'] / drug_n if drug_n else 0):.1%}）"
        for item in sex_distribution
    )
    mechanism_summary = _mechanism_summary_from_records(medication_records, denominator=drug_n)
    per_drug_patient_count_sum = sum(item["patient_count"] for item in top_drugs)
    top_text = "、".join(f"{item['label']} {item['patient_count']}人" for item in top_drugs[:5]) or "暂无可识别药物明细"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_session = "".join(ch for ch in (session_id or "default") if ch.isalnum() or ch in {"-", "_"})[:48] or "default"
    filename = f"disease_drug_overlap_{safe_session}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    export_path = REPORT_DIR / filename
    with export_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["drug_label", "drug_name_cn", "mechanism", "patient_count", "record_count"])
        writer.writeheader()
        translated_by_label = {item["drug_label"]: item for item in mechanism_summary["translated_drugs"]}
        for item in top_drugs:
            translated = translated_by_label.get(item.get("label"), {})
            writer.writerow(
                {
                    "drug_label": _csv_safe(item.get("label")),
                    "drug_name_cn": _csv_safe(translated.get("drug_name_cn")),
                    "mechanism": _csv_safe(translated.get("mechanism")),
                    "patient_count": _csv_safe(item.get("patient_count")),
                    "record_count": _csv_safe(item.get("record_count")),
                }
            )
    download_url = f"/api/download-file/{filename}"
    mechanism_text = "；".join(
        f"{item['mechanism']} {item['patient_count']}人（{item['patient_percent']:.1%}）"
        for item in mechanism_summary["mechanisms"][:6]
    )
    return {
        "status": "success",
        "analysis_type": "disease_drug_overlap",
        "disease": disease_label,
        "drug": drug_label,
        "disease_patients": disease_n,
        "drug_users_in_disease": drug_n,
        "drug_non_users_in_disease": non_user_n,
        "drug_use_rate_in_disease": rate,
        "sex_distribution": sex_distribution,
        "top_matching_drugs": top_drugs,
        "translated_drugs": mechanism_summary["translated_drugs"],
        "mechanisms": mechanism_summary["mechanisms"],
        "per_drug_patient_count_sum": per_drug_patient_count_sum,
        "counting_note": "总用药人数是患者级去重；各具体药物人数是药物级去重，同一患者可使用多种药，因此各药人数相加可大于总用药人数。",
        "download_url": download_url,
        "report_url": download_url,
        "export_filename": filename,
        "suggested_reply": (
            f"主任，在库里识别到的 {disease_label} 患者 {disease_n} 人中，"
            f"有 {drug_n} 人使用过{drug_label}，占 {rate:.1%}；"
            f"另有 {non_user_n} 人没有识别到{drug_label}记录。"
            f"使用者性别分布为：{sex_text or '暂无性别信息'}。"
            f"这类药物中出现较多的是：{top_text}。"
            f"按降压药类型做患者级去重后，主要类型为：{mechanism_text or '暂无可分类类型'}。"
            f"各具体药物人数相加为 {per_drug_patient_count_sum}，会大于 {drug_n}，因为同一个患者可能同时用过多种降压药。"
            "我已把药物种类、患者数和记录数导出为 CSV，可点击“下载数据”获取。"
            "注意：这里是处方/用药记录识别，不等同于真实服药依从性；如果要做疗效研究，还需要定义首次用药日期、剂量和随访窗口。"
        ),
    }


async def exploratory_mining() -> dict[str, Any]:
    connection = await get_db_connection()
    try:
        total_patients = await connection.fetchval("SELECT COUNT(*) FROM ukb_semantic.patient_master_index;")
        disease_rows = await connection.fetch(
            """
            SELECT patient_id, disease_name_cn
            FROM ukb_semantic.unified_diagnoses
            WHERE disease_name_cn IS NOT NULL;
            """
        )
        prediction_rows = await connection.fetch(
            """
            WITH disease_flags AS (
                SELECT
                    patient_id,
                    MAX(CASE WHEN disease_name_cn = '原发性高血压' THEN 1 ELSE 0 END) AS hypertension,
                    MAX(CASE WHEN disease_name_cn = '纯高胆固醇血症' THEN 1 ELSE 0 END) AS hyperchol,
                    MAX(CASE WHEN disease_name_cn = '2型糖尿病' THEN 1 ELSE 0 END) AS diabetes,
                    MAX(CASE WHEN disease_name_cn = '急性心肌梗死' THEN 1 ELSE 0 END) AS ami
                FROM ukb_semantic.unified_diagnoses
                GROUP BY patient_id
            ),
            med_flags AS (
                SELECT
                    patient_id,
                    MAX(CASE WHEN drug_name_cn = '阿托伐他汀' THEN 1 ELSE 0 END) AS atorvastatin,
                    MAX(CASE WHEN drug_name_cn = '阿司匹林' THEN 1 ELSE 0 END) AS aspirin,
                    MAX(CASE WHEN drug_name_cn = '二甲双胍' THEN 1 ELSE 0 END) AS metformin
                FROM ukb_semantic.unified_medications
                GROUP BY patient_id
            ),
            hosp AS (
                SELECT patient_id, 1 AS hospitalized
                FROM ukb_semantic.unified_hospitalizations
                GROUP BY patient_id
            )
            SELECT
                p.patient_id,
                p.age_at_recruitment::float AS age,
                CASE WHEN p.sex_label = '男' THEN 1 ELSE 0 END AS male,
                COALESCE(v.systolic_bp::float, 0) AS sbp,
                COALESCE(v.diastolic_bp::float, 0) AS dbp,
                COALESCE(df.hypertension, 0) AS hypertension,
                COALESCE(df.hyperchol, 0) AS hyperchol,
                COALESCE(df.diabetes, 0) AS diabetes,
                COALESCE(df.ami, 0) AS ami,
                COALESCE(mf.atorvastatin, 0) AS atorvastatin,
                COALESCE(mf.aspirin, 0) AS aspirin,
                COALESCE(mf.metformin, 0) AS metformin,
                COALESCE(h.hospitalized, 0) AS hospitalized
            FROM ukb_semantic.patient_master_index AS p
            LEFT JOIN ukb_semantic.unified_vitals AS v ON v.patient_id = p.patient_id
            LEFT JOIN disease_flags AS df ON df.patient_id = p.patient_id
            LEFT JOIN med_flags AS mf ON mf.patient_id = p.patient_id
            LEFT JOIN hosp AS h ON h.patient_id = p.patient_id;
            """
        )
    finally:
        await release_db_connection(connection)

    by_patient: dict[int, set[str]] = {}
    for row in disease_rows:
        by_patient.setdefault(row["patient_id"], set()).add(row["disease_name_cn"])

    disease_counts: dict[str, int] = {}
    pair_counts: dict[tuple[str, str], int] = {}
    for diseases in by_patient.values():
        for disease in diseases:
            disease_counts[disease] = disease_counts.get(disease, 0) + 1
        for a, b in itertools.combinations(sorted(diseases), 2):
            pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1

    pairs = []
    for (a, b), count in sorted(pair_counts.items(), key=lambda item: item[1], reverse=True)[:8]:
        support = count / total_patients if total_patients else 0
        confidence = count / disease_counts[a] if disease_counts.get(a) else 0
        pairs.append({"disease_a": a, "disease_b": b, "count": count, "support": support, "confidence": confidence})

    model_result: dict[str, Any] = {"available": False, "message": "样本不足，未训练模型。"}
    visualization_html = ""
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import roc_auc_score, roc_curve
        from sklearn.model_selection import train_test_split

        feature_names = ["age", "male", "sbp", "dbp", "hypertension", "hyperchol", "diabetes", "ami", "atorvastatin", "aspirin", "metformin"]
        records = [dict(row) for row in prediction_rows]
        x = np.array([[float(row[name] or 0) for name in feature_names] for row in records])
        y = np.array([int(row["hospitalized"] or 0) for row in records])
        if len(set(y.tolist())) > 1 and len(y) >= 50:
            x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.3, random_state=42, stratify=y)
            model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight="balanced")
            model.fit(x_train, y_train)
            scores = model.predict_proba(x_test)[:, 1]
            auc = float(roc_auc_score(y_test, scores))
            fpr, tpr, _ = roc_curve(y_test, scores)
            importance = sorted(
                [{"feature": name, "importance": float(value)} for name, value in zip(feature_names, model.feature_importances_)],
                key=lambda item: item["importance"],
                reverse=True,
            )
            model_result = {
                "available": True,
                "target": "是否有住院记录",
                "auc": auc,
                "feature_importance": importance,
                "roc": [{"fpr": float(a), "tpr": float(b)} for a, b in zip(fpr, tpr)],
            }
            roc_points = " ".join(f"{30 + point['fpr'] * 240:.1f},{260 - point['tpr'] * 200:.1f}" for point in model_result["roc"])
            bars = "".join(
                f"<div style='margin:6px 0'><span style='display:inline-block;width:120px'>{item['feature']}</span>"
                f"<span style='display:inline-block;height:10px;background:#2563eb;width:{max(8, item['importance'] * 360):.0f}px'></span>"
                f" {item['importance']:.3f}</div>"
                for item in importance[:8]
            )
            visualization_html = (
                "<div style='font-family:Arial,sans-serif'>"
                f"<h3>住院预测模型 ROC (AUC={auc:.2f})</h3>"
                "<svg viewBox='0 0 320 280' style='width:100%;max-width:520px;background:#fff;border:1px solid #e5e7eb'>"
                "<line x1='30' y1='260' x2='290' y2='260' stroke='#888'/>"
                "<line x1='30' y1='260' x2='30' y2='40' stroke='#888'/>"
                "<line x1='30' y1='260' x2='270' y2='60' stroke='#ddd' stroke-dasharray='4 4'/>"
                f"<polyline points='{roc_points}' fill='none' stroke='#111827' stroke-width='3'/>"
                "</svg>"
                "<h3>特征重要性</h3>"
                f"{bars}</div>"
            )
    except Exception as exc:
        model_result = {"available": False, "message": f"模型训练失败：{exc}"}

    pair_text = "；".join(
        f"{item['disease_a']} + {item['disease_b']}：{item['count']}人，支持度 {item['support']:.1%}，置信度 {item['confidence']:.1%}"
        for item in pairs[:3]
    )
    if model_result.get("available"):
        top_features = "、".join(item["feature"] for item in model_result["feature_importance"][:3])
        model_text = f"住院预测模型 AUC={model_result['auc']:.2f}；Top 3 特征为：{top_features}。"
    else:
        model_text = model_result.get("message", "模型暂不可用。")

    return {
        "status": "success",
        "comorbidity_pairs": pairs,
        "hospitalization_model": model_result,
        "visualization_html": visualization_html,
        "suggested_reply": (
            "主任，我做了一个探索性挖掘原型。\n"
            f"多病共存方面，最突出的组合包括：{pair_text}。\n"
            f"预测住院方面，{model_text}\n"
            "注意：这是探索性结果，适合生成选题和假设；正式投稿前需要预注册主要结局、外部验证或交叉验证，并补充临床合理性解释。"
        ),
    }


async def dispatch_query(intent: str, entities: ExtractedEntities, message: str, session_id: str | None = None) -> dict[str, Any]:
    if intent == "database_identity":
        return {"kind": "database_identity", "result": await describe_database_identity()}
    if intent in {"capability_review", "research_suggestion"}:
        return {"kind": "research_capabilities", "result": await get_research_capabilities()}
    if intent == "data_overview":
        return {"kind": "sample_distribution", "result": await get_sample_distribution()}
    if intent == "demographic_query":
        return {"kind": "demographic_distribution", "result": await get_demographic_distribution(entities, message)}
    if intent == "disease_count" and entities.first_disease_text():
        return {"kind": "disease_count", "result": await _get_disease_count(entities.first_disease_text())}
    if intent == "disease_intersection":
        return {"kind": "disease_intersection", "result": await get_disease_intersection(entities, session_id=session_id)}
    if intent == "drug_count" and entities.first_drug_text():
        return {"kind": "drug_count", "result": await get_drug_count_for_entities(entities)}
    if intent == "drug_event_rate":
        return {"kind": "drug_event_rate", "result": await compare_drug_event_rate(entities, message)}
    if intent == "variable_query":
        return {"kind": "variable_distribution", "result": await get_variable_distribution(entities)}
    if intent == "term_explanation":
        return {"kind": "term_explanation", "result": await explain_terms(entities, message)}
    if intent == "drug_baseline_comparison":
        return {"kind": "baseline_comparison", "result": await compare_drug_baseline(entities, message)}
    if intent == "disease_drug_overlap":
        return {"kind": "disease_drug_overlap", "result": await disease_drug_overlap(entities, session_id=session_id)}
    if intent == "causal_safety_review":
        return {"kind": "causal_safety_review", "result": await causal_safety_review(entities, message)}
    if intent == "exploratory_mining":
        return {"kind": "exploratory_mining", "result": await exploratory_mining()}
    return {
        "kind": "clarify",
        "result": {
            "status": "needs_clarification",
            "suggested_reply": "主任，我需要再确认一下：您是想看数据概况、查某个疾病/药物人数，还是要建立队列研究？",
        },
    }












