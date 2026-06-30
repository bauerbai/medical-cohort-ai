from __future__ import annotations

import unittest

from agent.context_manager import (
    ConversationContext,
    resolve_population_context,
    update_context_from_query,
)
from agent.entity_extractor import extract_entities
from agent.semantic_parser import parse_semantic_frame


class SemanticContextTests(unittest.TestCase):
    def test_population_pronoun_resolves_previous_disease_intersection(self) -> None:
        context = ConversationContext()
        update_context_from_query(
            context,
            "disease_intersection",
            {
                "count": 81,
                "diseases": [
                    {"label": "原发性高血压", "text": "高血压", "code": "I10"},
                    {"label": "2型糖尿病", "text": "糖尿病", "code": "E11"},
                ],
            },
        )

        frame = parse_semantic_frame("那这些人用的哪些降压药？都什么类型的降压药？")
        population = resolve_population_context(frame, context)

        self.assertIsNotNone(population)
        self.assertEqual(population.kind, "disease_intersection")
        self.assertEqual(population.size, 81)
        self.assertEqual(len(population.diseases), 2)

    def test_heart_failure_entity(self) -> None:
        entities = extract_entities("统计队列中确诊过心力衰竭的患者总数")

        self.assertEqual([(item.canonical, item.code) for item in entities.diseases], [("心力衰竭", "I50")])
    def test_hypertension_drug_phrase_is_not_hypertension_disease(self) -> None:
        entities = extract_entities("吃高血压药同时患糖尿病的有多少，男女比例")

        self.assertEqual([item.canonical for item in entities.diseases], ["2型糖尿病"])
        self.assertEqual([(item.canonical, item.kind) for item in entities.drugs], [("降压药", "drug_class")])
    def test_drug_mechanism_followup_uses_drug_context_language(self) -> None:
        frame = parse_semantic_frame("这些药都是哪种类型的降压药呀，能按照降压药类型统计一下吗")

        self.assertEqual(frame.intent, "drug_mechanism_summary")
        self.assertTrue(frame.uses_drug_context)
        self.assertIn("classify", frame.operations)

    def test_counting_unit_followup_is_explanation(self) -> None:
        frame = parse_semantic_frame("38个人使用过降压药，但各种药物加一起以后是大于38的呀，为啥呢")

        self.assertEqual(frame.intent, "result_explanation")
        self.assertIn("explain", frame.operations)


if __name__ == "__main__":
    unittest.main()





