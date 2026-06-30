from typing import Any


RESEARCH_TYPES = [
    {
        "value": "队列研究",
        "label": "队列研究",
        "description": "适合已有基线特征、随访结局和事件时间的数据；可以回答暴露与疾病风险是否相关。",
        "why": "数据库有 patient_master_index、unified_vitals、unified_diagnoses 和事件日期，能构建暴露-结局随访队列。",
    },
    {
        "value": "孟德尔随机化",
        "label": "孟德尔随机化",
        "description": "适合使用遗传工具变量推断因果方向；当前版本先提供流程化原型和简化 OR。",
        "why": "当前语义层没有遗传工具变量表，因此只能先做方法框架和暴露-结局关联近似，后续可接入 GWAS/PRS 表。",
    },
    {
        "value": "疾病负担描述",
        "label": "疾病负担描述",
        "description": "统计 ICD-10 疾病频率、Top 疾病和人群分布。",
        "why": "unified_diagnoses 已有 ICD-10 编码、描述和事件日期，适合做疾病谱探索。",
    },
    {
        "value": "用药与结局探索",
        "label": "用药与结局探索",
        "description": "探索药物处方与后续疾病结局之间的关系。",
        "why": "unified_medications 有处方日期和药物分类，可与诊断表按 patient_id 和时间关系联结。",
    },
]

COHORT_STUDY_TYPES = [
    {
        "value": "暴露-结局队列",
        "label": "暴露-结局队列",
        "description": "选择一个基线暴露和一个 ICD-10 结局，比较暴露水平与发病风险。",
        "why": "当前库有基线血压、人口学变量和诊断日期，是最稳的第一条分析路径。",
    },
    {
        "value": "疾病首发队列",
        "label": "疾病首发队列",
        "description": "围绕某个 ICD-10 疾病，提取首发时间、事件状态和基线特征。",
        "why": "unified_first_occurrences 和 unified_diagnoses 都能支持疾病事件提取。",
    },
    {
        "value": "用药暴露队列",
        "label": "用药暴露队列",
        "description": "以某类药物为暴露，观察后续疾病结局。",
        "why": "有 unified_medications，但还需要更细的药物选择器，建议作为下一步扩展。",
    },
]

ANALYSIS_METHODS = [
    {
        "value": "基线特征",
        "label": "基线特征表",
        "description": "计算年龄、社会经济指数、暴露变量的均值和标准差。",
        "why": "这是所有队列研究的第一步，用来判断样本构成和变量质量。",
    },
    {
        "value": "结局发生率",
        "label": "结局发生率",
        "description": "计算目标 ICD-10 结局事件数、非事件数和发生比例。",
        "why": "能快速判断结局是否足够常见，决定后续模型是否稳定。",
    },
    {
        "value": "暴露分组OR",
        "label": "暴露高低分组 OR",
        "description": "按暴露中位数分为高低组，计算结局 odds ratio 和 95% CI。",
        "why": "当前样本量较小，先用稳健、可解释的 2x2 表近似风险比较。",
    },
    {
        "value": "分层描述",
        "label": "按性别分层描述",
        "description": "按 sex 分层计算样本量和结局率。",
        "why": "能检查结果是否可能受性别构成影响，也方便报告解释。",
    },
    {
        "value": "全做",
        "label": "全做",
        "description": "一次执行基线特征、结局发生率、暴露分组 OR 和分层描述。",
        "why": "适合初次探索，先快速拿到一份完整可读的初步报告。",
    },
]


def format_research_catalog(metadata: dict[str, Any]) -> str:
    table_names = "、".join(metadata.get("tables", {}).keys())
    lines = [
        f"我已经读取 ukb_semantic，发现 {metadata.get('table_count')} 张表：{table_names}。",
        "基于当前数据结构，我建议优先考虑这些研究：",
    ]
    for index, item in enumerate(RESEARCH_TYPES, start=1):
        lines.append(f"{index}. {item['label']}：{item['description']}为什么可做：{item['why']}")
    lines.append("你可以直接说：队列研究、孟德尔随机化，或者描述你的研究问题。")
    return "\n".join(lines)


def format_cohort_catalog() -> str:
    lines = ["队列研究可以先做这几类，我会说明为什么："]
    for index, item in enumerate(COHORT_STUDY_TYPES, start=1):
        lines.append(f"{index}. {item['label']}：{item['description']}为什么推荐：{item['why']}")
    lines.append("建议先选“暴露-结局队列”，因为当前数据库字段最完整。")
    return "\n".join(lines)


def format_method_recommendations(params: dict[str, Any]) -> str:
    exposure = params.get("exposure", "暴露")
    outcome = params.get("icd_code", params.get("outcome", "结局"))
    lines = [
        f"我已经为 {exposure} -> {outcome} 提取了队列 SQL。下一步建议先做数据预检，然后选择分析方法。",
        "可选分析方法：",
    ]
    for index, item in enumerate(ANALYSIS_METHODS, start=1):
        lines.append(f"{index}. {item['label']}：{item['description']}为什么：{item['why']}")
    lines.append("你可以说“全做”，也可以只选“基线特征”或“暴露分组OR”。")
    return "\n".join(lines)


def get_research_options() -> list[dict[str, Any]]:
    return RESEARCH_TYPES


def get_cohort_options() -> list[dict[str, Any]]:
    return COHORT_STUDY_TYPES


def get_method_options() -> list[dict[str, Any]]:
    return ANALYSIS_METHODS


def normalize_method_selection(message: str) -> list[str] | None:
    compact = message.strip().replace(" ", "")
    if compact in {"全做", "全部", "都做", "全部分析", "全都做"}:
        return ["基线特征", "结局发生率", "暴露分组OR", "分层描述"]

    selected: list[str] = []
    aliases = {
        "基线特征": "基线特征",
        "基线特征表": "基线特征",
        "发生率": "结局发生率",
        "结局发生率": "结局发生率",
        "OR": "暴露分组OR",
        "暴露分组OR": "暴露分组OR",
        "分组OR": "暴露分组OR",
        "分层": "分层描述",
        "分层描述": "分层描述",
    }
    upper_message = compact.upper()
    for key, value in aliases.items():
        if key.upper() in upper_message and value not in selected:
            selected.append(value)
    return selected or None
