from __future__ import annotations

import json
import urllib.request


CASES = [
    ("这是什么数据库", "database_identity", False),
    ("你能用这些数据做什么呀", "capability_review", False),
    ("这些数据适合做什么研究", "research_suggestion", False),
    ("这个数据库中的样本分布能描述一下吗", "data_overview", False),
    ("这个库大概是什么样的数据", "data_overview", False),
    ("帮我看看库里的男女都有多少人", "demographic_query", False),
    ("平均年龄是多少", "demographic_query", False),
    ("有多少得高血压的", "disease_count", False),
    ("糖尿病患者多少", "disease_count", False),
    ("同时得糖尿病和高血压的人有多少？男女比例是多少？能下载一下这些数据吗", "disease_intersection", False),
    ("二甲双胍有多少人用过", "drug_count", False),
    ("阿司匹林使用者多少", "drug_count", False),
    ("帮我看看库里吃阿托伐他汀的人，和不吃的人，基线特征有什么区别？顺便告诉我这两组人里，高血压和糖尿病的比例差多少。", "drug_baseline_comparison", False),
    ("帮我看看库里吃降压药的人，和不吃的人，基线特征有什么区别？顺便告诉我这两组人里，高血压和糖尿病的比例差多少", "drug_baseline_comparison", False),
    ("高血压患者吃 CCB 的比例是多少", "disease_drug_overlap", False),
    ("糖尿病人群中，吃降压药的有哪些种类的药物，各多少人，能下载吗", "disease_drug_overlap", False),
    ("这些药都是哪种类型的降压药呀，能按照降压药类型统计一下吗", "drug_mechanism_summary", False),
    ("我想做个回顾性队列研究，看看高血压患者吃二甲双胍，能不能降低未来发生心梗的风险。你直接帮我跑个 Cox 回归看看 HR 值吧。", "causal_safety_review", False),
    ("科里想发篇 5 分以上的文章，你帮我从库里挖一挖，看看哪几种慢性病经常一起得（多病共存）？顺便建个模型预测一下，哪些因素最能预测患者未来会住院？", "exploratory_mining", False),
    ("帮我建立一个队列研究", "cohort_study", False),
    ("做 SBP 和高血压 的队列研究", "cohort_study", True),
]


def post_agent(message: str, session_id: str) -> dict:
    payload = json.dumps({"message": message, "session_id": session_id}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:8001/api/agent",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    failures: list[str] = []
    for index, (message, expected_intent, expected_sql) in enumerate(CASES):
        data = post_agent(message, f"route-regression-script-{index}")
        intent = data.get("intent")
        has_sql = bool(data.get("sql"))
        ok = intent == expected_intent and has_sql == expected_sql
        marker = "OK" if ok else "FAIL"
        print(f"[{marker}] {message} -> intent={intent}, has_sql={has_sql}")
        if not ok:
            failures.append(
                f"{message!r}: expected intent={expected_intent}, has_sql={expected_sql}; got intent={intent}, has_sql={has_sql}"
            )
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
