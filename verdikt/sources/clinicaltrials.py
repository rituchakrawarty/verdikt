"""ClinicalTrials.gov API v2 client.

This is where hype meets reality: how far a drug/target actually got in humans,
who ran the trials, and — most importantly — *why the failures stopped*. We
deliberately make a second, targeted call for terminated / suspended / withdrawn
studies so the `whyStopped` reason (often the single most decision-relevant fact
in the whole brief) is never buried past the first page of results.
"""
from __future__ import annotations

from collections import Counter

from .base import BaseSource

STUDY_URL = "https://clinicaltrials.gov/study/{}"
SEARCH_URL = "https://clinicaltrials.gov/search?term={}"

# Statuses that represent a trial that did not run to completion as planned.
STOPPED_STATUSES = ["TERMINATED", "SUSPENDED", "WITHDRAWN"]

_FIELDS = ",".join(
    [
        "protocolSection.identificationModule.nctId",
        "protocolSection.identificationModule.briefTitle",
        "protocolSection.statusModule.overallStatus",
        "protocolSection.statusModule.whyStopped",
        "protocolSection.statusModule.startDateStruct.date",
        "protocolSection.designModule.phases",
        "protocolSection.sponsorCollaboratorsModule.leadSponsor.name",
        "protocolSection.conditionsModule.conditions",
    ]
)


def _pretty_phase(phases: list[str] | None) -> str:
    if not phases:
        return "N/A"
    return "/".join(p.replace("PHASE", "Phase ").strip() for p in phases)


class ClinicalTrials(BaseSource):
    key = "clinicaltrials"
    label = "ClinicalTrials.gov"
    homepage = "https://clinicaltrials.gov"
    base_url = "https://clinicaltrials.gov/api/v2"
    min_interval = 0.2  # be polite; the API is generous but shared

    def _flatten(self, study: dict) -> dict:
        ps = study.get("protocolSection", {})
        ident = ps.get("identificationModule", {})
        status = ps.get("statusModule", {})
        design = ps.get("designModule", {})
        sponsor = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
        conditions = ps.get("conditionsModule", {}).get("conditions", [])
        nct = ident.get("nctId")
        return {
            "nctId": nct,
            "title": ident.get("briefTitle"),
            "status": status.get("overallStatus"),
            "whyStopped": status.get("whyStopped"),
            "startDate": (status.get("startDateStruct") or {}).get("date"),
            "phases": design.get("phases") or [],
            "phaseLabel": _pretty_phase(design.get("phases")),
            "sponsor": sponsor.get("name"),
            "conditions": conditions,
            "url": STUDY_URL.format(nct) if nct else None,
        }

    def _query(self, term: str, *, status: list[str] | None = None, page_size: int = 100,
               count_total: bool = False) -> dict:
        params = {"query.term": term, "pageSize": page_size, "fields": _FIELDS}
        if status:
            params["filter.overallStatus"] = "|".join(status)
        if count_total:
            params["countTotal"] = "true"
        return self._get(
            "/studies",
            params=params,
            cache_key=("ct", term, tuple(status or ()), page_size, count_total),
        )

    def evidence(self, term: str, sample_size: int = 120) -> dict:
        """Aggregate trial evidence for a free-text term (drug name or condition)."""
        # Call A: representative sample + true total count.
        overview = self._query(term, page_size=sample_size, count_total=True)
        studies = [self._flatten(s) for s in overview.get("studies", [])]
        total = overview.get("totalCount", len(studies))

        status_counts = Counter(s["status"] for s in studies if s["status"])
        phase_counts = Counter(
            p for s in studies for p in (s["phases"] or ["NA"])
        )
        sponsors = Counter(s["sponsor"] for s in studies if s["sponsor"])

        # Call B: dedicated pass so we never miss a stopped trial's reason.
        stopped_raw = self._query(term, status=STOPPED_STATUSES, page_size=40)
        stopped = [self._flatten(s) for s in stopped_raw.get("studies", [])]
        stopped_with_reason = [s for s in stopped if s.get("whyStopped")]

        # Highest-phase completed studies make the strongest positive signal.
        phase_rank = {"PHASE4": 4, "PHASE3": 3, "PHASE2": 2, "PHASE1": 1}
        completed = [s for s in studies if s["status"] == "COMPLETED"]
        completed.sort(
            key=lambda s: max((phase_rank.get(p, 0) for p in s["phases"]), default=0),
            reverse=True,
        )

        return {
            "term": term,
            "totalTrials": total,
            "sampled": len(studies),
            "statusBreakdown": dict(status_counts),
            "phaseBreakdown": {_pretty_phase([p]): c for p, c in phase_counts.items()},
            "topSponsors": [{"name": n, "trials": c} for n, c in sponsors.most_common(5)],
            "stoppedCount": len(stopped),
            "stoppedTrials": stopped_with_reason[:12],
            "topCompleted": completed[:8],
            "url": SEARCH_URL.format(term.replace(" ", "+")),
        }
