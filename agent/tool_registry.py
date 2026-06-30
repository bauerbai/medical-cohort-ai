from __future__ import annotations

from typing import Any

from agent.llm_planner import LLMToolPlan
from agent.query_tools import dispatch_query, summarize_antihypertensive_mechanisms
from agent.semantic_parser import parse_semantic_frame


async def execute_plan(plan: LLMToolPlan, session_id: str, previous_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if plan.intent == "drug_mechanism_summary" and previous_metadata:
        previous_overlap = previous_metadata.get("disease_drug_overlap") or previous_metadata
        return {"kind": "drug_mechanism_summary", "result": await summarize_antihypertensive_mechanisms(previous_overlap, session_id=session_id)}

    frame = parse_semantic_frame(plan.rewritten_query)
    return await dispatch_query(plan.intent, frame.entities, plan.rewritten_query, session_id=session_id)
