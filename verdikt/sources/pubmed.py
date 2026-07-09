"""PubMed / NCBI E-utilities client — literature volume and evidence.

We use PubMed for two signals: *how much* has been published on a
question (a proxy for evidence maturity) and *what the strongest recent papers
are*. An NCBI API key is optional but lifts the rate limit; the config slot is
wired through here.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from .base import BaseSource

ARTICLE_URL = "https://pubmed.ncbi.nlm.nih.gov/{}/"
SEARCH_URL = "https://pubmed.ncbi.nlm.nih.gov/?term={}"


class PubMed(BaseSource):
    key = "pubmed"
    label = "PubMed"
    homepage = "https://pubmed.ncbi.nlm.nih.gov"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    # NCBI asks for <=3 req/s without a key, <=10 with one.
    min_interval = 0.34

    def _auth_params(self) -> dict:
        params = {"tool": "Verdikt", "email": self.config.contact_email}
        if self.config.ncbi_api_key:
            params["api_key"] = self.config.ncbi_api_key
            self.min_interval = 0.11
        return params

    def count(self, term: str) -> int:
        """Just the number of papers matching a query — cheap relevance signal."""
        params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": 0}
        params.update(self._auth_params())
        data = self._get("/esearch.fcgi", params=params, cache_key=("count", term))
        return int(data.get("esearchresult", {}).get("count", 0))

    def search(self, term: str, retmax: int = 8) -> dict:
        params = {
            "db": "pubmed",
            "term": term,
            "retmode": "json",
            "retmax": retmax,
            "sort": "relevance",
        }
        params.update(self._auth_params())
        data = self._get("/esearch.fcgi", params=params, cache_key=("search", term, retmax))
        res = data.get("esearchresult", {})
        pmids = res.get("idlist", [])
        articles = self._summaries(pmids) if pmids else []
        return {
            "term": term,
            "count": int(res.get("count", 0)),
            "articles": articles,
            "url": SEARCH_URL.format(quote_plus(term)),
        }

    def _summaries(self, pmids: list[str]) -> list[dict]:
        params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
        params.update(self._auth_params())
        data = self._get("/esummary.fcgi", params=params, cache_key=("summ", tuple(pmids)))
        result = data.get("result", {})
        out = []
        for pmid in result.get("uids", []):
            doc = result.get(pmid, {})
            authors = [a.get("name") for a in doc.get("authors", [])][:3]
            out.append(
                {
                    "pmid": pmid,
                    "title": doc.get("title"),
                    "journal": doc.get("fulljournalname") or doc.get("source"),
                    "pubdate": doc.get("pubdate"),
                    "authors": authors,
                    "url": ARTICLE_URL.format(pmid),
                }
            )
        return out
