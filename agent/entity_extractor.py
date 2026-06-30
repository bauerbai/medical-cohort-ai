from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


DISEASE_CONCEPTS: dict[str, dict[str, Any]] = {
    "高血压": {
        "canonical": "原发性高血压",
        "icd10_prefix": "I10",
        "aliases": ["高血压", "原发性高血压", "hypertension", "i10"],
    },
    "高血脂": {
        "canonical": "纯高胆固醇血症",
        "icd10_prefix": "E78",
        "aliases": ["高血脂", "高脂血症", "胆固醇", "hyperlipidemia", "cholesterol", "e78"],
    },
    "糖尿病": {
        "canonical": "2型糖尿病",
        "icd10_prefix": "E11",
        "aliases": ["糖尿病", "2型糖尿病", "二型糖尿病", "diabetes", "e11"],
    },
    "阿尔茨海默": {
        "canonical": "阿尔茨海默病",
        "icd10_prefix": "G30",
        "aliases": ["阿尔茨海默", "老年痴呆", "alzheimer", "dementia", "g30"],
    },
    "冠心病": {
        "canonical": "慢性缺血性心脏病/冠心病",
        "icd10_prefix": "I25",
        "aliases": ["冠心病", "缺血性心脏病", "coronary", "ischemic heart", "i25"],
    },
    "心梗": {
        "canonical": "急性心肌梗死",
        "icd10_prefix": "I21",
        "aliases": ["心梗", "心肌梗死", "myocardial infarction", "i21"],
    },
    "脑卒中": {
        "canonical": "脑卒中",
        "icd10_prefix": "I64",
        "aliases": ["脑卒中", "中风", "stroke", "i64"],
    },
    "胃食管反流": {
        "canonical": "胃食管反流病",
        "icd10_prefix": "K21",
        "aliases": ["胃食管反流", "反流", "gastro-oesophageal reflux", "gastroesophageal reflux", "k21"],
    },
    "哮喘": {
        "canonical": "哮喘",
        "icd10_prefix": "J45",
        "aliases": ["哮喘", "asthma", "j45"],
    },
}


DRUG_CONCEPTS: dict[str, dict[str, Any]] = {
    "二甲双胍": {"canonical": "二甲双胍", "atc": "A10BA02", "aliases": ["二甲双胍", "metformin", "a10ba02"]},
    "阿司匹林": {"canonical": "阿司匹林", "atc": "B01AC06", "aliases": ["阿司匹林", "aspirin", "b01ac06"]},
    "阿托伐他汀": {"canonical": "阿托伐他汀", "atc": "C10AA05", "aliases": ["阿托伐他汀", "atorvastatin", "c10aa05"]},
    "比索洛尔": {"canonical": "比索洛尔", "atc": "C07AB07", "aliases": ["比索洛尔", "bisoprolol", "c07ab07"]},
    "依那普利": {"canonical": "依那普利", "atc": "C09AA02", "aliases": ["依那普利", "enalapril", "c09aa02"]},
}

DRUG_CLASS_CONCEPTS: dict[str, dict[str, Any]] = {
    "降压药": {
        "canonical": "降压药",
        "aliases": ["降压药", "抗高血压药", "降血压药", "高血压药", "高血压的药", "antihypertensive"],
        "text_terms": [
            "amlodipine",
            "bendroflumethiazide",
            "bisoprolol",
            "enalapril",
            "ramipril",
            "lisinopril",
            "losartan",
            "candesartan",
            "atenolol",
            "indapamide",
            "doxazosin",
            "propranolol",
            "nifedipine",
            "furosemide",
        ],
        "code_prefixes": ["02.02", "02.04", "02.05", "02.06"],
        "mechanisms": ["CCB", "ACEI", "ARB", "β受体阻滞剂", "利尿剂", "α受体阻滞剂"],
    },
    "CCB": {
        "canonical": "钙通道阻滞剂（CCB）",
        "aliases": ["ccb", "钙通道阻滞剂", "钙离子拮抗剂", "地平"],
        "text_terms": ["amlodipine", "nifedipine", "felodipine", "diltiazem", "verapamil"],
        "code_prefixes": ["02.06.02"],
        "mechanisms": ["CCB"],
    },
    "ACEI": {
        "canonical": "ACEI",
        "aliases": ["acei", "ace inhibitor", "普利", "血管紧张素转换酶抑制剂"],
        "text_terms": ["enalapril", "ramipril", "lisinopril", "perindopril", "captopril"],
        "code_prefixes": ["02.05.05"],
        "mechanisms": ["ACEI"],
    },
    "ARB": {
        "canonical": "ARB",
        "aliases": ["arb", "沙坦", "血管紧张素受体拮抗剂"],
        "text_terms": ["losartan", "candesartan", "valsartan", "irbesartan", "olmesartan"],
        "code_prefixes": ["02.05.05"],
        "mechanisms": ["ARB"],
    },
    "β受体阻滞剂": {
        "canonical": "β受体阻滞剂",
        "aliases": ["β受体阻滞剂", "β阻滞剂", "beta blocker", "倍他阻滞剂", "洛尔"],
        "text_terms": ["bisoprolol", "atenolol", "propranolol", "metoprolol", "carvedilol"],
        "code_prefixes": ["02.04"],
        "mechanisms": ["β受体阻滞剂"],
    },
    "利尿剂": {
        "canonical": "利尿剂",
        "aliases": ["利尿剂", "diuretic", "噻嗪", "袢利尿"],
        "text_terms": ["bendroflumethiazide", "indapamide", "furosemide", "spironolactone"],
        "code_prefixes": ["02.02"],
        "mechanisms": ["利尿剂"],
    },
}


