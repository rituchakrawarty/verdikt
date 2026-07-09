"""Answer-key scoring test.

Runs the full pipeline on three canonical longevity inputs — metformin,
rapamycin, and senolytics — and scores each brief against a curated answer key
of things a correct investigation MUST get right (resolution, directional
verdict, key signals, source coverage, structure).

These checks are engine-agnostic: they hold for both the Claude brain and the
heuristic fallback, so the suite is meaningful even without an API key.

Run standalone (prints a scorecard):
    python -m tests.test_answer_key
Or under pytest:
    pytest tests/test_answer_key.py -v
"""
from __future__ import annotations

from verdikt.agent import Agent

# The build-guide recommendation verbs.
VALID_VERDICTS = {"Pursue", "Explore", "Partner", "Pause", "Kill"}

# The known answer key. These three are all serious, evidence-backed longevity
# candidates, so a correct investigation should never "Kill" them outright — but
# it also should not blindly "Pursue" (the honest, conservative behaviour the
# build guide is all about).
ANSWER_KEY = {
    "metformin": {
        "kind": "drug",
        "id": "CHEMBL1431",
        "notVerdict": "Kill",
        "signals": {"approved": True},
        "ageRelated": True,
    },
    "rapamycin": {
        "kind": "drug",
        "id": "CHEMBL413",  # sirolimus
        "notVerdict": "Kill",
        "signals": {"approved": True},
        # rapamycin is the canonical mTOR inhibitor; mTOR must show up somewhere.
        "mentions": ["mtor", "sirolimus"],
    },
    "senolytics": {
        "kind": "drug",
        "viaAlias": True,            # resolves through the concept-alias map
        "representative": "DASATINIB",
        "notVerdict": "Kill",
    },
}

PASS_THRESHOLD = 0.80  # fraction of points required to pass


def _mentions_anywhere(brief: dict, needles: list[str]) -> bool:
    import json

    blob = json.dumps(brief, default=str).lower()
    return any(n.lower() in blob for n in needles)


def score_case(query: str, key: dict, brief: dict) -> tuple[int, int, list[str]]:
    """Return (points, max_points, notes) for one investigation."""
    checks: list[tuple[str, bool]] = []
    entity = brief.get("entity", {})
    analysis = brief.get("analysis", {})
    signals = brief.get("evidence", {}).get("signals", {})

    # 1. Entity kind resolved correctly.
    checks.append(("resolved kind == %s" % key["kind"], entity.get("kind") == key["kind"]))

    # 2. Canonical ID (or representative, for alias concepts).
    if key.get("viaAlias"):
        checks.append(("alias note present", bool(entity.get("note"))))
        checks.append(
            ("representative == %s" % key["representative"],
             (entity.get("name") or "").upper() == key["representative"]),
        )
    else:
        checks.append(("id == %s" % key["id"], entity.get("id") == key["id"]))

    # 3. Verdict is a valid build-guide verb and not the disallowed one.
    verdict = analysis.get("verdict")
    checks.append(("verdict is a valid verb (got %s)" % verdict, verdict in VALID_VERDICTS))
    checks.append(("verdict != %s" % key["notVerdict"], verdict != key["notVerdict"]))

    # 4. Confidence is a sane integer in range.
    conf = analysis.get("confidence")
    checks.append(("confidence in 0..100", isinstance(conf, int) and 0 <= conf <= 100))

    # 5. Expected signals.
    for sig, want in key.get("signals", {}).items():
        checks.append(("signal %s == %s" % (sig, want), signals.get(sig) == want))

    # 6. Age-related mapping present.
    if key.get("ageRelated"):
        has_aging = bool(signals.get("ageRelatedIndications") or signals.get("ageRelatedAssociations"))
        checks.append(("maps to age-related disease", has_aging))

    # 7. Required mentions anywhere in the brief.
    if key.get("mentions"):
        checks.append(("mentions %s" % key["mentions"], _mentions_anywhere(brief, key["mentions"])))

    # 8. Source coverage — at least 4 of 5 sources contributed.
    checks.append((">=4 sources queried", len(brief.get("sourceIndex", {})) >= 4))

    # 9. Structural completeness of the brief.
    checks.append(("has recommendation", bool(analysis.get("recommendation"))))
    checks.append(("has supporting evidence", len(analysis.get("supporting", [])) >= 1))
    checks.append(("every evidence item cites a source",
                   all(it.get("sources") for it in analysis.get("supporting", []))))

    points = sum(1 for _, ok in checks if ok)
    notes = ["%s %s" % ("✓" if ok else "✗", label) for label, ok in checks]
    return points, len(checks), notes


def run_scorecard() -> dict:
    agent = Agent()
    results = {}
    total_pts = total_max = 0
    for query, key in ANSWER_KEY.items():
        brief = agent.investigate(query)
        pts, mx, notes = score_case(query, key, brief)
        results[query] = {
            "points": pts, "max": mx, "pct": pts / mx,
            "verdict": brief.get("analysis", {}).get("verdict"),
            "confidence": brief.get("analysis", {}).get("confidence"),
            "notes": notes,
        }
        total_pts += pts
        total_max += mx
    results["_overall"] = {"points": total_pts, "max": total_max, "pct": total_pts / total_max}
    return results


# -- pytest entry point -------------------------------------------------------
def test_answer_key():
    results = run_scorecard()
    for query, r in results.items():
        if query == "_overall":
            continue
        assert r["pct"] >= PASS_THRESHOLD, (
            f"{query} scored {r['pct']:.0%}\n  " + "\n  ".join(r["notes"])
        )
    assert results["_overall"]["pct"] >= PASS_THRESHOLD


if __name__ == "__main__":
    res = run_scorecard()
    print("\n" + "═" * 62)
    print("  VERDIKT — ANSWER-KEY SCORECARD")
    print("═" * 62)
    for query, r in res.items():
        if query == "_overall":
            continue
        mark = "PASS" if r["pct"] >= PASS_THRESHOLD else "FAIL"
        print(f"\n▶ {query.upper():14} {r['points']}/{r['max']}  ({r['pct']:.0%})  "
              f"[{mark}]  verdict={r['verdict']} conf={r['confidence']}")
        for n in r["notes"]:
            print("     " + n)
    ov = res["_overall"]
    print("\n" + "─" * 62)
    verdict = "PASS ✓" if ov["pct"] >= PASS_THRESHOLD else "FAIL ✗"
    print(f"  OVERALL: {ov['points']}/{ov['max']}  ({ov['pct']:.0%})  →  {verdict}")
    print("═" * 62)
