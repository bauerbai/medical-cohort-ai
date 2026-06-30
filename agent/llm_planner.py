from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agent.llm_client import LLMRouterClient, LLMRouterUnavailable
from agent.semantic_parser import parse_semantic_frame


SUPPORTED_INTENTS = {
    "database_identity",
    "capability_review",
    "data_overview",
    "demographic_query",
    "disease_count",
    "disease_intersection",
    "drug_count",
    "drug_event_rate",
    "drug_baseline_comparison",
    "disease_drug_overlap",
    "drug_mechanism_summary",
    "term_explanation",
    "variable_query",
    "causal_safety_review",
    "exploratory_mining",
    "clarify",
}


class LLMToolPlan(BaseModel):
    intent: str = Field(description="One supported backend tool intent.")
    rewritten_query: str = Field(description="Chinese query rewritten with explicit clinical entities.")
    reasoning: str = Field(description="Brief methodologic reason for this routing decision.")
    needs_confirmation: bool = False
    safety_notes: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = """
你是医学真实世界研究 SQL Agent 的规划器，不直接写 SQL，不直接编造统计结果。
你的任务是把 PI 的自然语言问题转为后端安全工具可执行的 JSON 计划。

硬规则：
1. 只输出 JSON object，不输出 Markdown。
2. intent 必须从允许列表中选择。
3. rewritten_query 必须保留用户真实问题，但把省略实体补全成人话临床实体。
4. 遇到疾病人数、患病率、交集人群，一律要求患者级去重；不要暗示 COUNT(*)。
5. 遇到用药组 vs 未用药组疗效比较，必须提示适应症混杂和不朽时间偏倚。
6. 遇到“高血压药、降压药、CCB、ACEI、ARB、利尿剂、β阻滞剂”，应识别为药物类别，不要误识别成高血压疾病，除非用户明确说“高血压患者”。
7. 不确定时选择 clarify，但要说明缺什么信息。

允许 intent：
{intents}

输出 JSON 示例：
{
  "intent": "disease_drug_overlap",
  "rewritten_query": "糖尿病患者中，使用降压药的人有多少？男女比例是多少？需要下载数据。",
  "reasoning": "用户问疾病人群中的药物暴露和性别分布，应调用疾病-药物交叉统计工具。",
  "needs_confirmation": false,
  "safety_notes": ["患者人数按 patient_id 去重", "处方记录不等同于真实服药依从性"]
}
""".strip()


async def plan_with_llm(message: str) -> LLMToolPlan | None:
    client = LLMRouterClient()
    if not client.enabled:
        return None

    prompt = SYSTEM_PROMPT.replace("__SUPPORTED_INTENTS__", ", ".join(sorted(SUPPORTED_INTENTS)))
    try:
        content = await client.chat_json(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ]
        )
        data = json.loads(content)
        plan = LLMToolPlan.model_validate(data)
    except (LLMRouterUnavailable, json.JSONDecodeError, ValidationError):
        return None

    if plan.intent not in SUPPORTED_INTENTS:
        return None
    return plan


def plan_with_rules(message: str) -> LLMToolPlan:
    frame = parse_semantic_frame(message)
    intent = frame.intent if frame.intent in SUPPORTED_INTENTS else "clarify"
    return LLMToolPlan(
        intent=intent,
        rewritten_query=message,
        reasoning=f"规则解析回退：{frame.reason}",
        needs_confirmation=intent == "clarify",
        safety_notes=[],
    )

