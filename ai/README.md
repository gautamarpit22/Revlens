# Chat with RevLens — NL->SQL Copilot

Ask business questions in English; get answers from the governed semantic layer.

## Architecture
question -> [semantic context from dbt docs] -> LLM -> SQL
        -> GUARDRAILS (SELECT-only, marts-only whitelist, auto-LIMIT, sqlglot-parsed)
        -> read-only DuckDB execution -> answer
        -> everything logged to main.ai_telemetry

## Backends (env: REVLENS_AI_BACKEND)
- `ollama` (default, free): needs Ollama running locally — `ollama pull llama3.1:8b`
- `anthropic`: needs ANTHROPIC_API_KEY; used for final eval scoring (~$0.10/run with Haiku)
- `echo`: CI plumbing backend — no model; harness feeds ground-truth SQL through the
  full pipeline. Must always score 100%; anything less = pipeline bug, not model error.

## Usage
```bash
python ai/copilot.py "Which channel has the best conversion rate?"
python ai/run_evals.py --backend echo       # pipeline health (CI)
python ai/run_evals.py                      # real score with Ollama
python ai/run_evals.py --backend anthropic  # headline score for README
```

## Eval methodology
15 golden questions in evals/golden_set.jsonl. Grading is RESULT equivalence
(both SQLs execute; normalized results compared) — different-but-correct SQL passes,
plausible-but-wrong fails. Accuracy gate in CI: >=60% or the run fails.

## Guardrails (tested in ai/test_guardrails — 7/7)
DDL/DML blocked · raw/staging tables blocked · multi-statement blocked ·
CTEs allowed · auto LIMIT 1000 · read-only connection as defense-in-depth.
