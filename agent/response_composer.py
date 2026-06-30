from __future__ import annotations

from typing import Any


def compose_tool_reply(result: dict[str, Any]) -> str:
    reply = result.get("suggested_reply")
    if isinstance(reply, str) and reply.strip():
        return reply
    status = result.get("status", "unknown")
    return f"主任，工具已返回结果，状态为 {status}。"


def compose_clarification_reply(message: str) -> str:
    if any(term in message for term in {"都不是", "不是呢", "不对", "不是这个"}):
        return (
            "明白，主任，刚才我把问题框得太窄了。您可以继续直接用自然语言问数据翻译、药物分类、"
            "统计口径、变量解释、导出明细或研究设计，我会优先承接上一轮上下文。"
        )
    return (
        "主任，我需要先确认您的意图：您是想看数据库样本概况、查某个疾病/药物的人数，"
        "还是要建立一个队列研究并进入统计分析？"
    )
