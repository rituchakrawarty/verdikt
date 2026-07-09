"""Open Targets Platform client — the anchor source.

Open Targets ties targets, diseases and drugs together with quantitative
association scores, genetics, tractability and known drugs, so it is the first
place we look and the backbone the other four sources hang off.

Everything here returns plain dicts with a consistent shape and, crucially, a
`url` that points at the human-readable Open Targets page so every fact in the
final brief can be a clickable source chip.
"""
from __future__ import annotations

from .base import BaseSource

# Human-facing platform pages (used for clickable source chips in the brief).
PLATFORM = "https://platform.opentargets.org"


def _drug_url(chembl_id: str) -> str:
    return f"{PLATFORM}/drug/{chembl_id}"


def _target_url(ensembl_id: str) -> str:
    return f"{PLATFORM}/target/{ensembl_id}"


def _disease_url(efo_id: str) -> str:
    return f"{PLATFORM}/disease/{efo_id}"


def _evidence_url(ensembl_id: str, efo_id: str) -> str:
    return f"{PLATFORM}/evidence/{ensembl_id}/{efo_id}"


# Map Open Targets datatype ids to friendlier labels for the brief.
DATATYPE_LABELS = {
    "genetic_association": "Human genetics",
    "genetic_literature": "Genetic literature",
    "somatic_mutation": "Somatic mutation",
    "known_drug": "Known drug",
    "affected_pathway": "Pathways / systems biology",
    "literature": "Text mining",
    "rna_expression": "RNA expression",
    "animal_model": "Animal models",
}


