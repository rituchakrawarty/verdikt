# Verdikt — the Evidence-to-Decision Engine

**Type in one thing — a drug, a gene, or a disease linked to aging — and Verdikt reads five
public science databases, shows its work step by step, and answers three questions:
*Is this worth pursuing? How sure can we be? What do we still not know?* — with a link behind
every claim.**

It’s built for **aging & longevity** research triage. Its whole personality is honesty: instead
of sounding confident, it deliberately hunts for where the evidence *disagrees* and gives a
**calibrated confidence score** you can trust.

> ⚠️ **For research triage only — not medical advice, and not a final decision.** Verdikt reasons
> only from public data; it cannot see internal PK, toxicity, patents, or commercial data.

No vector DB, no embeddings, no RAG, no fine-tuning, no GPU. Just five free APIs and Claude as
the reasoning engine.

---

## The problem — validated

![The problem, validated: only 6 of 53 landmark preclinical cancer studies could be independently reproduced when Amgen tried, and >70% of 1,576 surveyed scientists have failed to reproduce another researcher's results — while the cost of getting it wrong is 37M+ papers to sift, ~67 weeks per systematic review, a 3.4% oncology approval rate, and ~$2.6B per approved drug.](docs/problem.png)

**Drug discovery doesn't fail for lack of data. It fails on *which evidence to trust*.** Before a
single go/no-go call — a decision that costs billions and takes years — a team spends weeks
manually triangulating trials, papers, FDA labels, and databases, and the evidence underneath them
is uneven. Every part of that pain is documented — and every number below links to its source:

| The reality | What the evidence shows |
|---|---|
| **Published evidence is often unreliable** | Amgen could independently reproduce only **6 of 53** landmark preclinical cancer studies.¹ In a survey of 1,576 scientists, **>70%** had failed to reproduce another researcher's results.² |
| **There is far too much of it** | PubMed indexes **>37 million** papers and grows by **~1.5 million/year** (~4,000/day).³ |
| **Vetting it by hand is slow** | A biomedical systematic review takes a **mean of ~67 weeks** to complete.⁴ |
| **The stakes are enormous** | Just **3.4%** of oncology drugs entering clinical trials reach approval (13.8% across all areas),⁵ at **~$2.6 billion** per approved drug.⁶ |
| **Good tooling is locked away** | Proprietary evidence-intelligence platforms run from **~$30k–$80k+/year** (GlobalData) to **six figures/year** (Clarivate Cortellis) — real money that prices out small and mid-size teams.⁷ |

**Verdikt is the decision-intelligence layer between that evidence and a billion-dollar bet.** It
reconciles agreeing-vs-conflicting evidence, traces every claim to its source, and stays
low-confidence when the evidence is thin — instead of hallucinating certainty.

> **Market.** AI in drug discovery was **~$1.7B in 2024**, projected to **~$8.5B by 2030** at
> **~30% CAGR**⁸ — the tooling layer around a global pharma R&D spend measured in hundreds of
> billions per year.

<sub>
¹ [Begley & Ellis, *Nature* 483:531 (2012)](https://www.nature.com/articles/483531a) ·
² [Baker, *Nature* 533:452 (2016)](https://www.nature.com/articles/533452a) ·
³ [PubMed / NLM (2024)](https://www.nlm.nih.gov/oet/ed/pubmed/06-24_oh-pubmed.html) ·
⁴ [Borah et al., *BMJ Open* 7:e012545 (2017)](https://pubmed.ncbi.nlm.nih.gov/28242767/) ·
⁵ [Wong, Siah & Lo, *Biostatistics* 20:273 (2019)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6409418/) ·
⁶ [DiMasi et al., Tufts CSDD / *J. Health Economics* (2016)](https://pubmed.ncbi.nlm.nih.gov/26928437/) ·
⁷ [Pharma market-intelligence pricing overview](https://intuitionlabs.ai/articles/pharmaceutical-market-intelligence-providers) ·
⁸ [AI-in-drug-discovery market sizing (Arizton / Research & Markets)](https://www.arizton.com/market-reports/ai-in-drug-discovery-market)
</sub>

---

## What it looks like

![Verdikt turns one input — metformin — into a confidence-scored, source-cited decision brief: a 62/100 "Explore" verdict, an Evidence → Reasoning → Decision pipeline, and side-by-side "what supports it" vs. "what works against it" panels.](docs/screenshot.png)

- **One search bar.** Type `metformin`, press enter.
- **Confirm step (human in the loop).** Verdikt shows what it thinks you mean (`metformin` → the
  drug) with alternatives, so the answer is about the right thing.
- **A live pipeline.** Watch the work happen: **Evidence → Reasoning → Decision**, each source
  lighting up as it’s queried.
- **A calm, transparent brief.** A big color-coded confidence dial, a plain-English verdict
  (*Pursue / Explore / Partner / Pause / Kill* — each shown with its meaning), a **“Why the score
  is 58/100”** panel showing what pushes it up ↑ and down ↓, and reasoning steps you can **tap to
  open** and see the exact evidence behind each one.
- **Two tiers.** Every search gives a fast, cheap **First look**. When a candidate looks worth it,
  one click runs **Full due diligence** — deeper reasoning plus a ranked list of the best
  age-related indications. Results are cached, so a repeat is instant and ~free.

---

## Quickstart

```bash
# 1. Install
pip install -r requirements.txt

# 2. Add your Claude key (get one at https://console.anthropic.com)
cp .env.example .env
#   then edit .env and paste your key after ANTHROPIC_API_KEY=

# 3. Run
python -m uvicorn verdikt.server:app --port 8123
#   open http://127.0.0.1:8123
```

Without a Claude key the app still runs on a transparent **rule-based fallback** (clearly labelled),
so you can try the whole UI first and add the key later for calibrated, reasoned briefs.

**Optional keys** (both sources work without them, just at lower rate limits): `NCBI_API_KEY`
(PubMed) and `OPENFDA_API_KEY` — add them to `.env` too.

### Command line / no server

```bash
python -m scripts.prove_metformin metformin   # or TP53, osteoarthritis, rapamycin, senolytics
python -m tests.test_answer_key               # scorecard vs a known answer key
```

---

## Deploy a live demo (shareable URL)

This is a Python web app, so it needs a host that runs Python — **GitHub Pages will not work**
(it only serves static files, and your Claude key must stay server-side).

**Render (free, ~5 minutes):**
1. Push this repo to GitHub (this repo includes a `render.yaml` Blueprint).
2. Go to [render.com](https://render.com) → **New → Blueprint** → select this repo.
3. When prompted, paste your `ANTHROPIC_API_KEY` (stored as a secret, never in the repo).
4. Deploy → you get a public URL like `https://verdikt.onrender.com`.

The free tier sleeps after inactivity, so the first visit after idle takes ~30s to wake.

**Hugging Face Spaces (free, good for AI demos):** this repo includes a `Dockerfile`.
Create a new **Space** → SDK **Docker** → add your files, then set `ANTHROPIC_API_KEY` under the
Space's **Settings → Secrets**. The app serves on port 7860 (handled by the Dockerfile).

> 💸 **Heads-up:** hosting is free, but every investigation spends Claude tokens on *your* key.
> Set a spending limit in the Anthropic console and share the link with people you trust.

**Quick temporary link (no deploy):** run it locally, then expose it with a tunnel —
`npx cloudflared tunnel --url http://localhost:8123` (or `ngrok http 8123`) — you'll get a public
URL that works while your machine is running it. Good for a quick demo.

---

## How a request flows

1. **Resolve** — free text → the right entity + ID via Open Targets’ `search` (longevity *classes*
   like “senolytics” map to a representative agent, with a note).
2. **Confirm** — you pick the exact entity (human in the loop).
3. **Gather** — five sources are queried; each streams *what it checked* and *what it found*.
4. **Reason** — Claude reconciles agreeing vs. conflicting evidence, assigns a **calibrated**
   confidence score (genetics > clinical > mechanism > association > literature; failed trials and
   boxed warnings penalized), and writes the brief in plain English — showing its steps.
5. **Decide** — you get the call, the caveats, and a “Your call” note that’s saved into the export
   (Markdown / print-to-PDF).

---

## Architecture

```
verdikt/
  config.py          Env/.env config; slots for ANTHROPIC / NCBI / openFDA keys
  cache.py           Tiny disk cache — repeats are near-free, identical answers
  sources/
    base.py          Thin UNIFORM client (session, retries, throttle, memory+disk cache)
    opentargets.py   Anchor source: target–disease scores, genetics, tractability, drugs
    clinicaltrials.py  Trials incl. a dedicated pass to capture whyStopped for failures
    chembl.py        Compounds, mechanisms, potency (filtered tightly by target + type)
    pubmed.py        Literature volume + top papers (NCBI E-utilities)
    openfda.py       Approved indications + boxed warnings
  resolver.py        Free text → ChEMBL/Ensembl/EFO IDs; longevity concept aliases
  longevity.py       Aging vocabulary + age-related-disease mapping
  investigator.py    Deterministically gathers evidence; streams purpose + finding per source
  prompts.py         The separate "brain": PLANNER + ANALYST prompts (quick & deep), strict JSON
  agent.py           Orchestrates resolve → plan → gather → reason → brief (Claude or heuristic)
  renderer.py        Brief → Markdown export
  server.py          FastAPI + SSE streaming; /api/resolve, /api/investigate, /api/export
frontend/
  index.html         Single-page app (no build step): search → confirm → live pipeline → brief
scripts/prove_metformin.py   End-to-end CLI proof
tests/test_answer_key.py     Scores output against metformin / rapamycin / senolytics
```

### The reasoning engine is pluggable
`agent.build_reasoner()` returns a Claude-powered reasoner when `ANTHROPIC_API_KEY` is set, else a
transparent heuristic. Both are engine-agnostic enough that the answer-key test passes either way.

### Deployment: one engine, pluggable sources
Verdikt separates *how evidence is gathered* from *how it's judged*. Every source is a `BaseSource`
([sources/base.py](verdikt/sources/base.py)) behind a uniform interface, so the transport is a
swappable seam:

- **Standalone (this repo).** The five sources are queried over their public REST/GraphQL APIs, so
  Verdikt runs anywhere with internet + a key — the web app, a container, a plain script, or a
  Claude/Cowork skill ([SKILL.md](SKILL.md)). No host runtime required.
- **Inside a connector host (e.g. Claude Science).** The same engine is *designed to* source that
  evidence through the host's own database connectors instead of its own REST calls — no duplicate
  fetching — because only the source adapter changes; the five-tier rubric and calibrated scoring
  stay identical. *(This `McpSources` adapter is on the roadmap, not yet wired in.)*

The reasoning is the product; the fetch layer is an implementation detail you can point wherever the
evidence lives. The REST clients also encode *what* to ask each source (association scores, pChEMBL,
`whyStopped` on failed trials), so that domain logic is reused regardless of transport.

---

## Domain note: “aging” isn’t one disease
The databases don’t model “aging” directly, so Verdikt maps longevity targets/drugs to the
**age-related diseases** they touch — osteoarthritis, pulmonary fibrosis, sarcopenia, Alzheimer’s,
metabolic disease — and reasons about those.

---

## FAQ

**Isn't re-fetching the five sources redundant inside Claude Science, which already has data connectors?**
Right instinct — and it's exactly why the source layer is a pluggable seam (see *Deployment* above).
Standalone, Verdikt fetches over public APIs so it runs anywhere; inside a connector host it's
*designed to* read through the host's connectors instead, with **no change to the rubric or scoring**.
The REST clients also encode *what* to ask each source, so that domain logic is reused either way.

**How is this different from asking ChatGPT/Claude to "review the literature"?**
A chat model answers from memory and can invent citations. Verdikt gathers a structured evidence
bundle from five databases *first*, then reasons **only** over it, and links every claim to a real
source id. It's evidence-grounded by construction, not by good intentions.

**Is it RAG? Does it use a vector database?**
No embeddings, no vector store. Evidence is retrieved by *structured* queries to each source's API
(IDs, scores, phases, counts) — not by semantic similarity — so the gathering is deterministic and
inspectable.

**How is the confidence score calibrated — is the weighting hard-coded?**
The five-tier evidence hierarchy and the 0–100 bands are an explicit rubric the model is *held to*
([prompts.py](verdikt/prompts.py)), and outputs are sanity-checked against a known answer key
([tests/test_answer_key.py](tests/test_answer_key.py)). It is **not** post-hoc statistical
calibration, and — in the Claude path — **not** a fixed numeric formula; the transparent additive
formula lives only in the no-key `HeuristicReasoner` fallback.

**Why aging & longevity specifically?**
"Aging" isn't one disease in these databases, so evidence quality varies wildly across longevity,
senescence, inflammation, and neurodegeneration — the domain where "which evidence to trust" bites
hardest. Verdikt maps targets/drugs to the concrete age-related diseases they touch and reasons about
those.

**What are the limits?**
Research triage only — **not medical advice, not a final decision.** Verdikt sees *public* data only;
it can't see internal PK/tox, patents, manufacturing, or commercial data, and it says so in the
"missing evidence" section. A fast, honest first read — not a verdict to act on blindly.

**Does it need an API key? What does it cost?**
It runs without a key on a clearly-labelled rule-based fallback. With a key, each investigation spends
Claude tokens — kept low by prompt caching, top-8 evidence sampling, and an evidence-keyed cache that
makes repeats near-free.

---

## Data sources
[Open Targets](https://platform.opentargets.org) ·
[ClinicalTrials.gov](https://clinicaltrials.gov) ·
[ChEMBL](https://www.ebi.ac.uk/chembl) ·
[PubMed / NCBI E-utilities](https://www.ncbi.nlm.nih.gov/home/develop/api/) ·
[openFDA](https://open.fda.gov). All free. Please respect their terms and rate limits.

## License
[MIT](LICENSE). Built with [Claude](https://www.anthropic.com/claude).
