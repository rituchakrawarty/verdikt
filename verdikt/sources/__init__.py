"""Data-source clients. All share the transport in `base.BaseSource`."""

from .base import BaseSource, SourceError
from .chembl import ChEMBL
from .clinicaltrials import ClinicalTrials
from .openfda import OpenFDA
from .opentargets import OpenTargets
from .pubmed import PubMed

# Uniform registry so the agent and UI can iterate sources generically.
ALL_SOURCES = [OpenTargets, ClinicalTrials, ChEMBL, PubMed, OpenFDA]

__all__ = [
    "BaseSource",
    "SourceError",
    "OpenTargets",
    "ClinicalTrials",
    "ChEMBL",
    "PubMed",
    "OpenFDA",
    "ALL_SOURCES",
]