class OpenTargets(BaseSource):
    key = "opentargets"
    label = "Open Targets"
    homepage = "https://platform.opentargets.org"
    base_url = "https://api.platform.opentargets.org/api/v4/graphql"

    def _gql(self, query: str, variables: dict, cache_key) -> dict:
        payload = self._post(json={"query": query, "variables": variables}, cache_key=cache_key)
        if "errors" in payload:
            msgs = "; ".join(e.get("message", "?") for e in payload["errors"])
            # Partial data is common in GraphQL; only raise if there is no data at all.
            if not payload.get("data"):
                from .base import SourceError

                raise SourceError(f"{self.label}: GraphQL errors — {msgs}")
        return payload.get("data") or {}

    # -- entity resolution --------------------------------------------------
    _SEARCH = """
    query Search($q: String!, $entities: [String!]) {
      search(queryString: $q, entityNames: $entities) {
        hits { id name entity description }
      }
    }"""

    def search(self, text: str, entities: list[str] | None = None) -> list[dict]:
        entities = entities or ["drug", "target", "disease"]
        data = self._gql(
            self._SEARCH,
            {"q": text, "entities": entities},
            cache_key=("search", text, tuple(entities)),
        )
        hits = (data.get("search") or {}).get("hits") or []
        return [
            {
                "id": h["id"],
                "name": h["name"],
                "entity": h["entity"],
                "description": h.get("description"),
            }
            for h in hits
        ]

    # -- drug ---------------------------------------------------------------
    _DRUG = """
    query Drug($id: String!) {
      drug(chemblId: $id) {
        id name drugType maximumClinicalStage description
        mechanismsOfAction {
          rows { mechanismOfAction actionType targetName targets { id approvedSymbol } }
        }
        indications {
          count
          rows { maxClinicalStage disease { id name therapeuticAreas { id name } } }
        }
        drugWarnings { warningType description year toxicityClass country }
      }
    }"""

    def drug(self, chembl_id: str) -> dict | None:
        data = self._gql(self._DRUG, {"id": chembl_id}, cache_key=("drug", chembl_id))
        d = data.get("drug")
        if not d:
            return None
        moa = []
        for r in (d.get("mechanismsOfAction") or {}).get("rows", []):
            syms = [t["approvedSymbol"] for t in (r.get("targets") or []) if t.get("approvedSymbol")]
            moa.append({
                "mechanism": r["mechanismOfAction"],
                "actionType": r.get("actionType"),
                "targets": syms[:8],          # top 8 kept for the brief; full count below
                "targetsTotal": len(syms),
            })
        indications = [
            {
                "maxPhase": r.get("maxClinicalStage"),
                "diseaseId": r["disease"]["id"],
                "disease": r["disease"]["name"],
                "therapeuticAreas": [ta["name"] for ta in (r["disease"].get("therapeuticAreas") or [])],
            }
            for r in (d.get("indications") or {}).get("rows", [])
        ]
        warnings = [
            {
                "type": w.get("warningType"),
                "description": w.get("description"),
                "year": w.get("year"),
                "toxicityClass": w.get("toxicityClass"),
                "country": w.get("country"),
            }
            for w in (d.get("drugWarnings") or [])
        ]
        return {
            "id": d["id"],
            "name": d["name"],
            "drugType": d.get("drugType"),
            "maxClinicalStage": d.get("maximumClinicalStage"),
            "description": d.get("description"),
            "mechanisms": moa,
            "indicationCount": (d.get("indications") or {}).get("count", 0),
            "indications": indications,
            "warnings": warnings,
            "url": _drug_url(d["id"]),
        }

    # -- target -------------------------------------------------------------
    _TARGET = """
    query Target($id: String!, $size: Int!) {
      target(ensemblId: $id) {
        id approvedSymbol approvedName biotype functionDescriptions
        tractability { label modality value }
        associatedDiseases(page: { index: 0, size: $size }) {
          count
          rows {
            score
            datatypeScores { id score }
            disease { id name therapeuticAreas { id name } }
          }
        }
        drugAndClinicalCandidates {
          count
          rows { maxClinicalStage drug { id name } diseases { disease { id name } } }
        }
      }
    }"""

    def target(self, ensembl_id: str, disease_limit: int = 20) -> dict | None:
        data = self._gql(
            self._TARGET,
            {"id": ensembl_id, "size": disease_limit},
            cache_key=("target", ensembl_id, disease_limit),
        )
        t = data.get("target")
        if not t:
            return None
        tract = [
            {"modality": r.get("modality"), "label": r.get("label"), "value": r.get("value")}
            for r in (t.get("tractability") or [])
            if r.get("value")  # keep only the buckets that are actually true
        ]
        assoc = [
            {
                "diseaseId": r["disease"]["id"],
                "disease": r["disease"]["name"],
                "score": r.get("score"),
                "datatypes": {
                    DATATYPE_LABELS.get(s["id"], s["id"]): s["score"]
                    for s in (r.get("datatypeScores") or [])
                },
                "therapeuticAreas": [ta["name"] for ta in (r["disease"].get("therapeuticAreas") or [])],
                "url": _evidence_url(t["id"], r["disease"]["id"]),
            }
            for r in (t.get("associatedDiseases") or {}).get("rows", [])
        ]
        candidates = [
            {
                "maxPhase": r.get("maxClinicalStage"),
                "drug": (r.get("drug") or {}).get("name"),
                "drugId": (r.get("drug") or {}).get("id"),
                "diseases": [
                    d["disease"]["name"]
                    for d in (r.get("diseases") or [])
                    if d.get("disease")
                ],
            }
            for r in (t.get("drugAndClinicalCandidates") or {}).get("rows", [])
        ]
        return {
            "id": t["id"],
            "symbol": t["approvedSymbol"],
            "name": t.get("approvedName"),
            "biotype": t.get("biotype"),
            "function": (t.get("functionDescriptions") or [None])[0],
            "tractability": tract,
            "associationCount": (t.get("associatedDiseases") or {}).get("count", 0),
            "associations": assoc,
            "clinicalCandidateCount": (t.get("drugAndClinicalCandidates") or {}).get("count", 0),
            "clinicalCandidates": candidates,
            "url": _target_url(t["id"]),
        }

    # -- disease ------------------------------------------------------------
    _DISEASE = """
    query Disease($id: String!, $size: Int!) {
      disease(efoId: $id) {
        id name description therapeuticAreas { id name }
        associatedTargets(page: { index: 0, size: $size }) {
          count
          rows {
            score
            datatypeScores { id score }
            target { id approvedSymbol approvedName }
          }
        }
      }
    }"""

    def disease(self, efo_id: str, target_limit: int = 20) -> dict | None:
        data = self._gql(
            self._DISEASE,
            {"id": efo_id, "size": target_limit},
            cache_key=("disease", efo_id, target_limit),
        )
        d = data.get("disease")
        if not d:
            return None
        targets = [
            {
                "targetId": r["target"]["id"],
                "symbol": r["target"]["approvedSymbol"],
                "name": r["target"].get("approvedName"),
                "score": r.get("score"),
                "datatypes": {
                    DATATYPE_LABELS.get(s["id"], s["id"]): s["score"]
                    for s in (r.get("datatypeScores") or [])
                },
                "url": _evidence_url(r["target"]["id"], d["id"]),
            }
            for r in (d.get("associatedTargets") or {}).get("rows", [])
        ]
        return {
            "id": d["id"],
            "name": d["name"],
            "description": d.get("description"),
            "therapeuticAreas": [ta["name"] for ta in (d.get("therapeuticAreas") or [])],
            "targetCount": (d.get("associatedTargets") or {}).get("count", 0),
            "topTargets": targets,
            "url": _disease_url(d["id"]),
        }
