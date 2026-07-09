"""End-to-end proof for milestone 1.

Resolve free text -> ID with the resolver, then pull the full Open Targets
record and print a readable summary. Run:

    python -m scripts.prove_metformin            # metformin
    python -m scripts.prove_metformin TP53       # any target/drug/disease
"""
from __future__ import annotations

import sys

from verdikt.resolver import EntityResolver
from verdikt.sources.opentargets import OpenTargets


def line(char="─", n=64):
    print(char * n)


def show_drug(d: dict) -> None:
    print(f"DRUG  {d['name']}  ({d['id']})   {d['url']}")
    print(f"  type={d['drugType']}   max clinical stage={d['maxClinicalStage']}")
    if d["mechanisms"]:
        print("  Mechanisms of action:")
        for m in d["mechanisms"]:
            tgts = ", ".join(m["targets"][:6]) + (" …" if len(m["targets"]) > 6 else "")
            print(f"    • {m['mechanism']} [{m['actionType']}]  → {tgts}")
    print(f"  Indications on file: {d['indicationCount']}")
    for ind in d["indications"][:8]:
        ta = f"  ({', '.join(ind['therapeuticAreas'][:2])})" if ind["therapeuticAreas"] else ""
        print(f"    • phase {ind['maxPhase']}: {ind['disease']}{ta}")
    if d["warnings"]:
        print("  Safety / warnings:")
        for w in d["warnings"][:5]:
            print(f"    ! {w['type']}: {w['description']} ({w['year']})")


def show_target(t: dict) -> None:
    print(f"TARGET  {t['symbol']}  {t['name']}  ({t['id']})   {t['url']}")
    if t["tractability"]:
        buckets = ", ".join(f"{r['modality']}:{r['label']}" for r in t["tractability"][:6])
        print(f"  Tractability: {buckets}")
    print(f"  Associated diseases: {t['associationCount']} (top {len(t['associations'])} shown)")
    for a in t["associations"][:10]:
        dts = ", ".join(f"{k} {v:.2f}" for k, v in list(a["datatypes"].items())[:3])
        print(f"    • {a['score']:.3f}  {a['disease']}   [{dts}]")


def show_disease(d: dict) -> None:
    print(f"DISEASE  {d['name']}  ({d['id']})   {d['url']}")
    if d["therapeuticAreas"]:
        print(f"  Therapeutic areas: {', '.join(d['therapeuticAreas'])}")
    print(f"  Associated targets: {d['targetCount']} (top {len(d['topTargets'])} shown)")
    for t in d["topTargets"][:10]:
        print(f"    • {t['score']:.3f}  {t['symbol']}  {t['name']}")


def main() -> None:
    query = " ".join(sys.argv[1:]) or "metformin"
    ot = OpenTargets()
    resolver = EntityResolver(ot)

    line("═")
    print(f"QUERY: {query!r}")
    line("═")

    entity = resolver.resolve(query)
    if entity is None:
        print("Could not resolve that input to any Open Targets entity.")
        return

    print(f"Resolved → {entity.kind.upper()}  {entity.name}  ({entity.id})")
    if entity.alternatives:
        alts = ", ".join(f"{a['name']} [{a['kind']}]" for a in entity.alternatives[:4])
        print(f"  (other candidates: {alts})")
    line()

    if entity.kind == "drug":
        show_drug(ot.drug(entity.id))
    elif entity.kind == "target":
        show_target(ot.target(entity.id))
    elif entity.kind == "disease":
        show_disease(ot.disease(entity.id))
    else:
        print(f"Unsupported entity kind: {entity.kind}")

    line("═")
    print("✓ End-to-end Open Targets path works.")


if __name__ == "__main__":
    main()
