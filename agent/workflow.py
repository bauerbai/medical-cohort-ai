from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from agent.academic_workflow import build_academic_workflow_plan, format_workflow_for_pi
from agent.context_manager import (
    get_conversation_context,
    reset_conversation_context,
    resolve_population_context,
    update_context_from_query,
)
from agent.intent_router import classify_intent
from agent.query_tools import (
    dispatch_query,
    disease_drug_overlap,
    explain_analysis_process,
    get_semantic_cohort_candidates,
    summarize_antihypertensive_mechanisms,
)
from agent.response_composer import compose_clarification_reply, compose_tool_reply
from agent.semantic_parser import parse_semantic_frame
from agent.system_prompt import RWE_AGENT_SYSTEM_PROMPT
from cohort_builder import build_cohort_sql, normalize_exposure, normalize_outcome
from metadata_scanner import scan_schema
from research_catalog import get_research_options
from stats_engine import preview_cohort, run_analysis


WorkflowStage = Literal[
    "intent",
    "design_review",
    "cohort_build",
    "data_preview",
    "method_selection",
    "analysis_execution",
    "final_response",
]


class AgentState(TypedDict, total=False):
    session_id: str
    message: str
    history: list[dict[str, str]]
    stage: WorkflowStage
    intent: str
    research_question: str
    metadata: dict[str, Any]
    design: dict[str, Any]
    bias_review: list[dict[str, str]]
    params: dict[str, Any]
    sql: str
    preview: dict[str, Any]
    selected_methods: list[str]
    analysis_result: dict[str, Any]
    reply: str
    options: list[dict[str, Any]]
    warnings: list[str]
    intent_reason: str
    intent_confidence: float
    semantic_frame: dict[str, Any]
    conversation_context: dict[str, Any]
    visualization_html: str
    report_url: str
    previous_metadata: dict[str, Any]


SESSION_MEMORY: dict[str, AgentState] = {}


def get_agent_session(session_id: str) -> AgentState:
    return SESSION_MEMORY.setdefault(session_id, {"session_id": session_id, "history": [], "params": {}, "warnings": []})


def _append_history(state: AgentState, role: str, content: str) -> None:
    history = state.setdefault("history", [])
    history.append({"role": role, "content": content})
    if len(history) > 20:
        del history[:-20]


def _extract_methods(message: str) -> list[str] | None:
    compact = message.replace(" ", "").upper()
    if any(term in message for term in {"全做", "全部", "都做", "完整分析"}):
        return ["基线特征", "结局发生率", "暴露分组OR", "分层描述"]
    selected: list[str] = []
    mapping = {
        "基线": "基线特征",
        "TABLE1": "基线特征",
        "发生率": "结局发生率",
        "OR": "暴露分组OR",
        "分组": "暴露分组OR",
        "分层": "分层描述",
    }
    for key, value in mapping.items():
        if key.upper() in compact and value not in selected:
            selected.append(value)
    return selected or None


def _explain_previous_result(previous_metadata: dict[str, Any]) -> str:
    overlap = previous_metadata.get("disease_drug_overlap")
    if overlap:
        disease = overlap.get("disease", "该疾病")
        drug = overlap.get("drug", "该类药物")
        users = overlap.get("drug_users_in_disease", 0)
        per_drug_sum = overlap.get("per_drug_patient_count_sum")
        top_drugs = overlap.get("top_matching_drugs", [])
        examples = "、".join(
            f"{item.get('label')} {item.get('patient_count')}人"
            for item in top_drugs[:5]
        )
        sum_text = f"这些具体药物人数相加是 {per_drug_sum} 人次口径，" if per_drug_sum is not None else ""
        return (
            f"主任，是这样的：上一条里的 {users} 人，是“{disease} 患者中使用过{drug}的人数”，"
            "这里按 patient_id 去重，一个人只算一次。\n\n"
            f"后面列出的药物种类是“按具体药品分别统计”：例如 {examples}。"
            f"{sum_text}它可以大于 {users}，因为同一个患者可能同时或先后用过多种降压药，"
            "比如既用过氨氯地平，又用过雷米普利；在总人数里仍是 1 个人，但在两个具体药物条目里会各出现一次。\n\n"
            "所以这两个数的统计口径不同：总人数看患者去重，药物清单看药品暴露明细。做 Table 1 或疗效分析时，"
            "应使用患者级去重分组；做用药模式分析时，才看各药物或各机制类别的明细。"
        )
    return (
        "主任，这个追问是在问上一轮结果的统计口径。当前我没有找到可解释的上一轮结构化结果，"
        "您可以让我重新跑一次具体查询，例如“糖尿病人群中吃降压药的有哪些种类，各多少人”。"
    )


