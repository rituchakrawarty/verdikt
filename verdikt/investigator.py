"""Investigator — deterministically gathers the evidence bundle.

The Claude agent decides *what it all means*; this module reliably fetches the
raw material. Gathering is deterministic (not tool-calling) so it is fast,
debuggable and easy to stream.

For trust ("show your work", Feynman-style) each step emits:
- a plain-English PURPOSE on start  — what we are about to check and why, and
- a plain-English FINDING on done   — what we actually found, in one line.

The output is a single `bundle` dict plus a `sourceIndex` (every clickable
source used, keyed by a short id) so the analyst can cite by id and the UI can
render source chips.
"""
from __future__ import annotations

import time
from typing import Callable

from . import longevity
from .config import CONFIG
from .resolver import ResolvedEntity
from .sources import ChEMBL, ClinicalTrials, OpenFDA, OpenTargets, PubMed
from .sources.base import SourceError

Emit = Callable[[dict], None]

# We send the reasoning engine only the top N items of each long list (prioritising
# age-related ones), which keeps cost low. We ALWAYS keep the true total count next to
# it (indicationCount, associationCount, targetCount) so nothing is hidden — the brief
# shows "top 8 of N", and every source chip links to the complete data.
TOP_N = 8


def _noop(_event: dict) -> None:
    pass


