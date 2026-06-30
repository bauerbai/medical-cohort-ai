from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.semantic_parser import SemanticFrame


@dataclass
class PopulationContext:
    label: str
    kind: str
    size: int | None = None
    diseases: list[dict[str, Any]] = field(default_factory=list)
    source_kind: str = ""

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DrugContext:
    label: str
    kind: str
    users: int | None = None
    drugs: list[dict[str, Any]] = field(default_factory=list)
    mechanisms: list[dict[str, Any]] = field(default_factory=list)
    source_kind: str = ""

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConversationContext:
    active_population: PopulationContext | None = None
    active_drug_set: DrugContext | None = None
    latest_result_kind: str = ""
    latest_result: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "active_population": self.active_population.model_dump() if self.active_population else None,
            "active_drug_set": self.active_drug_set.model_dump() if self.active_drug_set else None,
            "latest_result_kind": self.latest_result_kind,
            "latest_result": deepcopy(self.latest_result),
        }


CONTEXT_MEMORY: dict[str, ConversationContext] = {}


def get_conversation_context(session_id: str) -> ConversationContext:
    return CONTEXT_MEMORY.setdefault(session_id, ConversationContext())


def reset_conversation_context(session_id: str) -> None:
    CONTEXT_MEMORY[session_id] = ConversationContext()


def resolve_population_context(frame: SemanticFrame, context: ConversationContext) -> PopulationContext | None:
    if frame.entities.diseases:
        return None
    if frame.uses_population_context:
        return context.active_population
    return None


def resolve_drug_context(frame: SemanticFrame, context: ConversationContext) -> DrugContext | None:
    if frame.entities.drugs:
        return None
    if frame.uses_drug_context:
        return context.active_drug_set
    return None


def update_context_from_query(context: ConversationContext, kind: str, result: dict[str, Any]) -> None:
    context.latest_result_kind = kind
    context.latest_result = deepcopy(result)

    if kind == "disease_count":
        context.active_population = PopulationContext(
            label=result.get("disease", "疾病人群"),
            kind="single_disease",
            size=result.get("patient_count"),
            diseases=[
                {
                    "label": result.get("disease"),
                    "text": result.get("disease"),
                    "code": result.get("icd10_prefix") or result.get("disease_code"),
                }
            ],
            source_kind=kind,
        )
        return

    if kind == "disease_intersection":
        diseases = result.get("diseases", [])
        label = "合并".join(item.get("label") or item.get("text") or "疾病" for item in diseases)
        context.active_population = PopulationContext(
            label=label or "复合疾病人群",
            kind="disease_intersection",
            size=result.get("count"),
            diseases=deepcopy(diseases),
            source_kind=kind,
        )
        return

    if kind == "disease_drug_overlap":
        context.active_population = PopulationContext(
            label=result.get("disease", "疾病人群"),
            kind="drug_overlap_population",
            size=result.get("disease_patients"),
            diseases=result.get("diseases", []),
            source_kind=kind,
        )
        context.active_drug_set = DrugContext(
            label=result.get("drug", "药物"),
            kind="drug_overlap",
            users=result.get("drug_users_in_disease"),
            drugs=deepcopy(result.get("translated_drugs") or result.get("top_matching_drugs") or []),
            mechanisms=deepcopy(result.get("mechanisms") or []),
            source_kind=kind,
        )
        return

    if kind == "drug_mechanism_summary":
        context.active_drug_set = DrugContext(
            label=result.get("drug", "药物"),
            kind="drug_mechanism_summary",
            users=result.get("drug_users_in_disease"),
            drugs=deepcopy(result.get("translated_drugs") or []),
            mechanisms=deepcopy(result.get("mechanisms") or []),
            source_kind=kind,
        )