async def intent_node(state: AgentState) -> AgentState:
    message = state["message"].strip()
    frame = parse_semantic_frame(message)
    decision = classify_intent(message)
    state["previous_metadata"] = state.get("metadata", {})
    state["reply"] = ""
    state["options"] = []
    state["metadata"] = {}
    state["design"] = {}
    state["bias_review"] = []
    state["preview"] = {}
    state["analysis_result"] = {}
    state["visualization_html"] = ""
    state["report_url"] = ""
    state["semantic_frame"] = frame.model_dump()
    state["intent_reason"] = frame.reason
    state["intent_confidence"] = frame.confidence
    _append_history(state, "user", message)

    previous_intent = state.get("intent")

    if decision.reset_context:
        state["sql"] = ""
        state["params"] = {}
        state["selected_methods"] = []
        reset_conversation_context(state["session_id"])

    context = get_conversation_context(state["session_id"])
    state["conversation_context"] = context.model_dump()

    if frame.intent == "run_analysis":
        state["intent"] = "run_analysis"
    elif previous_intent == "cohort_study" and frame.entities.diseases:
        state["intent"] = "cohort_study"
    elif frame.intent in {
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
        "causal_safety_review",
        "exploratory_mining",
        "analysis_process",
        "research_suggestion",
        "capability_review",
        "clarify",
    }:
        state["intent"] = frame.intent
    elif _extract_methods(message):
        state["intent"] = "method_selection"
        state["selected_methods"] = _extract_methods(message) or []
    elif frame.intent == "cohort_design":
        state["intent"] = "cohort_study"
    elif frame.intent == "report_workflow":
        state["intent"] = "academic_workflow"
    else:
        state["intent"] = frame.intent

    state["research_question"] = message
    state["stage"] = "intent"
    return state


