from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agent.entity_extractor import ExtractedEntities, extract_entities
from agent.intent_router import classify_intent


PRONOUN_TERMS = {"这些人", "这群人", "这组人", "他们", "上述人群", "这些患者", "该人群"}
DRUG_PRONOUN_TERMS = {"这些药", "这些药物", "上述药物", "这类药", "这类药物"}
DOWNLOAD_TERMS = {"下载", "导出", "保存", "csv", "CSV"}
COUNTING_TERMS = {"患者级", "去重", "记录数", "人次", "药物级", "口径"}


@dataclass(frozen=True)
class SemanticFrame:
    raw_message: str
    intent: str
    confidence: float
    reason: str
    entities: ExtractedEntities
    uses_population_context: bool = False
    uses_drug_context: bool = False
    wants_download: bool = False
    asks_counting_unit: bool = False
    operations: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        data = asdict(self)
        data["entities"] = {
            "diseases": [asdict(item) for item in self.entities.diseases],
            "drugs": [asdict(item) for item in self.entities.drugs],
            "demographics": self.entities.demographics,
            "exposures": [asdict(item) for item in self.entities.exposures],
        }
        return data


def _contains_any(message: str, terms: set[str]) -> bool:
    lowered = message.lower()
    return any(term.lower() in lowered for term in terms)


def parse_semantic_frame(message: str) -> SemanticFrame:
    decision = classify_intent(message)
    entities = extract_entities(message)
    operations: list[str] = []
    if _contains_any(message, {"多少", "人数", "比例", "占比", "统计"}):
        operations.append("count")
    if _contains_any(message, {"类型", "机制", "分类", "中文名", "转化"}):
        operations.append("classify")
    if _contains_any(message, DOWNLOAD_TERMS):
        operations.append("download")
    if _contains_any(message, {"为什么", "为啥", "口径", "加起来"}):
        operations.append("explain")

    return SemanticFrame(
        raw_message=message,
        intent=decision.intent,
        confidence=decision.confidence,
        reason=decision.reason,
        entities=entities,
        uses_population_context=_contains_any(message, PRONOUN_TERMS),
        uses_drug_context=_contains_any(message, DRUG_PRONOUN_TERMS),
        wants_download=_contains_any(message, DOWNLOAD_TERMS),
        asks_counting_unit=_contains_any(message, COUNTING_TERMS),
        operations=operations,
    )
