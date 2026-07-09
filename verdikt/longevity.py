"""Aging & longevity domain mapping.

"Aging" is not a single disease in these databases, so we anchor longevity
questions to the age-related diseases the databases actually model. Rather than
hard-code fragile IDs everywhere, we match on disease *names* returned by the
sources — robust to ID churn and good enough to flag longevity relevance.
"""
from __future__ import annotations

# Canonical age-related diseases we care about, with the primary EFO/MONDO id
# used by Open Targets (handy when we want to query a specific disease directly).
AGE_RELATED_DISEASES = [
    {"name": "osteoarthritis", "id": "MONDO_0005178"},
    {"name": "idiopathic pulmonary fibrosis", "id": "EFO_0000768"},
    {"name": "sarcopenia", "id": "EFO_0004251"},
    {"name": "Alzheimer disease", "id": "MONDO_0004975"},
    {"name": "Parkinson disease", "id": "MONDO_0005180"},
    {"name": "type 2 diabetes mellitus", "id": "MONDO_0005148"},
    {"name": "metabolic disease", "id": "EFO_0000589"},
    {"name": "atherosclerosis", "id": "EFO_0003914"},
    {"name": "osteoporosis", "id": "EFO_0003882"},
    {"name": "age-related macular degeneration", "id": "MONDO_0005298"},
    {"name": "frailty", "id": "EFO_0008572"},
]

# Substrings that mark a disease / paper as longevity-relevant.
AGING_KEYWORDS = (
    "aging",
    "ageing",
    "senescence",
    "senolytic",
    "longevity",
    "lifespan",
    "healthspan",
    "osteoarthritis",
    "pulmonary fibrosis",
    "sarcopenia",
    "alzheimer",
    "parkinson",
    "dementia",
    "neurodegenerat",
    "diabetes",
    "metabolic",
    "obesity",
    "frailty",
    "macular degeneration",
    "atherosclerosis",
    "cardiovascular",
    "osteoporosis",
    "cataract",
    "kidney disease",
)


def is_age_related(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(k in lowered for k in AGING_KEYWORDS)


def filter_age_related(items: list[dict], key: str) -> list[dict]:
    """Keep only the items whose `key` field reads as age-related."""
    return [it for it in items if is_age_related(it.get(key))]