async def design_review_node(state: AgentState) -> AgentState:
    metadata = await scan_schema()
    state["metadata"] = metadata
    intent = state.get("intent")
    frame = parse_semantic_frame(state["message"])
    context = get_conversation_context(state["session_id"])

    if intent == "greeting":
        state["sql"] = ""
        state["reply"] = "你好，帅哥。我在。你可以问：能做哪些研究？也可以直接说：做 SBP 与 G30 的队列研究。"
        state["options"] = get_research_options()
        state["stage"] = "final_response"
        return state

    if intent == "academic_workflow":
        state["sql"] = ""
        state["reply"] = format_workflow_for_pi()
        state["metadata"] = {"academic_workflow": build_academic_workflow_plan()}
        state["stage"] = "final_response"
        return state

    if intent in {
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
        "causal_safety_review",
        "exploratory_mining",
        "analysis_process",
        "research_suggestion",
        "capability_review",
    }:
        decision = classify_intent(state["message"])
        if intent == "result_explanation":
            state["sql"] = ""
            state["params"] = {}
            state["reply"] = _explain_previous_result(state.get("previous_metadata", {}))
            state["metadata"] = {
                "previous_result_explanation": {"status": "success"},
                "schema": metadata,
                "semantic_frame": frame.model_dump(),
                "context": context.model_dump(),
            }
            state["stage"] = "final_response"
            return state
        if intent == "analysis_process":
            query = {
                "kind": "analysis_process",
                "result": explain_analysis_process(context.latest_result_kind, context.latest_result),
            }
            state["sql"] = ""
            state["params"] = {}
            state["reply"] = compose_tool_reply(query["result"])
            state["conversation_context"] = context.model_dump()
            state["metadata"] = {
                query["kind"]: query["result"],
                "schema": metadata,
                "semantic_frame": frame.model_dump(),
                "context": context.model_dump(),
            }
            state["stage"] = "final_response"
            return state
        if intent == "drug_mechanism_summary":
            previous_overlap = {}
            if context.latest_result_kind == "disease_drug_overlap":
                previous_overlap = context.latest_result
            if not previous_overlap:
                previous_overlap = state.get("previous_metadata", {}).get("disease_drug_overlap", {})
            query = {
                "kind": "drug_mechanism_summary",
                "result": await summarize_antihypertensive_mechanisms(
                    previous_overlap,
                    session_id=state["session_id"],
                ),
            }
            state["sql"] = ""
            state["params"] = {}
            state["reply"] = compose_tool_reply(query["result"])
            update_context_from_query(context, query["kind"], query["result"])
            state["conversation_context"] = context.model_dump()
            state["metadata"] = {
                query["kind"]: query["result"],
                "schema": metadata,
                "semantic_frame": frame.model_dump(),
                "context": context.model_dump(),
            }
            state["report_url"] = query["result"].get("report_url") or query["result"].get("download_url", "")
            state["stage"] = "final_response"
            return state
        if intent == "disease_drug_overlap":
            previous_metadata = state.get("previous_metadata", {})
            previous_disease = (
                previous_metadata
                .get("disease_count", {})
                .get("disease")
            )
            previous_intersection = previous_metadata.get("disease_intersection", {})
            population_context = resolve_population_context(frame, context)
            cohort_context = previous_intersection
            if population_context and population_context.kind == "disease_intersection":
                cohort_context = {"diseases": population_context.diseases}
            if population_context and not previous_disease and population_context.kind == "single_disease":
                previous_disease = population_context.label
            query = {
                "kind": "disease_drug_overlap",
                "result": await disease_drug_overlap(
                    decision.entities,
                    fallback_disease=previous_disease,
                    cohort_context=cohort_context,
                    session_id=state["session_id"],
                ),
            }
        else:
            query = await dispatch_query(intent, decision.entities, state["message"], session_id=state["session_id"])
        state["sql"] = ""
        state["params"] = {}
        state["reply"] = compose_tool_reply(query["result"])
        update_context_from_query(context, query["kind"], query["result"])
        state["conversation_context"] = context.model_dump()
        state["metadata"] = {
            query["kind"]: query["result"],
            "schema": metadata,
            "semantic_frame": frame.model_dump(),
            "context": context.model_dump(),
        }
        state["visualization_html"] = query["result"].get("visualization_html", "")
        state["report_url"] = query["result"].get("report_url") or query["result"].get("download_url", "")
        state["stage"] = "final_response"
        return state

    if intent == "clarify":
        state["sql"] = ""
        state["params"] = {}
        if any(term in state["message"] for term in {"都不是", "不是呢", "不对", "不是这个"}):
            state["reply"] = compose_clarification_reply(state["message"])
            state["options"] = []
            state["stage"] = "final_response"
            return state
        state["reply"] = compose_clarification_reply(state["message"])
        state["options"] = [
            {"value": "描述一下数据库中的样本分布", "label": "样本分布"},
            {"value": "有多少得高血压的", "label": "高血压人数"},
            {"value": "帮我建立一个队列研究", "label": "建立队列研究"},
        ]
        state["stage"] = "final_response"
        return state

    if intent == "analysis_plan":
        state["sql"] = ""
        state["reply"] = (
            "主任，分析方法要先看研究目的：如果只是描述样本，用基线特征表和疾病/用药频数；"
            "如果比较暴露和结局，用回顾性队列、Logistic/Poisson 回归或 Cox；"
            "如果担心混杂，用多因素调整、PSM 或 IPTW；如果做预测，用机器学习和 ROC/DCA。"
            "您可以先告诉我暴露、结局和目标问题，我再给出具体方案。"
        )
        state["stage"] = "final_response"
        return state

    if intent == "methodology_qa":
        state["sql"] = ""
        state["reply"] = (
            "主任，这属于方法学问题。简单说：描述性问题先看分布和频数；关联问题看 OR/RR/HR；"
            "时间到事件问题用 KM/Cox；治疗或药物比较要特别注意混杂、时间零点和新使用者设计。"
            "如果您给我一个具体研究问题，我可以把它拆成 PICO、偏倚风险和推荐统计模型。"
        )
        state["stage"] = "final_response"
        return state

    if intent in {"cohort_study", "survival_analysis", "causal_inference"} and not normalize_outcome(state["message"]) and not state.get("params", {}).get("outcome"):
        candidates = await get_semantic_cohort_candidates(limit=10)
        state["metadata"] = {"cohort_candidates": candidates, "schema": metadata}
        state["reply"] = candidates["suggested_reply"]
        state["options"] = [
            {
                "value": item["label"],
                "label": item["label"],
                "patient_count": item["patient_count"],
            }
            for item in candidates.get("candidates", [])
            if item.get("has_cn_label")
        ]
        state["stage"] = "final_response"
        return state

    design = {
        "estimand": "exposure-outcome association unless PI specifies a causal contrast",
        "time_zero": "baseline assessment date derived from recruitment age and birth year/month",
        "population": "participants in patient_master_index with linked semantic tables",
        "recommended_design": "retrospective cohort" if intent in {"cohort_study", "survival_analysis"} else "target trial emulation / causal design review",
        "minimum_data": ["patient_id", "baseline covariates", "exposure", "outcome", "event date or follow-up time"],
    }
    bias_review = [
        {
            "bias": "Immortal time bias",
            "recommendation": "Align time zero before exposure/outcome assessment; avoid classifying future exposure as baseline exposure.",
        },
        {
            "bias": "Confounding",
            "recommendation": "Adjust for age, sex, socioeconomic status, and clinically plausible baseline covariates; use PSM/IPTW for treatment comparisons.",
        },
        {
            "bias": "Prevalent outcome bias",
            "recommendation": "Exclude subjects with outcome before or at baseline when estimating incident risk.",
        },
    ]
    if intent == "survival_analysis":
        bias_review.append({"bias": "Non-proportional hazards", "recommendation": "Check Schoenfeld residuals and consider time-varying effects if PH is violated."})
    if intent == "causal_inference":
        bias_review.append({"bias": "Positivity", "recommendation": "Inspect propensity score overlap and post-match SMD before effect estimation."})

    state["design"] = design
    state["bias_review"] = bias_review
    state["stage"] = "design_review"
    return state


