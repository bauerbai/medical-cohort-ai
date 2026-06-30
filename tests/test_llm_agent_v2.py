from __future__ import annotations

import unittest

from agent.llm_planner import _strip_json_fence, plan_with_rules
from main import app


class LLMAgentV2Tests(unittest.TestCase):
    def test_rule_fallback_plan_keeps_supported_intent(self) -> None:
        plan = plan_with_rules("吃高血压药同时患糖尿病的有多少，男女比例")

        self.assertEqual(plan.intent, "disease_drug_overlap")
        self.assertEqual(plan.rewritten_query, "吃高血压药同时患糖尿病的有多少，男女比例")
        self.assertIn("规则解析回退", plan.reasoning)

    def test_rule_fallback_data_dictionary_plan(self) -> None:
        plan = plan_with_rules("现在数据库中的数据字典是怎么构成的？详细说明一下")

        self.assertEqual(plan.intent, "data_dictionary")
    def test_strip_json_fence(self) -> None:
        content = """```json
{"intent":"data_overview"}
```"""

        self.assertEqual(_strip_json_fence(content), '{"intent":"data_overview"}')
    def test_agent_v2_route_is_registered(self) -> None:
        routes = {getattr(route, "path", "") for route in app.routes}

        self.assertIn("/api/agent-v2", routes)
        self.assertIn("/api/agent", routes)


if __name__ == "__main__":
    unittest.main()




