"""ChEMBL client — compounds, mechanisms and hard potency numbers.

ChEMBL is the quantitative pharmacology backstop: is there real, potent chemical
matter against this target, and what does the drug actually do? The activity
table is enormous, so — as warned — we NEVER query it without both a
`target_chembl_id` and a `standard_type`, and we cap the page size hard.
"""
from __future__ import annotations

import statistics

from .base import BaseSource

COMPOUND_URL = "https://www.ebi.ac.uk/chembl/explore/compound/{}"
TARGET_URL = "https://www.ebi.ac.uk/chembl/explore/target/{}"

# Potency measures worth summarising, in rough order of preference.
POTENCY_TYPES = ("IC50", "Ki", "EC50", "Kd")


class ChEMBL(BaseSource):
    key = "chembl"
    label = "ChEMBL"
    homepage = "https://www.ebi.ac.uk/chembl"
    base_url = "https://www.ebi.ac.uk/chembl/api/data"
    min_interval = 0.2

    # -- compounds ----------------------------------------------------------
    def molecule(self, chembl_id: str) -> dict | None:
        try:
            m = self._get(f"/molecule/{chembl_id}.json", cache_key=("mol", chembl_id))
        except Exception:
            return None
        if not m or "molecule_chembl_id" not in m:
            return None
        props = m.get("molecule_properties") or {}
        return {
            "id": m.get("molecule_chembl_id"),
            "name": m.get("pref_name"),
            "maxPhase": m.get("max_phase"),
            "firstApproval": m.get("first_approval"),
            "moleculeType": m.get("molecule_type"),
            "oral": m.get("oral"),
            "withdrawn": m.get("withdrawn_flag"),
            "qedWeighted": props.get("qed_weighted"),
            "url": COMPOUND_URL.format(m.get("molecule_chembl_id")),
        }

    def mechanisms(self, molecule_chembl_id: str) -> list[dict]:
        data = self._get(
            "/mechanism.json",
            params={"molecule_chembl_id": molecule_chembl_id, "limit": 20},
            cache_key=("mech", molecule_chembl_id),
        )
        return [
            {
                "mechanism": r.get("mechanism_of_action"),
                "actionType": r.get("action_type"),
                "targetId": r.get("target_chembl_id"),
                "maxPhase": r.get("max_phase"),
            }
            for r in (data.get("mechanisms") or [])
        ]

    # -- targets ------------------------------------------------------------
    def find_target(self, name: str) -> dict | None:
        """Resolve a protein name/symbol to a ChEMBL target id (single protein)."""
        data = self._get(
            "/target.json",
            params={"pref_name__icontains": name, "target_type": "SINGLE PROTEIN", "limit": 1},
            cache_key=("findtarget", name),
        )
        rows = data.get("targets") or []
        if not rows:
            return None
        t = rows[0]
        return {
            "id": t.get("target_chembl_id"),
            "name": t.get("pref_name"),
            "organism": t.get("organism"),
            "url": TARGET_URL.format(t.get("target_chembl_id")),
        }

    def target_potency(self, target_chembl_id: str, standard_type: str = "IC50",
                       limit: int = 60) -> dict:
        """Summarise potency of chemical matter against a target.

        Tightly filtered by design: `target_chembl_id` + `standard_type`, small
        page. Returns aggregate pChEMBL stats plus the most potent compounds.
        """
        data = self._get(
            "/activity.json",
            params={
                "target_chembl_id": target_chembl_id,
                "standard_type": standard_type,
                "pchembl_value__isnull": "false",
                "limit": limit,
            },
            cache_key=("act", target_chembl_id, standard_type, limit),
        )
        rows = data.get("activities") or []
        total = (data.get("page_meta") or {}).get("total_count", len(rows))

        pchembls: list[float] = []
        compounds = []
        for a in rows:
            try:
                pc = float(a["pchembl_value"]) if a.get("pchembl_value") else None
            except (TypeError, ValueError):
                pc = None
            if pc is not None:
                pchembls.append(pc)
            compounds.append(
                {
                    "id": a.get("molecule_chembl_id"),
                    "value": a.get("standard_value"),
                    "units": a.get("standard_units"),
                    "type": a.get("standard_type"),
                    "pchembl": pc,
                    "url": COMPOUND_URL.format(a.get("molecule_chembl_id")),
                }
            )
        # Most potent first (higher pChEMBL = more potent).
        compounds.sort(key=lambda c: (c["pchembl"] is not None, c["pchembl"] or 0), reverse=True)

        summary = {}
        if pchembls:
            summary = {
                "maxPchembl": round(max(pchembls), 2),
                "medianPchembl": round(statistics.median(pchembls), 2),
                "potentCount": sum(1 for p in pchembls if p >= 6),  # ~<=1µM
            }
        return {
            "targetId": target_chembl_id,
            "standardType": standard_type,
            "totalActivities": total,
            "sampled": len(rows),
            "summary": summary,
            "topCompounds": compounds[:8],
            "url": TARGET_URL.format(target_chembl_id),
        }
