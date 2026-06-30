from typing import Any

from cohort_builder import (
    build_cohort_sql,
    get_common_exposures,
    get_common_outcomes,
    normalize_exposure,
    normalize_outcome,
)
from metadata_scanner import scan_schema
from research_catalog import (
    ANALYSIS_METHODS,
    format_cohort_catalog,
    format_method_recommendations,
    get_cohort_options,
    get_method_options,
    get_research_options,
    normalize_method_selection,
)
from stats_engine import preview_cohort, run_analysis


SESSION_STORE: dict[str, dict[str, Any]] = {}

MR_OPTIONS = [
    {"value": "方案A", "label": "方案A：两样本 MR，暴露到疾病结局"},
    {"value": "方案B", "label": "方案B：多变量 MR，纳入协变量校正"},
    {"value": "方案C", "label": "方案C：反向 MR，检验方向性"},
    {"value": "方案D", "label": "方案D：敏感性分析与异质性检验"},
]


def get_session(session_id: str) -> dict[str, Any]:
    return SESSION_STORE.setdefault(session_id, {"step": "select_analysis", "params": {}})


def reset_session(session_id: str) -> dict[str, Any]:
    SESSION_STORE[session_id] = {"step": "select_analysis", "params": {}}
    return SESSION_STORE[session_id]


def _contains_any(message: str, keywords: set[str]) -> bool:
    return any(keyword in message for keyword in keywords)


def _response(
    reply: str,
    session: dict[str, Any],
    options: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "reply": reply,
        "status": "success",
        "step": session["step"],
        "params": session["params"],
    }
    if options is not None:
        payload["options"] = options
    if extra:
        payload.update(extra)
    return payload


async def run_session_analysis(session_id: str) -> dict[str, Any]:
    session = get_session(session_id)
    sql = session.get("sql")
    if session.get("step") not in {"confirm", "select_methods", "analysis_complete"} or not sql:
        return _response("还没有可执行的队列 SQL。请先完成研究类型、暴露和结局选择。", session)

    if not session["params"].get("methods"):
        session["params"]["methods"] = ["基线特征", "结局发生率", "暴露分组OR", "分层描述"]

    session["step"] = "running_analysis"
    analysis_result = await run_analysis(session_id, session["params"], sql)
    session["step"] = "analysis_complete"
    session["analysis_result"] = analysis_result
    return _response(
        analysis_result["reply"],
        session,
        extra={
            "count": analysis_result["count"],
            "stats": analysis_result["stats"],
            "visualization_html": analysis_result["visualization_html"],
            "report_url": analysis_result["report_url"],
        },
    )


async def _start_cohort_catalog(session: dict[str, Any]) -> dict[str, Any]:
    session["step"] = "select_cohort_type"
    session["params"] = {"analysis_type": "队列研究"}
    session.pop("sql", None)
    session.pop("analysis_result", None)
    return _response(format_cohort_catalog(), session, options=get_cohort_options())


async def _start_exposure_selection(session: dict[str, Any]) -> dict[str, Any]:
    metadata = await scan_schema()
    session["step"] = "select_exposure"
    session["params"].setdefault("analysis_type", "队列研究")
    session["params"].setdefault("cohort_type", "暴露-结局队列")
    return _response(
        "好，我们先做暴露-结局队列。请选一个暴露变量；我会根据当前表字段判断哪些变量可用。",
        session,
        options=get_common_exposures(metadata),
        extra={"metadata_summary": {"table_count": metadata["table_count"]}},
    )


async def _preview_and_recommend(session: dict[str, Any]) -> dict[str, Any]:
    cohort_result = build_cohort_sql(session["params"])
    session["sql"] = cohort_result["sql"]
    session["params"].update(cohort_result["params"])
    preview = await preview_cohort(cohort_result["sql"])
    session["preview"] = preview
    session["step"] = "select_methods"

    outcome = preview["outcome"]
    exposure_n = preview["baseline"].get("exposure_value", {}).get("n", 0)
    reply = (
        f"我先做了数据预检：共提取 {preview['row_count']} 行，"
        f"结局事件 {outcome.get('positive', 0)} 例，发生率 {outcome.get('rate') or 0:.2%}，"
        f"暴露变量有效值 {exposure_n} 个。\n"
        f"{format_method_recommendations(session['params'])}"
    )
    return _response(
        reply,
        session,
        options=get_method_options(),
        extra={
            "sql": cohort_result["sql"],
            "warnings": cohort_result["warnings"],
            "cohort_params": cohort_result["params"],
            "preview": preview,
        },
    )


