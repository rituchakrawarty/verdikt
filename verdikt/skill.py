"""Verdikt as a Claude skill (and a full-brief CLI).

Same engine as the web app: real public-API source clients + Claude as the
reasoning brain. This module does NOT use the Claude Science `host.mcp`/`host.llm`
runtime -- it drives the exact, tested `Agent.investigate()` code the deployed
app uses, so a Claude/Cowork skill, a terminal, or a plain script all produce
the identical brief. All it needs is Python, internet, and (ideally) an
`ANTHROPIC_API_KEY`; without a key it degrades to the labelled heuristic brain.

Two front doors, one engine:

    # In a Python / Cowork skill cell (from the repo root):
    from verdikt.skill import investigate, investigate_to_markdown
    brief = investigate("metformin")                 # -> full brief dict
    md    = investigate_to_markdown("rapamycin", depth="deep", out_path="brief.md")

    # From a terminal (no server):
    python -m verdikt.skill metformin
    python -m verdikt.skill "TP53" --deep --out=tp53.md
"""
from __future__ import annotations

import sys

from .agent import Agent
from .renderer import brief_to_markdown


def investigate(query: str, depth: str = "quick", *, forced_entity: dict | None = None) -> dict:
    """Run one investigation and return the full brief dict.

    `depth="quick"` is a fast, cheap first look; `depth="deep"` spends more
    reasoning and adds an opportunity ranking of the strongest age-related
    indications. `forced_entity` (optional) honours a human-confirmed entity
    pick instead of re-resolving the free text.
    """
    return Agent().investigate(query, depth=depth, forced_entity=forced_entity)


def investigate_to_markdown(query: str, depth: str = "quick", out_path: str | None = None) -> str:
    """Run one investigation and return the brief as Markdown (optionally saved).

    Handy for the CLI, for exports, and for dropping a readable brief straight
    into a chat / document from a skill.
    """
    brief = investigate(query, depth=depth)
    if brief.get("error"):
        md = (f"# Verdikt\n\nCould not resolve “{query}” to a biomedical entity. "
              f"Try a drug, gene, or disease name (e.g. metformin, TP53, osteoarthritis).")
    else:
        md = brief_to_markdown(brief)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(md)
    return md


def _main(argv: list[str]) -> int:
    depth = "deep" if "--deep" in argv else "quick"
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--out=")), None)
    terms = [a for a in argv if not a.startswith("-")]
    query = " ".join(terms) or "metformin"
    md = investigate_to_markdown(query, depth=depth, out_path=out)
    print(md)
    if out:
        print(f"\n[saved to {out}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
