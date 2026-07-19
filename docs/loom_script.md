# Loom Demo Script (5 min)

**0:00–0:30 — Hook.** "This is RevLens: a click on a website to a dollar on an invoice,
fully traceable. Three source systems, one governed platform, plus an AI copilot whose
accuracy I can prove." Show README architecture diagram.

**0:30–1:30 — The problem + lineage.** Dagster UI, Lineage tab, full green graph.
"Product events, CRM, billing — separate identities. This graph is the pipeline that
stitches them: bronze per-source assets, dbt silver and gold." Zoom identity models.

**1:30–2:15 — Closed loop.** Terminal: query fct_revenue_attribution.
"Google: 139 signups, 32% conversion, $49.9K — only possible because 12.8K pre-signup
anonymous events were retroactively stitched."

**2:15–3:00 — Reliability.** Restart Dagster with REVLENS_CHAOS=1, materialize:
CRM asset fails red, events/billing stay green. "Failure isolation + exact blast radius.
And 37 dbt tests gate every run — they caught 3 real bugs during the build."

**3:00–4:15 — AI copilot + evals.** `python ai/copilot.py "Which channel has the best
conversion rate?"` — show SQL + answer. Then run_evals.py output. "15-question golden set,
result-equivalence grading. Journey: 47% baseline to 80% — via telemetry-driven failure
analysis, a grader fix, and one key finding: two independent models failed identically,
so I moved metric semantics into the dbt docs instead of stacking prompt rules.
Guardrails: SELECT-only, marts-only, read-only connection — DDL attempts get blocked."

**4:15–5:00 — Triage agent + close.** `python ai/triage_agent.py --demo`, open the issue
draft. "On-call's first 15 minutes, automated — diagnosis only, humans decide.
Everything here is open source, $0 infra, warehouse-agnostic. Repo linked below."
