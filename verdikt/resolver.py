"""Entity resolver — turn free text into the correct database IDs.

A user types "metformin", "TP53" or "osteoarthritis". Before we can investigate
anything we must know *what kind of thing* that is (drug / target / disease) and
its canonical ID (ChEMBL / Ensembl / EFO). Open Targets' `search` endpoint does
the heavy lifting; this module wraps it with sensible ranking and an
aging/longevity vocabulary so ambiguous longevity terms resolve well.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import longevity
from .sources.opentargets import OpenTargets

# Aging is not one disease in these databases, so we anchor longevity-flavoured
# free text to the age-related diseases that Open Targets/EFO actually models.
AGING_DISEASE_HINTS = {
    "osteoarthritis": "EFO_0002506",
    "pulmonary fibrosis": "EFO_0000768",
    "idiopathic pulmonary fibrosis": "EFO_0000768",
    "sarcopenia": "EFO_0004251",
    "alzheimer": "MONDO_0004975",
    "alzheimer's disease": "MONDO_0004975",
    "type 2 diabetes": "MONDO_0005148",
    "metabolic disease": "EFO_0000589",
    "frailty": "EFO_0008572",
}

# Longevity *concepts* that are not single entities in these databases. We map
# each to a representative agent so the tool can still investigate them, and carry
# a note so the brief is honest that a class is being probed via a proxy.
CONCEPT_ALIASES = {
    "senolytics": ("dasatinib", "“Senolytics” is a drug class; analysed via a representative "
                                 "senolytic (dasatinib, classically studied with quercetin)."),
    "senolytic": ("dasatinib", "“Senolytic” is a drug class; analysed via a representative "
                               "senolytic (dasatinib)."),
    "senotherapeutics": ("navitoclax", "Senotherapeutic class; analysed via representative "
                                       "senolytic navitoclax (ABT-263)."),
    "nad booster": ("nicotinamide riboside", "NAD+ boosters are a class; analysed via "
                                             "nicotinamide riboside."),
    "nad+ booster": ("nicotinamide riboside", "NAD+ boosters are a class; analysed via "
                                              "nicotinamide riboside."),
    "mtor inhibitor": ("rapamycin", "mTOR inhibitors are a class; analysed via rapamycin (sirolimus)."),
    "mtor inhibitors": ("rapamycin", "mTOR inhibitors are a class; analysed via rapamycin (sirolimus)."),
    "caloric restriction mimetic": ("metformin", "CR mimetics are a class; analysed via metformin."),
}

# Which entity to trust when free text matches several. Drugs and targets are the
# most common intent for this tool; diseases come last because many drug/gene
# names also appear as measurement or phenotype "diseases".
ENTITY_PRIORITY = {"drug": 0, "target": 1, "disease": 2}


@dataclass
class ResolvedEntity:
    kind: str  # "drug" | "target" | "disease"
    id: str
    name: str
    query: str
    description: str | None = None
    alternatives: list[dict] = field(default_factory=list)
    note: str | None = None  # set when resolved via a longevity concept alias

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "query": self.query,
            "description": self.description,
            "alternatives": self.alternatives,
            "note": self.note,
        }


class EntityResolver:
    def __init__(self, open_targets: OpenTargets | None = None):
        self.ot = open_targets or OpenTargets()

    def resolve(self, text: str) -> ResolvedEntity | None:
        text = text.strip()
        if not text:
            return None

        # Longevity class terms have no single database entity — redirect to a
        # representative agent and remember why.
        note = None
        search_text = text
        alias = CONCEPT_ALIASES.get(text.lower())
        if alias:
            search_text, note = alias

        hits = self.ot.search(search_text)
        if not hits:
            return None

        lowered = search_text.lower()
        best = self._rank(hits, lowered)

        # Keep the picker on-focus: drugs and targets always, but only
        # aging-related diseases (Verdikt reasons through an aging/longevity lens,
        # so unrelated diseases like head & neck cancer would just be noise here).
        def _keep(h) -> bool:
            if h.get("entity") in ("drug", "target"):
                return True
            return longevity.is_age_related(h.get("name"))

        alternatives = [
            {"kind": h["entity"], "id": h["id"], "name": h["name"]}
            for h in hits
            if h["id"] != best["id"] and _keep(h)
        ][:5]

        return ResolvedEntity(
            kind=best["entity"],
            id=best["id"],
            name=best["name"],
            query=text,
            description=best.get("description"),
            alternatives=alternatives,
            note=note,
        )

    def _rank(self, hits: list[dict], lowered: str) -> dict:
        """Pick the best hit: exact-name matches first, then Open Targets' own
        relevance order, gently biased toward drugs/targets over diseases."""

        def score(index_hit) -> tuple:
            index, h = index_hit
            name = (h.get("name") or "").lower()
            exact = 0 if name == lowered else 1
            starts = 0 if name.startswith(lowered) else 1
            priority = ENTITY_PRIORITY.get(h["entity"], 3)
            # Exact name wins outright; otherwise keep search rank but nudge by type.
            return (exact, starts, priority, index)

        return min(enumerate(hits), key=score)[1]
