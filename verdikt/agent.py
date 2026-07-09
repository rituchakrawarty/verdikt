"""The agent — orchestrates resolve → plan → gather → reason → brief.

The reasoning is pluggable behind the `Reasoner` protocol:

* `ClaudeReasoner` is the real brain (Anthropic). It plans the sub-questions and
  writes the calibrated brief.
* `HeuristicReasoner` is a transparent, no-API fallback so the pipeline is
  demoable and testable without a key. It is clearly labelled as such in output.

`Agent.investigate()` streams events (resolved → plan → each source → analyzing →
brief) via an `emit` callback, which the web layer forwards to the browser.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Callable, Protocol

from .config import CONFIG, Config
from .investigator import Investigator
from .prompts import (
    ANALYST_QUICK_SYSTEM,
    ANALYST_SYSTEM,
    PLANNER_SYSTEM,
    analyst_user_prompt,
)
from .resolver import EntityResolver, ResolvedEntity

Emit = Callable[[dict], None]


def _noop(_event: dict) -> None:
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response, fences or not."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rsplit("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model response")
    return json.loads(text[start : end + 1])


class Reasoner(Protocol):
    engine: str

    def plan(self, entity: dict) -> list[dict]: ...
    def analyze(self, entity: dict, bundle: dict) -> dict: ...


# ---------------------------------------------------------------------------
class ClaudeReasoner:
    """The real reasoning engine, powered by Claude."""

    engine = "claude"

    def __init__(self, config: Config = CONFIG):
        if not config.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        import anthropic

        self.config = config
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self.model = config.model

    def _complete(self, system: str, user: str, max_tokens: int) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            # Prompt caching: the big, stable instruction block is billed at ~10%
            # on repeat calls instead of full price.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")

    def plan(self, entity: dict) -> list[dict]:
        from . import cache

        key = {"kind": "plan", "model": self.model, "entity": entity}
        hit = cache.get("claude", key, ttl=cache.CLAUDE_TTL)
        if hit is not None:
            return hit
        user = f"Resolved entity:\n{json.dumps(entity, indent=2)}\n\nReturn the plan JSON."
        raw = self._complete(PLANNER_SYSTEM, user, max_tokens=700)
        result = _extract_json(raw).get("plan", [])
        cache.put("claude", key, result)
        return result

    def analyze(self, entity: dict, bundle: dict, depth: str = "quick") -> dict:
        from . import cache

        # Cache on the evidence itself + depth: same evidence in → same reasoning
        # out, free. Quick and deep are cached separately.
        cache_key = {"kind": "analyze", "model": self.model, "depth": depth,
                     "entity_id": entity.get("id"), "signals": bundle.get("signals")}
        hit = cache.get("claude", cache_key, ttl=cache.CLAUDE_TTL)
        if hit is not None:
            return hit

        system = ANALYST_SYSTEM if depth == "deep" else ANALYST_QUICK_SYSTEM
        max_tokens = 4096 if depth == "deep" else 1400
        user = analyst_user_prompt(entity, bundle)
        raw = self._complete(system, user, max_tokens=max_tokens)
        try:
            result = _extract_json(raw)
        except (ValueError, json.JSONDecodeError):
            # One repair attempt: ask for strictly valid, compact JSON.
            repair = user + (
                "\n\nYour previous reply was not valid JSON (it may have been cut off). "
                "Return ONLY a single valid JSON object, compact, no prose, no markdown."
            )
            raw = self._complete(system, repair, max_tokens=max_tokens)
            result = _extract_json(raw)
        result["engine"] = "claude:" + self.model
        result["depth"] = depth
        cache.put("claude", cache_key, result)
        return result


# ---------------------------------------------------------------------------
class HeuristicReasoner:
    """Deterministic fallback used when no API key is available.

    It is intentionally simple and fully transparent — good enough to demo the
    UI and to anchor the scoring test, but clearly not the Claude brain.
    """

    engine = "heuristic"

    def plan(self, entity: dict) -> list[dict]:
        kind = entity.get("kind")
        common = [
            {"question": f"How strong is the evidence linking {entity.get('name')} to age-related disease?",
             "sources": ["opentargets"]},
            {"question": "What does the clinical trial record (incl. failures) show?",
             "sources": ["clinicaltrials"]},
            {"question": "How much and how recent is the supporting literature?",
             "sources": ["pubmed"]},
        ]
        if kind == "drug":
            common.insert(1, {"question": "What is the mechanism and approval/safety status?",
                              "sources": ["chembl", "openfda"]})
        elif kind == "target":
            common.insert(1, {"question": "Is the target tractable with potent chemical matter?",
                              "sources": ["chembl", "opentargets"]})
        return common

    def analyze(self, entity: dict, bundle: dict, depth: str = "quick") -> dict:
        s = bundle.get("signals", {})
        kind = bundle.get("entityKind")
        score = 40
        supporting, contradicting, missing = [], [], []

        if kind == "drug":
            if s.get("approved"):
                score += 20
                supporting.append({"claim": "FDA-approved / phase 4 drug",
                                   "detail": "Established human safety and manufacturing.",
                                   "sources": ["openfda", "chembl"]})
            if s.get("ageRelatedIndications"):
                score += 12
                supporting.append({"claim": "Studied in age-related indications",
                                   "detail": ", ".join(s["ageRelatedIndications"][:5]),
                                   "sources": ["opentargets"]})
            if s.get("boxedWarning"):
                score -= 10
                contradicting.append({"claim": "Carries a boxed warning",
                                      "detail": "Safety ceiling for broad healthy-aging use.",
                                      "sources": ["openfda"]})
        elif kind == "target":
            g = s.get("bestHumanGeneticsScore", 0)
            if g >= 0.5:
                score += 22
                supporting.append({"claim": "Human genetic support",
                                   "detail": f"Best human-genetics datatype score {g}.",
                                   "sources": ["opentargets"]})
            if s.get("potentChemistry"):
                score += 10
                supporting.append({"claim": "Potent chemical matter exists",
                                   "detail": "ChEMBL shows potent (pChEMBL≥6) compounds.",
                                   "sources": ["chembl"]})
            if s.get("ageRelatedAssociations"):
                score += 8
                supporting.append({"claim": "Associated with age-related diseases",
                                   "detail": ", ".join(a["disease"] for a in s["ageRelatedAssociations"][:4]),
                                   "sources": ["opentargets"]})
        elif kind == "disease":
            if s.get("topTargetCount"):
                score += 10
                supporting.append({"claim": "Well-characterised target landscape",
                                   "detail": f"{s['topTargetCount']} associated targets on Open Targets.",
                                   "sources": ["opentargets"]})

        stopped = s.get("stoppedWithReason", 0)
        if stopped:
            score -= min(8, 2 * stopped)
            contradicting.append({"claim": f"{stopped} trial(s) stopped early",
                                  "detail": "See whyStopped reasons; check for safety vs logistics.",
                                  "sources": ["clinicaltrials"]})

        lit = s.get("literatureVolume", 0)
        if lit > 500:
            supporting.append({"claim": "Large supporting literature",
                               "detail": f"~{lit} PubMed records (context, not proof).",
                               "sources": ["pubmed"]})
        elif lit < 30:
            missing.append({"gap": "Sparse literature",
                            "whyItMatters": "Few papers means the hypothesis is under-tested."})

        if not s.get("totalTrials"):
            missing.append({"gap": "No/again few interventional trials in aging",
                            "whyItMatters": "Human efficacy for a longevity indication is unproven."})

        score = max(0, min(100, score))
        # Build-guide verbs: Pursue / Explore / Partner / Pause / Kill.
        if kind == "drug" and s.get("approved") and s.get("boxedWarning") and score >= 50:
            verdict = "Partner"  # de-risk an approved-but-flagged asset
        elif score >= 72:
            verdict = "Pursue"
        elif score >= 56:
            verdict = "Explore"
        elif score >= 40:
            verdict = "Pause"
        else:
            verdict = "Kill"

        # Opportunity ranking — which age-related indications look strongest.
        opportunity = []
        if kind == "drug":
            for ind in s.get("ageRelatedIndications", [])[:6]:
                opportunity.append({"indication": ind,
                                    "rationale": "Studied here per Open Targets indications.",
                                    "sources": ["opentargets"]})
        elif kind == "target":
            for a in s.get("ageRelatedAssociations", [])[:6]:
                opportunity.append({"indication": a["disease"],
                                    "rationale": f"Open Targets association score {a['score']:.2f}.",
                                    "sources": ["opentargets"]})

        # Make the score transparent: turn the points that moved it into factors.
        factors = []
        for x in supporting:
            factors.append({"factor": x["claim"], "effect": "up", "note": x.get("detail", "")})
        for x in contradicting:
            factors.append({"factor": x["claim"], "effect": "down", "note": x.get("detail", "")})
        if not factors:
            factors.append({"factor": "Thin evidence", "effect": "neutral",
                            "note": "little for or against on public data."})

        # Show the reasoning as plain steps (even the rule-based path is transparent).
        reasoning = []
        for x in supporting[:3]:
            reasoning.append({"step": f"In favour: {x['claim'].lower()}.", "sources": x.get("sources", [])})
        for x in contradicting[:3]:
            reasoning.append({"step": f"Against: {x['claim'].lower()}.", "sources": x.get("sources", [])})
        reasoning.append({"step": f"Weighing it up, the signals net out to {score}/100, "
                                  f"so the call is “{verdict}.”", "sources": []})

        if depth != "deep":  # quick read: trim to essentials
            opportunity = []
            reasoning = reasoning[:3]
            supporting, contradicting = supporting[:2], contradicting[:2]

        return {
            "verdict": verdict,
            "depth": depth,
            "confidenceFactors": factors[:5],
            "reasoningSteps": reasoning,
            "recommendation": f"Public evidence suggests {entity.get('name')} rates “{verdict}” "
                              f"for aging/longevity ({score}/100 on current public data). "
                              f"[Heuristic — set ANTHROPIC_API_KEY for a reasoned Claude brief.]",
            "confidence": score,
            "confidenceRationale": "Rule-based score from source signals; enable a Claude API "
                                   "key for a reasoned, calibrated brief.",
            "summary": f"Deterministic baseline assessment of {entity.get('name')} "
                       f"({kind}) against aging/longevity evidence.",
            "opportunityRanking": opportunity,
            "supporting": supporting,
            "contradicting": contradicting,
            "missing": missing,
            "longevityAngle": "Mapped to age-related diseases via matched associations/indications.",
            "engine": "heuristic",
        }


def build_reasoner(config: Config = CONFIG) -> Reasoner:
    """Claude when a key is present, otherwise the transparent heuristic."""
    if config.anthropic_api_key:
        return ClaudeReasoner(config)
    return HeuristicReasoner()


# ---------------------------------------------------------------------------
class Agent:
    def __init__(self, config: Config = CONFIG, reasoner: Reasoner | None = None):
        self.config = config
        self.resolver = EntityResolver()
        self.investigator = Investigator()
        self.reasoner = reasoner or build_reasoner(config)

    def investigate(self, query: str, emit: Emit = _noop, *, forced_entity: dict | None = None,
                    depth: str = "quick") -> dict:
        # Human-in-the-loop: if the user confirmed/overrode which entity to study,
        # honour their pick instead of re-resolving the free text.
        if forced_entity and forced_entity.get("id") and forced_entity.get("kind"):
            entity = ResolvedEntity(
                kind=forced_entity["kind"],
                id=forced_entity["id"],
                name=forced_entity.get("name") or query,
                query=query,
                note=forced_entity.get("note"),
            )
        else:
            emit({"type": "status", "message": f"Resolving “{query}”…"})
            entity = self.resolver.resolve(query)
        if entity is None:
            emit({"type": "error", "message": f"Could not resolve “{query}”."})
            return {"query": query, "error": "unresolved"}

        emit({"type": "resolved", "entity": entity.as_dict()})

        # (1) Plan the sub-questions (streamed to the UI). Quick read uses the
        # free rule-based plan; the deep dive spends a Claude call on planning.
        if depth == "deep":
            try:
                plan = self.reasoner.plan(entity.as_dict())
            except Exception as exc:
                emit({"type": "status", "message": f"Planner unavailable ({exc}); using default plan."})
                plan = HeuristicReasoner().plan(entity.as_dict())
        else:
            plan = HeuristicReasoner().plan(entity.as_dict())
        emit({"type": "plan", "plan": plan})

        # (2) Gather evidence from the sources (each emits start/done).
        emit({"type": "status", "message": "Querying public databases…"})
        bundle = self.investigator.gather(entity, emit)

        # (3-5) Reconcile, score, write the brief. If the Claude brain fails
        # (e.g. an unparseable reply), fall back to the heuristic so the user
        # always gets a brief rather than a dead end.
        emit({"type": "status", "message": "Reasoning over the evidence…"})
        try:
            analysis = self.reasoner.analyze(entity.as_dict(), bundle, depth=depth)
        except Exception as exc:
            emit({"type": "status",
                  "message": f"Claude analysis failed ({exc}); using rule-based fallback."})
            analysis = HeuristicReasoner().analyze(entity.as_dict(), bundle, depth=depth)

        brief = {
            "query": query,
            "entity": entity.as_dict(),
            "plan": plan,
            "analysis": analysis,
            "evidence": bundle,
            "sourceIndex": bundle.get("sourceIndex", {}),
            "engine": analysis.get("engine", self.reasoner.engine),
            "depth": depth,
            "generatedAt": _now(),
        }
        emit({"type": "brief", "brief": brief})
        return brief
