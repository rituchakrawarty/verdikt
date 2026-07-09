"""openFDA drug label client — approved indications and real-world safety.

If a compound is FDA-approved, its label is the ground truth on what it is
approved *for* and what its boxed warnings are. That distinguishes "approved and
repurposable" from "investigational" — a big input to the confidence score. An
openFDA API key is optional (raises the rate limit); the config slot is wired.
"""
from __future__ import annotations

from .base import BaseSource

# Human-readable label pages live on DailyMed, keyed by SPL set id.
DAILYMED_URL = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={}"
OPENFDA_QUERY_URL = "https://api.fda.gov/drug/label.json?search={}"


def _first(value) -> str | None:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _clip(text: str | None, limit: int = 600) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


class OpenFDA(BaseSource):
    key = "openfda"
    label = "openFDA"
    homepage = "https://open.fda.gov"
    base_url = "https://api.fda.gov"
    min_interval = 0.3

    def _auth_params(self) -> dict:
        return {"api_key": self.config.openfda_api_key} if self.config.openfda_api_key else {}

    def label(self, drug_name: str) -> dict | None:
        """Fetch the most relevant drug label for a generic/brand name.

        openFDA happily returns combination products, so we pull a few candidates
        and prefer the one whose generic name most cleanly matches the query
        (i.e. metformin monotherapy over sitagliptin+metformin).
        """
        target = drug_name.strip().lower()
        for field in ("openfda.generic_name", "openfda.brand_name"):
            params = {"search": f'{field}:"{drug_name}"', "limit": 5}
            params.update(self._auth_params())
            try:
                data = self._get("/drug/label.json", params=params,
                                 cache_key=("label", field, drug_name))
            except Exception:
                continue
            results = data.get("results") or []
            if not results:
                continue

            def match_score(r: dict) -> tuple:
                generics = [g.lower() for g in (r.get("openfda", {}).get("generic_name") or [])]
                joined = ", ".join(generics)
                exact = 0 if target in generics else 1          # exact monotherapy match
                combo = joined.count(" and ") + joined.count(",")  # fewer components = simpler
                return (exact, combo)

            best = min(results, key=match_score)
            return self._normalise(best, drug_name)
        return None

    def _normalise(self, r: dict, query: str) -> dict:
        openfda = r.get("openfda", {})
        set_id = _first(openfda.get("spl_set_id"))
        return {
            "query": query,
            "genericName": _first(openfda.get("generic_name")),
            "brandName": _first(openfda.get("brand_name")),
            "manufacturer": _first(openfda.get("manufacturer_name")),
            "route": _first(openfda.get("route")),
            "indications": _clip(_first(r.get("indications_and_usage"))),
            "boxedWarning": _clip(_first(r.get("boxed_warning"))),
            "contraindications": _clip(_first(r.get("contraindications"))),
            "warnings": _clip(_first(r.get("warnings_and_cautions") or r.get("warnings"))),
            "hasBoxedWarning": bool(r.get("boxed_warning")),
            "url": DAILYMED_URL.format(set_id) if set_id else self.homepage,
        }