class Investigator:
    def __init__(
        self,
        open_targets: OpenTargets | None = None,
        clinical_trials: ClinicalTrials | None = None,
        chembl: ChEMBL | None = None,
        pubmed: PubMed | None = None,
        openfda: OpenFDA | None = None,
    ):
        self.ot = open_targets or OpenTargets()
        self.ct = clinical_trials or ClinicalTrials()
        self.chembl = chembl or ChEMBL()
        self.pubmed = pubmed or PubMed()
        self.openfda = openfda or OpenFDA()

    # -- event-wrapped source calls ----------------------------------------
    def _run_source(self, emit: Emit, source_id: str, label: str, purpose: str,
                    fn, finding_fn=None):
        """Run one source call, streaming what we're checking and what we found,
        and recording it in the evidence log so the brief can show the Evidence
        phase (what each database contributed)."""
        emit({"type": "source_start", "source": source_id, "label": label, "purpose": purpose})
        if CONFIG.demo_step_delay:  # pace the pipeline so each step is filmable (cached = instant)
            time.sleep(CONFIG.demo_step_delay)
        result, finding, ok = None, "", True
        try:
            result = fn()
        except SourceError as exc:
            ok, finding = False, "Couldn't reach this source."
            emit({"type": "source_error", "source": source_id, "label": label, "error": str(exc)})
        except Exception as exc:  # never let one source sink the investigation
            ok, finding = False, "Couldn't reach this source."
            emit({"type": "source_error", "source": source_id, "label": label,
                  "error": f"unexpected: {exc}"})

        if ok:
            if finding_fn is not None:
                try:
                    finding = finding_fn(result) or ""
                except Exception:
                    finding = ""
            if not finding:
                finding = "No usable data found." if not result else "Data collected."
            emit({"type": "source_done", "source": source_id, "label": label, "finding": finding})

        if getattr(self, "_log", None) is not None:
            self._log.append({"source": source_id, "label": label,
                              "purpose": purpose, "finding": finding})
        return result

    def gather(self, entity: ResolvedEntity, emit: Emit = _noop) -> dict:
        self._log = []  # evidence log for this investigation
        if entity.kind == "drug":
            return self._gather_drug(entity, emit)
        if entity.kind == "target":
            return self._gather_target(entity, emit)
        if entity.kind == "disease":
            return self._gather_disease(entity, emit)
        raise ValueError(f"Unsupported entity kind: {entity.kind}")

    # ----------------------------------------------------------------------
    def _gather_drug(self, entity: ResolvedEntity, emit: Emit) -> dict:
        name = entity.name
        index: dict[str, dict] = {}

        def f_ot(d):
            if not d:
                return "Not found in Open Targets."
            approved = d.get("maxClinicalStage") == "APPROVAL"
            return (f"{'Approved drug' if approved else 'Investigational'} · "
                    f"{d.get('indicationCount', 0)} recorded indications.")

        ot = self._run_source(emit, "opentargets", "Open Targets",
                              "See what it targets and which diseases it's tied to",
                              lambda: self.ot.drug(entity.id), f_ot)
        if ot:
            index["opentargets"] = {"label": "Open Targets", "url": ot["url"]}

        def f_mol(m):
            if not m:
                return "No ChEMBL record."
            return f"{m.get('moleculeType') or 'compound'}, max phase {m.get('maxPhase')}."

        mol = self._run_source(emit, "chembl", "ChEMBL",
                              "Confirm the compound, its type and how far it's been developed",
                              lambda: self.chembl.molecule(entity.id), f_mol)
        mechs = None
        if mol:
            index["chembl"] = {"label": "ChEMBL", "url": mol["url"]}
            mechs = self.chembl.mechanisms(entity.id)

        def f_trials(t):
            if not t:
                return "No trials found."
            return f"{t.get('totalTrials', 0)} trials · {len(t.get('stoppedTrials', []))} stopped early."

        trials = self._run_source(emit, "clinicaltrials", "ClinicalTrials.gov",
                                 "See how far it got in humans — and why any trials stopped",
                                 lambda: self.ct.evidence(name), f_trials)
        if trials:
            index["clinicaltrials"] = {"label": "ClinicalTrials.gov", "url": trials["url"]}

        def f_lit(l):
            return f"~{(l or {}).get('count', 0)} papers on this + aging/longevity."

        lit = self._run_source(emit, "pubmed", "PubMed",
                              "Gauge how much (and how recent) the research is",
                              lambda: self.pubmed.search(f"{name} AND (aging OR longevity)"), f_lit)
        if lit:
            index["pubmed"] = {"label": "PubMed", "url": lit["url"]}

        def f_label(lb):
            if not lb:
                return "No FDA label found."
            return f"FDA label found · boxed warning: {'yes' if lb.get('hasBoxedWarning') else 'no'}."

        label = self._run_source(emit, "openfda", "openFDA",
                               "Read the approved label and any safety warnings",
                               lambda: self.openfda.label(name), f_label)
        if label:
            index["openfda"] = {"label": "openFDA", "url": label["url"]}

        aging_indications = longevity.filter_age_related((ot or {}).get("indications", []), "disease")
        # Trim the indications list (metformin has 248 → ~20k tokens). Keep age-related
        # first, cap at TOP_N; indicationCount still holds the real total.
        if ot:
            rest = [i for i in ot.get("indications", []) if i not in aging_indications]
            ot["indications"] = (aging_indications + rest)[:TOP_N]
            ot["indicationsShown"] = len(ot["indications"])

        signals = {
            "approved": bool(ot and ot.get("maxClinicalStage") == "APPROVAL")
            or bool(mol and str(mol.get("maxPhase")) in ("4", "4.0")),
            "boxedWarning": bool(label and label.get("hasBoxedWarning")),
            "withdrawn": bool(mol and mol.get("withdrawn")),
            "totalTrials": (trials or {}).get("totalTrials", 0),
            "stoppedWithReason": len((trials or {}).get("stoppedTrials", [])),
            "literatureVolume": (lit or {}).get("count", 0),
            "ageRelatedIndications": [i["disease"] for i in aging_indications][:8],
        }
        return {
            "entityKind": "drug",
            "openTargets": ot,
            "chembl": {"molecule": mol, "mechanisms": mechs} if mol else None,
            "clinicalTrials": trials,
            "pubmed": lit,
            "openFDA": label,
            "signals": signals,
            "sourceIndex": index,
            "evidenceLog": list(getattr(self, "_log", [])),
        }

    # ----------------------------------------------------------------------
    def _gather_target(self, entity: ResolvedEntity, emit: Emit) -> dict:
        symbol = entity.name
        index: dict[str, dict] = {}

        def f_ot(t):
            if not t:
                return "Not found in Open Targets."
            top = (t.get("associations") or [{}])[0]
            return (f"Top disease link: {top.get('disease', '—')} "
                    f"(score {top.get('score', 0):.2f}) · {t.get('associationCount', 0)} links.")

        ot = self._run_source(emit, "opentargets", "Open Targets",
                              "Check human genetics and which diseases it's linked to",
                              lambda: self.ot.target(entity.id), f_ot)
        if ot:
            index["opentargets"] = {"label": "Open Targets", "url": ot["url"]}
            symbol = ot.get("symbol") or symbol

        def _potency():
            ct_target = self.chembl.find_target(symbol)
            if not ct_target:
                return None
            pot = self.chembl.target_potency(ct_target["id"], "IC50")
            pot["targetName"] = ct_target["name"]
            return pot

        def f_pot(p):
            if not p or not p.get("summary"):
                return "No potent chemistry found."
            s = p["summary"]
            return f"Best potency pChEMBL {s.get('maxPchembl')} · {s.get('potentCount', 0)} potent compounds."

        potency = self._run_source(emit, "chembl", "ChEMBL",
                                  "See whether potent, drug-like chemistry exists against it",
                                  _potency, f_pot)
        if potency:
            index["chembl"] = {"label": "ChEMBL", "url": potency["url"]}

        def f_trials(t):
            if not t:
                return "No trials found."
            return f"{t.get('totalTrials', 0)} trials mention it · {len(t.get('stoppedTrials', []))} stopped."

        trials = self._run_source(emit, "clinicaltrials", "ClinicalTrials.gov",
                                 "Look for human trials that target it",
                                 lambda: self.ct.evidence(symbol), f_trials)
        if trials:
            index["clinicaltrials"] = {"label": "ClinicalTrials.gov", "url": trials["url"]}

        def f_lit(l):
            return f"~{(l or {}).get('count', 0)} papers on it + aging/senescence."

        lit = self._run_source(emit, "pubmed", "PubMed",
                              "Gauge how much research ties it to aging",
                              lambda: self.pubmed.search(f"{symbol} AND (aging OR longevity OR senescence)"), f_lit)
        if lit:
            index["pubmed"] = {"label": "PubMed", "url": lit["url"]}

        aging_assoc = longevity.filter_age_related((ot or {}).get("associations", []), "disease")
        # Trim disease associations (age-related first), keeping associationCount intact.
        if ot:
            rest = [a for a in ot.get("associations", []) if a not in aging_assoc]
            ot["associations"] = (aging_assoc + rest)[:TOP_N]
            ot["associationsShown"] = len(ot["associations"])
            ot["clinicalCandidates"] = ot.get("clinicalCandidates", [])[:TOP_N]

        best_genetic = 0.0
        for a in (ot or {}).get("associations", []):
            best_genetic = max(best_genetic, a.get("datatypes", {}).get("Human genetics", 0) or 0)
        signals = {
            "topAssociationScore": ((ot or {}).get("associations") or [{}])[0].get("score", 0),
            "bestHumanGeneticsScore": round(best_genetic, 3),
            "ageRelatedAssociations": [
                {"disease": a["disease"], "score": a["score"]} for a in aging_assoc
            ][:8],
            "tractable": bool((ot or {}).get("tractability")),
            "clinicalCandidates": (ot or {}).get("clinicalCandidateCount", 0),
            "potentChemistry": bool(potency and potency.get("summary", {}).get("potentCount")),
            "literatureVolume": (lit or {}).get("count", 0),
        }
        return {
            "entityKind": "target",
            "openTargets": ot,
            "chembl": potency,
            "clinicalTrials": trials,
            "pubmed": lit,
            "signals": signals,
            "sourceIndex": index,
            "evidenceLog": list(getattr(self, "_log", [])),
        }

    # ----------------------------------------------------------------------
    def _gather_disease(self, entity: ResolvedEntity, emit: Emit) -> dict:
        name = entity.name
        index: dict[str, dict] = {}

        def f_ot(d):
            if not d:
                return "Not found in Open Targets."
            top = (d.get("topTargets") or [{}])[0]
            return f"{d.get('targetCount', 0)} gene targets · strongest: {top.get('symbol', '—')}."

        ot = self._run_source(emit, "opentargets", "Open Targets",
                              "Find the strongest gene targets behind this disease",
                              lambda: self.ot.disease(entity.id), f_ot)
        if ot:
            index["opentargets"] = {"label": "Open Targets", "url": ot["url"]}
            # Keep only the top targets for the LLM; targetCount holds the real total.
            ot["topTargets"] = ot.get("topTargets", [])[:TOP_N]

        def f_trials(t):
            if not t:
                return "No trials found."
            return f"{t.get('totalTrials', 0)} trials · {len(t.get('stoppedTrials', []))} stopped early."

        trials = self._run_source(emit, "clinicaltrials", "ClinicalTrials.gov",
                                 "See the scale of human trials in this disease",
                                 lambda: self.ct.evidence(name), f_trials)
        if trials:
            index["clinicaltrials"] = {"label": "ClinicalTrials.gov", "url": trials["url"]}

        def f_lit(l):
            return f"~{(l or {}).get('count', 0)} papers on it + aging."

        lit = self._run_source(emit, "pubmed", "PubMed",
                              "Gauge how strongly it's studied as an aging disease",
                              lambda: self.pubmed.search(f"{name} AND (aging OR senescence OR longevity)"), f_lit)
        if lit:
            index["pubmed"] = {"label": "PubMed", "url": lit["url"]}

        signals = {
            "topTargetCount": (ot or {}).get("targetCount", 0),
            "topTargets": [
                {"symbol": t["symbol"], "score": t["score"]}
                for t in (ot or {}).get("topTargets", [])[:8]
            ],
            "totalTrials": (trials or {}).get("totalTrials", 0),
            "literatureVolume": (lit or {}).get("count", 0),
            "isAgeRelated": longevity.is_age_related(name),
        }
        return {
            "entityKind": "disease",
            "openTargets": ot,
            "clinicalTrials": trials,
            "pubmed": lit,
            "signals": signals,
            "sourceIndex": index,
            "evidenceLog": list(getattr(self, "_log", [])),
        }