async def cohort_builder_node(state: AgentState) -> AgentState:
    params = state.setdefault("params", {})
    message = state["message"]

    exposure = normalize_exposure(message) or params.get("exposure") or "SBP"
    outcome = normalize_outcome(message) or params.get("outcome") or "G30"
    params.update(
        {
            "analysis_type": "队列研究" if state.get("intent") != "causal_inference" else "因果推断",
            "cohort_type": "暴露-结局队列",
            "exposure": exposure,
            "outcome": outcome,
            "methods": params.get("methods", ["基线特征", "结局发生率", "暴露分组OR", "分层描述"]),
        }
    )
    cohort = build_cohort_sql(params)
    state["sql"] = cohort["sql"]
    params.update(cohort["params"])
    state["warnings"] = [*state.get("warnings", []), *cohort.get("warnings", [])]
    state["stage"] = "cohort_build"
    return state


async def data_preview_node(state: AgentState) -> AgentState:
    if not state.get("sql"):
        return state
    state["preview"] = await preview_cohort(state["sql"])
    state["stage"] = "data_preview"
    return state


async def method_selection_node(state: AgentState) -> AgentState:
    params = state.setdefault("params", {})
    selected = state.get("selected_methods") or params.get("methods")
    if not selected:
        selected = ["基线特征", "结局发生率", "暴露分组OR", "分层描述"]
    params["methods"] = selected
    state["stage"] = "method_selection"
    return state


async def analysis_execution_node(state: AgentState) -> AgentState:
    if state.get("intent") != "run_analysis" and "开始分析" not in state.get("message", ""):
        return state
    if not state.get("sql"):
        state["reply"] = "我还没有可执行的队列 SQL。请先说明研究问题、暴露和结局。"
        return state
    state["analysis_result"] = await run_analysis(state["session_id"], state["params"], state["sql"])
    state["stage"] = "analysis_execution"
    return state


