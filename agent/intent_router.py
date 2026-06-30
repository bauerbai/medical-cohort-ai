from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from agent.entity_extractor import ExtractedEntities, extract_entities


AgentIntent = Literal[
    "greeting",
    "database_identity",
    "data_overview",
    "demographic_query",
    "disease_count",
    "disease_intersection",
    "drug_count",
    "drug_event_rate",
    "drug_baseline_comparison",
    "disease_drug_overlap",
    "drug_mechanism_summary",
    "result_explanation",
    "term_explanation",
    "variable_query",
    "cohort_design",
    "analysis_plan",
    "causal_safety_review",
    "exploratory_mining",
    "analysis_process",
    "run_analysis",
    "methodology_qa",
    "report_workflow",
    "capability_review",
    "research_suggestion",
    "clarify",
]


@dataclass(frozen=True)
class IntentDecision:
    intent: AgentIntent
    confidence: float
    reason: str
    entities: ExtractedEntities
    reset_context: bool = False


GREETINGS = {"hi", "hello", "你好", "您好", "嗨", "在吗"}
DATABASE_IDENTITY_TERMS = {
    "这是什么数据库",
    "这个数据库是什么",
    "什么数据库",
    "数据库介绍",
    "数据来源",
    "这个库是什么",
    "这是个什么库",
}
CAPABILITY_TERMS = {
    "能做",
    "能用这些数据做什么",
    "能用这个数据做什么",
    "能做什么",
    "可以做什么",
    "适合做什么",
    "哪些分析",
    "哪些研究",
    "研究类型",
    "能分析",
    "可以分析",
    "能干什么",
}
RESEARCH_SUGGESTION_TERMS = {"适合做什么研究", "推荐研究", "研究方向", "科研选题", "可以研究什么", "建议做什么"}
REPORT_WORKFLOW_TERMS = {"科研流程", "论文", "文献", "写作", "投稿", "审稿", "academic-research-skills", "academic research", "报告"}
COHORT_TERMS = {"建队列", "建立队列", "队列研究", "构建队列", "生成sql", "生成 sql", "研究队列"}
RUN_TERMS = {"开始分析", "执行分析", "运行分析"}
ANALYSIS_PLAN_TERMS = {"分析方法", "怎么分析", "建议分析", "统计方法", "分析方案"}
ANALYSIS_PROCESS_TERMS = {
    "分析过程",
    "过程呈现",
    "怎么做出来",
    "怎么分析出来",
    "怎么算出来",
    "计算过程",
    "统计过程",
    "方法过程",
    "呈现出来",
}
METHODOLOGY_TERMS = {"什么是", "解释", "为什么", "or", "rr", "hr", "cox", "psm", "iptw", "孟德尔随机化", "mr"}
TERM_EXPLANATION_TERMS = {"是什么", "什么意思", "啥意思", "代表什么", "解释一下", "是什么啊"}
RESULT_EXPLANATION_TERMS = {"为什么", "为啥", "怎么回事", "口径", "加起来", "相加", "大于", "超过", "不等于"}
DRUG_MECHANISM_TERMS = {"类型", "种类", "机制", "类别", "哪种类型", "按照降压药类型", "分类", "中文名", "转化成中文"}
OVERVIEW_TERMS = {
    "样本分布",
    "数据分布",
    "数据库分布",
    "数据概况",
    "样本概况",
    "总体情况",
    "整体情况",
    "描述一下",
    "预检",
    "人群特征",
    "基线特征",
    "什么样的数据",
    "有什么数据",
    "库里有什么",
}
COUNT_TERMS = {"多少", "几个", "几人", "人数", "有多少", "count", "比例", "占比"}
DISEASE_STATE_TERMS = {"得", "患", "患者", "病人", "诊断", "疾病"}
INTERSECTION_TERMS = {"同时", "合并", "共患", "都有", "都得", "交集", "共病"}
DRUG_STATE_TERMS = {"用", "吃", "服用", "使用", "处方", "药物", "用药"}
VARIABLE_TERMS = {"字段", "变量", "有没有", "是否有", "分布如何", "范围"}
BASELINE_COMPARISON_TERMS = {"基线特征", "table 1", "table1", "区别", "差异", "比例差", "p值", "p 值", "mean", "sd"}
EVENT_RATE_TERMS = {"事件发生率", "发生率", "结局发生", "事件率", "风险差", "有没有不同", "是否不同"}
CONTEXT_PRONOUN_TERMS = {"这些人", "他们", "这组人", "这群人", "上述人群"}
CAUSAL_SAFETY_TERMS = {"直接帮我跑", "cox", "hr", "未来发生", "降低风险", "风险", "回顾性队列"}
EXPLORATORY_TERMS = {"5 分", "5分", "挖一挖", "多病共存", "共病", "经常一起", "预测", "住院", "模型", "roc", "auc", "特征重要性"}


def _contains_any(message: str, terms: set[str]) -> bool:
    lowered = message.lower()
    return any(term.lower() in lowered for term in terms)


def _asks_count(message: str) -> bool:
    return _contains_any(message, COUNT_TERMS)


def _asks_ranked_summary(message: str) -> bool:
    return _contains_any(message, {"前三", "前十", "排名", "top", "最多", "常见"})



def _has_demographic_filter(message: str) -> bool:
    has_age_threshold = bool(re.search(r"\d{1,3}\s*岁\s*(以上|及以上|以下|及以下|以内)|(?:大于|超过|小于|低于)\s*\d{1,3}\s*岁", message))
    has_sex = _contains_any(message, {"男", "男性", "女", "女性", "male", "female"})
    return has_age_threshold or has_sex