EXPOSURE_CONCEPTS: dict[str, dict[str, str]] = {
    "SBP": {"canonical": "SBP", "column": "systolic_bp", "label": "收缩压"},
    "DBP": {"canonical": "DBP", "column": "diastolic_bp", "label": "舒张压"},
    "LDL-C": {"canonical": "LDL-C", "column": "", "label": "低密度脂蛋白胆固醇"},
}


@dataclass(frozen=True)
class ExtractedEntity:
    kind: str
    text: str
    canonical: str
    code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedEntities:
    diseases: list[ExtractedEntity] = field(default_factory=list)
    drugs: list[ExtractedEntity] = field(default_factory=list)
    demographics: list[str] = field(default_factory=list)
    exposures: list[ExtractedEntity] = field(default_factory=list)

    def first_disease_text(self) -> str | None:
        return self.diseases[0].text if self.diseases else None

    def first_drug_text(self) -> str | None:
        return self.drugs[0].text if self.drugs else None


def _contains_alias(message: str, aliases: list[str]) -> str | None:
    lowered = message.lower()
    for alias in sorted(aliases, key=len, reverse=True):
        if alias.lower() in lowered:
            return alias
    return None


def _extract_icd10(message: str) -> str | None:
    match = re.search(r"\b([A-Z]\d{2}(?:\.?\d|[A-Z0-9])?)\b", message.upper())
    return match.group(1).replace(".", "") if match else None


def _is_alias_inside_drug_phrase(message: str, alias: str) -> bool:
    """Avoid treating disease words as diseases when they modify a drug class."""
    protected_phrases = {
        "高血压药",
        "高血压的药",
        "高血压用药",
        "抗高血压药",
        "降高血压药",
    }
    return any(alias in phrase and phrase in message for phrase in protected_phrases)

def extract_entities(message: str) -> ExtractedEntities:
    diseases: list[ExtractedEntity] = []
    drugs: list[ExtractedEntity] = []
    exposures: list[ExtractedEntity] = []
    demographics: list[str] = []

    seen_disease_codes: set[str] = set()
    for key, concept in DISEASE_CONCEPTS.items():
        alias = _contains_alias(message, concept["aliases"])
        if alias and _is_alias_inside_drug_phrase(message, alias):
            alias = None
        if alias and concept["icd10_prefix"] not in seen_disease_codes:
            diseases.append(
                ExtractedEntity(
                    kind="disease",
                    text=alias,
                    canonical=concept["canonical"],
                    code=concept["icd10_prefix"],
                    metadata={"dictionary_key": key},
                )
            )
            seen_disease_codes.add(concept["icd10_prefix"])

    if not diseases:
        icd10 = _extract_icd10(message)
        if icd10:
            diseases.append(ExtractedEntity(kind="disease", text=icd10, canonical=icd10, code=icd10))

    for key, concept in DRUG_CONCEPTS.items():
        alias = _contains_alias(message, concept["aliases"])
        if alias:
            drugs.append(
                ExtractedEntity(
                    kind="drug",
                    text=alias,
                    canonical=concept["canonical"],
                    code=concept["atc"],
                    metadata={"dictionary_key": key},
                )
            )
            break

    for key, concept in DRUG_CLASS_CONCEPTS.items():
        alias = _contains_alias(message, concept["aliases"])
        if alias:
            drugs.append(
                ExtractedEntity(
                    kind="drug_class",
                    text=alias,
                    canonical=concept["canonical"],
                    code=None,
                    metadata={
                        "dictionary_key": key,
                        "text_terms": concept["text_terms"],
                        "code_prefixes": concept["code_prefixes"],
                        "mechanisms": concept["mechanisms"],
                    },
                )
            )
            break

    lowered = message.lower()
    if any(term in lowered for term in {"男女", "男", "女", "性别", "male", "female", "sex"}):
        demographics.append("sex")
    if any(term in lowered for term in {"年龄", "岁数", "age"}):
        demographics.append("age")

    exposure_aliases = {
        "SBP": ["sbp", "收缩压", "systolic"],
        "DBP": ["dbp", "舒张压", "diastolic"],
        "LDL-C": ["ldl", "ldl-c", "低密度脂蛋白"],
    }
    for key, aliases in exposure_aliases.items():
        alias = _contains_alias(message, aliases)
        if alias:
            concept = EXPOSURE_CONCEPTS[key]
            exposures.append(
                ExtractedEntity(
                    kind="exposure",
                    text=alias,
                    canonical=concept["canonical"],
                    code=concept["column"] or None,
                    metadata={"label": concept["label"]},
                )
            )

    return ExtractedEntities(diseases=diseases, drugs=drugs, demographics=demographics, exposures=exposures)