def final_response_node(state: AgentState) -> AgentState:
    if state.get("reply"):
        _append_history(state, "assistant", state["reply"])
        return state

    if state.get("analysis_result"):
        result = state["analysis_result"]
        state["reply"] = (
            f"分析已完成。样本量 {result.get('count')}；已生成统计结果、图表和报告。"
            f"下载链接：{result.get('report_url')}"
        )
        return state

    if state.get("preview"):
        preview = state["preview"]
        outcome = preview.get("outcome", {})
        methods = ", ".join(state.get("params", {}).get("methods", []))
        bias_lines = "\n".join(f"- {item['bias']}：{item['recommendation']}" for item in state.get("bias_review", []))
        state["reply"] = (
            "我已经完成研究设计审查和数据预检。\n"
            f"预检结果：提取 {preview.get('row_count')} 行，结局事件 {outcome.get('positive', 0)} 例，"
            f"发生率 {(outcome.get('rate') or 0):.2%}。\n"
            f"建议分析方法：{methods}。\n"
            f"主要偏倚检查：\n{bias_lines}\n"
            "如果你同意，可以回复“开始分析”；也可以说“只做基线和发生率”来缩小分析范围。"
        )
    else:
        design = state.get("design", {})
        bias_lines = "\n".join(f"- {item['bias']}：{item['recommendation']}" for item in state.get("bias_review", []))
        state["reply"] = (
            "我会先把问题转成可执行的 RWE 设计。\n"
            f"推荐设计：{design.get('recommended_design', '待定')}。\n"
            f"主要偏倚检查：\n{bias_lines}\n"
            "请告诉我暴露、结局和随访窗口，或直接说例如：做 SBP 与 G30 的队列研究。"
        )
    _append_history(state, "assistant", state["reply"])
    return state


def route_after_design(state: AgentState) -> str:
    if state.get("stage") == "final_response":
        return "final_response"
    return "cohort_builder"


def route_after_preview(state: AgentState) -> str:
    if state.get("intent") == "run_analysis" or "开始分析" in state.get("message", ""):
        return "analysis_execution"
    return "method_selection"


def build_rwe_graph():
    graph = StateGraph(AgentState)
    graph.add_node("intent", intent_node)
    graph.add_node("design_review", design_review_node)
    graph.add_node("cohort_builder", cohort_builder_node)
    graph.add_node("data_preview", data_preview_node)
    graph.add_node("method_selection", method_selection_node)
    graph.add_node("analysis_execution", analysis_execution_node)
    graph.add_node("final_response", final_response_node)

    graph.set_entry_point("intent")
    graph.add_edge("intent", "design_review")
    graph.add_conditional_edges("design_review", route_after_design, {"cohort_builder": "cohort_builder", "final_response": "final_response"})
    graph.add_edge("cohort_builder", "data_preview")
    graph.add_conditional_edges("data_preview", route_after_preview, {"method_selection": "method_selection", "analysis_execution": "analysis_execution"})
    graph.add_edge("method_selection", "final_response")
    graph.add_edge("analysis_execution", "final_response")
    graph.add_edge("final_response", END)
    return graph.compile()


RWE_GRAPH = build_rwe_graph()


async def run_rwe_agent(message: str, session_id: str = "default") -> dict[str, Any]:
    session_state = get_agent_session(session_id)
    state: AgentState = {**session_state, "session_id": session_id, "message": message}
    result = await RWE_GRAPH.ainvoke(state)
    SESSION_MEMORY[session_id] = result
    return {
        "reply": result.get("reply", ""),
        "status": "success",
        "step": result.get("stage"),
        "intent": result.get("intent"),
        "design": result.get("design"),
        "bias_review": result.get("bias_review"),
        "metadata": result.get("metadata"),
        "params": result.get("params"),
        "sql": result.get("sql"),
        "preview": result.get("preview"),
        "analysis_result": result.get("analysis_result"),
        "visualization_html": result.get("visualization_html"),
        "report_url": result.get("report_url") or result.get("analysis_result", {}).get("report_url"),
        "options": result.get("options"),
        "warnings": result.get("warnings", []),
        "semantic_frame": result.get("semantic_frame"),
        "context": result.get("conversation_context"),
        "system_prompt_version": hash(RWE_AGENT_SYSTEM_PROMPT),
    }