def classify_intent(message: str) -> IntentDecision:
    text = message.strip()
    lowered = text.lower()
    entities = extract_entities(text)

    if lowered in GREETINGS:
        return IntentDecision("greeting", 0.99, "问候语", entities, reset_context=True)

    if text in RUN_TERMS:
        return IntentDecision("run_analysis", 0.98, "用户明确要求执行分析", entities)

    if _contains_any(text, DATABASE_IDENTITY_TERMS):
        return IntentDecision("database_identity", 0.96, "数据库身份/数据来源介绍", entities, reset_context=True)

    if _contains_any(text, REPORT_WORKFLOW_TERMS):
        return IntentDecision("report_workflow", 0.95, "科研流程/报告/论文工作流问题", entities, reset_context=True)

    if _contains_any(text, RESEARCH_SUGGESTION_TERMS):
        return IntentDecision("research_suggestion", 0.94, "基于当前数据推荐研究方向", entities, reset_context=True)

    if _contains_any(text, CAPABILITY_TERMS):
        return IntentDecision("capability_review", 0.95, "能力范围问题", entities, reset_context=True)

    if entities.drugs and entities.diseases and _contains_any(text, CAUSAL_SAFETY_TERMS):
        return IntentDecision("causal_safety_review", 0.95, "存在因果/生存分析偏倚风险，需先方法学排雷", entities, reset_context=True)

    if _contains_any(text, COHORT_TERMS):
        return IntentDecision("cohort_design", 0.95, "明确要求建立或构建队列", entities)

    if _contains_any(text, ANALYSIS_PLAN_TERMS):
        return IntentDecision("analysis_plan", 0.9, "分析方案或统计方法推荐", entities)

    if _contains_any(text, ANALYSIS_PROCESS_TERMS):
        return IntentDecision("analysis_process", 0.9, "解释上一轮分析流程和统计口径", entities, reset_context=False)

    if entities.drugs and _contains_any(text, BASELINE_COMPARISON_TERMS):
        return IntentDecision("drug_baseline_comparison", 0.94, "药物暴露组与非暴露组基线特征比较", entities, reset_context=True)

    if entities.drugs and _contains_any(text, EVENT_RATE_TERMS):
        return IntentDecision("drug_event_rate", 0.93, "不同药物暴露组之间的结局事件发生率比较", entities, reset_context=True)

    if _contains_any(text, EXPLORATORY_TERMS):
        return IntentDecision("exploratory_mining", 0.92, "探索性共病挖掘/预测模型任务", entities, reset_context=True)

    if _contains_any(text, RESULT_EXPLANATION_TERMS) and not _has_demographic_filter(text):
        return IntentDecision("result_explanation", 0.88, "解释上一轮统计结果或统计口径", entities, reset_context=False)

    if _contains_any(text, TERM_EXPLANATION_TERMS) and (entities.exposures or entities.diseases):
        return IntentDecision("term_explanation", 0.9, "解释变量、缩写或疾病编码含义", entities, reset_context=True)

    if entities.drugs and _contains_any(text, CONTEXT_PRONOUN_TERMS) and _contains_any(text, DRUG_STATE_TERMS):
        return IntentDecision("disease_drug_overlap", 0.86, "承接上文疾病人群，查询其中用药比例", entities, reset_context=False)

    if entities.drugs and entities.diseases and _contains_any(text, DRUG_STATE_TERMS):
        return IntentDecision("disease_drug_overlap", 0.9, "疾病人群中的用药比例查询", entities, reset_context=True)

    if _contains_any(text, DRUG_MECHANISM_TERMS) and _contains_any(text, {"这些药", "中文名", "类型", "机制", "分类"}):
        return IntentDecision("drug_mechanism_summary", 0.9, "承接上一轮药物明细，按药物机制/中文名汇总", entities, reset_context=False)

    if len(entities.diseases) >= 2 and (
        _contains_any(text, INTERSECTION_TERMS)
        or _asks_count(text)
        or _contains_any(text, {"男女比例", "性别", "下载", "导出"})
    ):
        return IntentDecision("disease_intersection", 0.94, "多个疾病同时满足的人群交集查询", entities, reset_context=True)

    if entities.drugs and (_asks_count(text) or _contains_any(text, DRUG_STATE_TERMS)):
        return IntentDecision("drug_count", 0.92, "药物人数/用药事实查询", entities, reset_context=True)

    if entities.diseases and (_asks_count(text) or _contains_any(text, DISEASE_STATE_TERMS)):
        return IntentDecision("disease_count", 0.92, "疾病人数/患病事实查询", entities, reset_context=True)

    if _contains_any(text, OVERVIEW_TERMS) or (_asks_ranked_summary(text) and _contains_any(text, {"慢性病", "疾病", "诊断", "药物", "用药"})):
        return IntentDecision("data_overview", 0.9, "样本/数据库总体描述", entities, reset_context=True)

    if (entities.demographics or _has_demographic_filter(text)) and (_asks_count(text) or _contains_any(text, {"分布", "比例", "概况"})):
        return IntentDecision("demographic_query", 0.9, "人口学分布查询", entities, reset_context=True)

    if _contains_any(text, VARIABLE_TERMS) or (entities.exposures and not _contains_any(text, TERM_EXPLANATION_TERMS)):
        return IntentDecision("variable_query", 0.78, "变量或字段可用性/分布查询", entities, reset_context=True)

    if _contains_any(text, METHODOLOGY_TERMS):
        return IntentDecision("methodology_qa", 0.75, "研究设计或统计方法解释", entities, reset_context=True)

    return IntentDecision(
        "clarify",
        0.35,
        "无法稳定判断用户想查数据、建队列还是做统计分析",
        entities,
        reset_context=True,
    )







