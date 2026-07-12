---
name: verdikt
description: Turn ONE input — a drug, gene, or disease linked to aging & longevity — into a transparent, confidence-scored decision brief with a source link behind every claim. Runs a real investigation across five live public biomedical databases (Open Targets, ClinicalTrials.gov, ChEMBL, PubMed, openFDA) and uses Claude to reconcile agreeing-vs-conflicting evidence and calibrate an honest confidence score. Use for longevity research triage, target/drug landscape reads, go/no-go evidence prep, or any "is this worth pursuing, how sure can we be, and what is still missing" question.
---

# Verdikt — the Evidence-to-Decision Engine (skill)

Give it **one** input — a drug, gene, or disease tied to aging — and Verdikt reads
five public science databases, shows its work, and answers three questions:
**Is this worth pursuing? How sure can we be? What do we still not know?** — with a
link behind every claim.

This skill drives the **same engine as the Verdikt web app** (real REST clients +
Claude reasoning). It does **not** use `host.mcp`, so it runs in any normal python
kernel that has internet and an `ANTHROPIC_API_KEY`. Web app, terminal, and skill
are three doors into one tested core.

> Research triage only — **not** medical advice, and **not** a final decision.
> Public data only: it cannot see internal PK, tox, patents, or commercial data.

## Prerequisites
- From the repo root: `pip install -r requirements.txt` (mainly `anthropic`, `requests`).
- Set `ANTHROPIC_API_KEY`. Without it the pipeline still runs on a clearly-labelled
  rule-based fallback, so the skill degrades gracefully.
- Optional keys for higher rate limits: `NCBI_API_KEY` (PubMed), `OPENFDA_API_KEY`.

## One-call usage (run from the repo root, in a python cell)
```python
from verdikt.skill import investigate, investigate_to_markdown

# Full brief as a dict:
brief = investigate("metformin")                     # quick first look
print(brief["analysis"]["verdict"], brief["analysis"]["confidence"], "/100")

# Deeper reasoning + an opportunity ranking, saved as Markdown:
md = investigate_to_markdown("rapamycin", depth="deep", out_path="brief.md")
```

`depth="quick"` = a fast, cheap first look. `depth="deep"` = deeper reasoning plus a
ranked list of the strongest age-related indications. Results are cached, so a repeat
is instant and near-free.

**The brief dict** contains: `entity` (what it resolved to), `analysis`
(`verdict` ∈ Pursue / Explore / Partner / Pause / Kill, `confidence` 0–100,
`supporting`, `contradicting`, `missing`, `reasoningSteps`), `evidence` (the raw
bundle + per-source `evidenceLog`), and `sourceIndex` (every clickable source).

## Command line (same engine, no server)
```bash
python -m verdikt.skill metformin            # prints the full brief as Markdown
python -m verdikt.skill "TP53" --deep --out=tp53.md
```

## What good output looks like (answer key)
metformin / rapamycin → a cautious, **non-"Kill"** verdict at modest confidence; a
thin input (e.g. a NAD+ booster) → a **visibly lower** confidence score. That honesty
is the whole point. Sanity-check the engine any time with:
```bash
python -m tests.test_answer_key
```

## How a run flows
1. **Resolve** free text → the right entity + ID (Open Targets `search`; longevity
   concepts like "senolytics" map to a representative agent, with a note).
2. **Gather** evidence from the five sources; each records what it checked and found.
3. **Reason** — Claude reconciles agreeing vs. conflicting evidence, penalises failed
   trials and boxed warnings, calibrates confidence, and writes the brief in plain English.
4. **Decide** — you get the call, the caveats, and every claim linked to its source.
