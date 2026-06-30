from __future__ import annotations

import unittest

from agent.intent_router import classify_intent


class AgentIntentRouterTests(unittest.TestCase):
    def assert_intent(self, message: str, expected: str) -> None:
        decision = classify_intent(message)
        self.assertEqual(decision.intent, expected, f"{message!r} -> {decision.intent}: {decision.reason}")

    def test_data_overview_questions(self) -> None:
        self.assert_intent("这个数据库中的样本分布能描述一下吗", "data_overview")
        self.assert_intent("这个库大概是什么样的数据", "data_overview")
        self.assert_intent("帮我看看库里的男女比例和排名前三的慢性病", "data_overview")

    def test_database_identity_questions(self) -> None:
        self.assert_intent("这是什么数据库", "database_identity")
        self.assert_intent("这个数据库是什么", "database_identity")

    def test_capability_questions(self) -> None:
        self.assert_intent("你能用这些数据做什么呀", "capability_review")
        self.assert_intent("这些数据适合做什么研究", "research_suggestion")

    def test_demographic_questions(self) -> None:
        self.assert_intent("帮我看看库里的男女都有多少人", "demographic_query")
        self.assert_intent("平均年龄是多少", "demographic_query")
        self.assert_intent("60岁以上的所有男性有多少", "demographic_query")
        self.assert_intent("大于60岁的女性有多少", "demographic_query")

    def test_disease_count_questions(self) -> None:
        self.assert_intent("有多少得高血压的", "disease_count")
        self.assert_intent("糖尿病患者多少", "disease_count")
        self.assert_intent("G30 有多少人", "disease_count")

    def test_disease_intersection_questions(self) -> None:
        self.assert_intent("同时得糖尿病和高血压的人有多少？男女比例是多少？能下载一下这些数据吗", "disease_intersection")
        self.assert_intent("合并糖尿病和高血压的患者有多少", "disease_intersection")

    def test_drug_count_questions(self) -> None:
        self.assert_intent("二甲双胍有多少人用过", "drug_count")
        self.assert_intent("阿司匹林使用者多少", "drug_count")
        self.assert_intent("降压药有多少人用过", "drug_count")

    def test_drug_event_rate_questions(self) -> None:
        self.assert_intent("使用不同降压药的患者事件发生率有不同吗", "drug_event_rate")
        self.assert_intent("不同类型降压药患者心梗发生率有不同吗", "drug_event_rate")

    def test_level_1_baseline_comparison(self) -> None:
        self.assert_intent(
            "帮我看看库里吃阿托伐他汀的人，和不吃的人，基线特征有什么区别？顺便告诉我这两组人里，高血压和糖尿病的比例差多少。",
            "drug_baseline_comparison",
        )
        self.assert_intent(
            "帮我看看库里吃降压药的人，和不吃的人，基线特征有什么区别？顺便告诉我这两组人里，高血压和糖尿病的比例差多少",
            "drug_baseline_comparison",
        )

    def test_drug_class_overlap(self) -> None:
        self.assert_intent("这些人都吃降压药了吗", "disease_drug_overlap")
        self.assert_intent("高血压患者吃 CCB 的比例是多少", "disease_drug_overlap")
        self.assert_intent("糖尿病人群中，吃降压药的有哪些种类的药物，各多少人，能下载吗", "disease_drug_overlap")
        self.assert_intent("吃高血压药同时患糖尿病的有多少，男女比例", "disease_drug_overlap")
        self.assert_intent("那这些人用的哪些降压药？都什么类型的降压药？按照类型分类的话，统计学数据是多少", "disease_drug_overlap")

    def test_result_explanation_questions(self) -> None:
        self.assert_intent("38个人使用过降压药，但各种药物加一起以后是大于38的呀，为啥呢", "result_explanation")

    def test_term_explanation_questions(self) -> None:
        self.assert_intent("sbp和g30是什么啊", "term_explanation")
        self.assert_intent("SBP 是什么意思", "term_explanation")

    def test_drug_mechanism_summary_questions(self) -> None:
        self.assert_intent("这些药都是哪种类型的降压药呀，能按照降压药类型统计一下吗", "drug_mechanism_summary")
        self.assert_intent("能不能把这些药转化成中文名", "drug_mechanism_summary")

    def test_level_2_causal_safety_review(self) -> None:
        self.assert_intent(
            "我想做个回顾性队列研究，看看高血压患者吃二甲双胍，能不能降低未来发生心梗的风险。你直接帮我跑个 Cox 回归看看 HR 值吧。",
            "causal_safety_review",
        )

    def test_level_3_exploratory_mining(self) -> None:
        self.assert_intent(
            "科里想发篇 5 分以上的文章，你帮我从库里挖一挖，看看哪几种慢性病经常一起得（多病共存）？顺便建个模型预测一下，哪些因素最能预测患者未来会住院？",
            "exploratory_mining",
        )
        self.assert_intent("慢病共病谱分析", "exploratory_mining")

    def test_analysis_process_followup(self) -> None:
        self.assert_intent("能把分析过程呈现出来吗", "analysis_process")
        self.assert_intent("这个结果是怎么算出来的", "analysis_process")

    def test_cohort_design_questions(self) -> None:
        self.assert_intent("帮我建立一个队列研究", "cohort_design")
        self.assert_intent("做 SBP 和高血压 的队列研究", "cohort_design")

    def test_run_analysis(self) -> None:
        self.assert_intent("开始分析", "run_analysis")


if __name__ == "__main__":
    unittest.main()




