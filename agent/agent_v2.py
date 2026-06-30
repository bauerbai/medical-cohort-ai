from __future__ import annotations

from typing import Any

from agent.llm_planner import LLMToolPlan, plan_with_llm, plan_with_rules
from agent.response_composer import compose_tool_reply
from agent.tool_registry import execute_plan
from agent.workflow import run_rwe_agent


SESSION_MEMORY_V2: dict[str, dict[str, Any]] = {}


def _metadata_for_kind(kind: str, result: dict[str, Any]) -> dict[str, Any]:
    return {kind: result, "llm_agent_v2": True}


async def run_llm_agent_v2(message: str, session_id: str = "default") -> dict[str, Any]:
    state = SESSION_MEMORY_V2.setdefault(session_id, {"history": [], "metadata": {}})
    plan = await plan_with_llm(message)
    planner_source = "llm_router"
    if plan is None:
        plan = plan_with_rules(message)
        planner_source = "rule_fallback"

    if plan.intent == "clarify" and planner_source == "rule_fallback":
        # Preserve the mature rule agent for ambiguous flows until the LLM router is configured.
        fallback = await run_rwe_agent(message, session_id)
        fallback["planner_source"] = planner_source
        fallback["llm_plan"] = plan.model_dump()
        return fallback

    tool_result = await execute_plan(plan, session_id=session_id, previous_metadata=state.get("metadata"))
    result = tool_result.get("result", {})
    kind = tool_result.get("kind", plan.intent)
    metadata = _metadata_for_kind(kind, result)
    state["metadata"] = metadata
    state["history"].append({"role": "user", "content": message})
    state["history"].append({"role": "assistant", "content": result.get("suggested_reply", "")})
    if len(state["history"]) > 20:
        del state["history"][:-20]

    return {
        "status": result.get("status", "success"),
        "reply": compose_tool_reply(result),
        "metadata": metadata,
        "result": result,
        "options": result.get("options", []),
        "sql": result.get("sql"),
        "report_url": result.get("report_url") or result.get("download_url"),
        "download_url": result.get("download_url"),
        "planner_source": planner_source,
        "llm_plan": plan.model_dump(),
        "safety_notes": plan.safety_notes,
    }