async def handle_chat_message(message: str, session_id: str = "default") -> dict[str, Any]:
    normalized_message = message.strip()
    compact_message = normalized_message.upper().replace(" ", "")
    session = get_session(session_id)

    if normalized_message in {"重置", "reset", "重新开始"}:
        session = reset_session(session_id)
        return _response("已重置。你可以先问“能做哪些分析”，或直接选择一种研究类型。", session, options=get_research_options())

    if normalized_message in {"开始分析", "[开始分析]"}:
        return await run_session_analysis(session_id)

    method_selection = normalize_method_selection(normalized_message)
    if session["step"] in {"select_methods", "confirm"} and method_selection:
        session["params"]["methods"] = method_selection
        session["step"] = "confirm"
        return _response(
            f"已选择分析方法：{', '.join(method_selection)}。点击 [开始分析] 后我会执行 SQL、计算统计、生成图表和 Word 报告。",
            session,
            extra={"sql": session.get("sql"), "can_analyze": True, "selected_methods": method_selection},
        )

    if _contains_any(normalized_message, {"队列研究", "生成队列", "队列分析", "协助生成队列"}):
        return await _start_cohort_catalog(session)

    if normalized_message in {"暴露-结局队列", "疾病首发队列", "用药暴露队列"}:
        session["params"]["cohort_type"] = normalized_message
        if normalized_message != "暴露-结局队列":
            session["step"] = "select_cohort_type"
            return _response(
                "这个方向可以做，但当前版本最完整的是“暴露-结局队列”。建议先走这条路径，后续再扩展药物选择器和首发疾病专用流程。",
                session,
                options=get_cohort_options(),
            )
        return await _start_exposure_selection(session)

    if "孟德尔" in normalized_message or compact_message in {"MR", "MENDELIANRANDOMIZATION"}:
        session["step"] = "select_mr_type"
        session["params"] = {"analysis_type": "孟德尔随机化"}
        session.pop("sql", None)
        session.pop("analysis_result", None)
        return _response(
            "可以做 MR 流程原型。不过当前库还没有遗传工具变量表，所以我会先用暴露-结局队列做简化 OR，等接入 GWAS/PRS 后再升级为正式 MR。请选择方案。",
            session,
            options=MR_OPTIONS,
        )

    if session["step"] == "select_mr_type":
        option_values = {option["value"] for option in MR_OPTIONS}
        if compact_message in option_values:
            metadata = await scan_schema()
            session["step"] = "select_exposure"
            session["params"]["mr_type"] = compact_message
            return _response("请选择暴露变量。", session, options=get_common_exposures(metadata))
        return _response("我还不认识这个方案，请选择方案A、方案B、方案C或方案D。", session, MR_OPTIONS)

    if session["step"] == "select_cohort_type":
        return _response("请选择一个队列研究类型。", session, options=get_cohort_options())

    if session["step"] == "select_exposure":
        exposure = normalize_exposure(normalized_message)
        if exposure:
            session["step"] = "select_outcome"
            session["params"]["exposure"] = exposure
            return _response(
                f"已选择暴露：{exposure}。请选择结局疾病 ICD-10 编码。",
                session,
                options=get_common_outcomes(),
            )
        metadata = await scan_schema()
        return _response("我还不认识这个暴露变量，请从列表中选择。", session, get_common_exposures(metadata))

    if session["step"] == "select_outcome":
        outcome = normalize_outcome(normalized_message)
        if outcome:
            session["params"]["outcome"] = outcome
            return await _preview_and_recommend(session)
        return _response("我还不认识这个 ICD-10 结局，请从列表中选择。", session, get_common_outcomes())

    if session["step"] == "analysis_complete":
        result = session.get("analysis_result", {})
        return _response(
            "分析已经完成，可继续下载报告，或发送“重置”开始新的分析流程。",
            session,
            extra={
                "count": result.get("count"),
                "stats": result.get("stats"),
                "visualization_html": result.get("visualization_html"),
                "report_url": result.get("report_url"),
            },
        )

    return _response(
        "我可以像研究助手一样陪你多轮设计：先判断能做哪些研究，再解释原因，然后提取数据、推荐分析方法。你想先看哪些分析可做，还是直接做队列研究？",
        session,
        options=get_research_options(),
    )
