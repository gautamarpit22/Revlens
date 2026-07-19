"""AI Data-Quality Triage Agent.

When dbt tests fail, this agent does the first 15 minutes of on-call work:
  1. Reads the failed test(s) from dbt's run_results.json
  2. Pulls context: the tested model's SQL + description, upstream lineage (manifest),
     sample rows from the affected model, dead-letter stats if relevant
  3. Asks an LLM for: root-cause hypothesis, severity, suggested next checks
  4. Writes a ready-to-file GitHub issue draft (markdown) to ai/triage_out/

The agent DIAGNOSES; it never fixes. No write access to models or data — its only
output is a markdown file a human reviews. (Same guardrail philosophy as the copilot:
AI proposes, human disposes.)

Usage:
  python ai/triage_agent.py                # triage latest dbt run (exits clean if all green)
  python ai/triage_agent.py --demo         # exercise the full path with a canned failure
  Backend: REVLENS_AI_BACKEND (ollama default; echo for CI plumbing)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from copilot import BACKENDS, log_telemetry

ROOT = Path(__file__).resolve().parents[1]
DBT_TARGET = ROOT / "dbt" / "revlens" / "target"
DB = os.environ.get("REVLENS_DB_PATH", str(ROOT / "revlens.duckdb"))
OUT_DIR = Path(__file__).parent / "triage_out"

DEMO_FAILURE = {
    "unique_id": "test.revlens.unique_int_identity__account_spine_account_id",
    "status": "fail",
    "failures": 6,
    "message": "Got 6 results, configured to fail if != 0",
    "depends_on_model": "int_identity__account_spine",
}


def load_failures(demo: bool):
    if demo:
        return [DEMO_FAILURE]
    rr = json.loads((DBT_TARGET / "run_results.json").read_text())
    out = []
    for r in rr["results"]:
        if r["status"] in ("fail", "error") and r["unique_id"].startswith("test."):
            model = ""
            for dep in r.get("depends_on", {}).get("nodes", []):
                if dep.startswith("model."):
                    model = dep.split(".")[-1]
            out.append({"unique_id": r["unique_id"], "status": r["status"],
                        "failures": r.get("failures"), "message": r.get("message") or "",
                        "depends_on_model": model})
    return out


def gather_context(model_name: str) -> str:
    manifest = json.loads((DBT_TARGET / "manifest.json").read_text())
    node = next((n for n in manifest["nodes"].values()
                 if n.get("resource_type") == "model" and n["name"] == model_name), None)
    if not node:
        return f"(model {model_name} not found in manifest)"
    upstream = [d.split(".")[-1] for d in node["depends_on"]["nodes"]]
    parts = [
        f"MODEL: {model_name}",
        f"DESCRIPTION: {node.get('description', '')}",
        f"UPSTREAM LINEAGE: {' <- '.join([model_name] + upstream)}",
        f"MODEL SQL:\n{node.get('raw_code', '')[:2500]}",
    ]
    try:
        con = duckdb.connect(DB, read_only=True)
        sample = con.execute(f"select * from main.{model_name} limit 5").fetchdf()
        parts.append(f"SAMPLE ROWS:\n{sample.to_string(index=False)[:1500]}")
        dl = con.execute("select failure_reason, count(*) n from main.stg_events_dead_letter "
                         "group by 1 order by 2 desc").fetchdf()
        parts.append(f"DEAD LETTER SUMMARY:\n{dl.to_string(index=False)}")
        con.close()
    except Exception as e:
        parts.append(f"(live queries unavailable: {str(e)[:120]})")
    return "\n\n".join(parts)


PROMPT = """You are a senior data engineer triaging a failed dbt test. Using ONLY the
context below, produce a GitHub issue in this exact markdown structure:

# [DQ] <one-line title>
## Severity
<critical|high|medium|low> — <one sentence: who/what is impacted downstream>
## Failure summary
<2-3 sentences: which test, which model, what the numbers say>
## Root-cause hypothesis (ranked)
1. <most likely — reference specific columns/joins/upstreams from the context>
2. <second>
## Suggested next checks
- <specific SQL or inspection step>
- <another>
## Blast radius
<which downstream marts/consumers are affected, from the lineage>

Do not invent columns or tables not present in the context. Be specific, not generic.

=== CONTEXT ===
FAILED TEST: {test_id}
STATUS: {status} | FAILING ROWS: {failures}
MESSAGE: {message}

{model_context}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--backend", default=None)
    args = ap.parse_args()
    backend = args.backend or os.environ.get("REVLENS_AI_BACKEND", "ollama")

    failures = load_failures(args.demo)
    if not failures:
        print("All dbt tests green — nothing to triage.")
        return

    OUT_DIR.mkdir(exist_ok=True)
    for f in failures:
        ctx = gather_context(f["depends_on_model"])
        prompt = PROMPT.format(test_id=f["unique_id"], status=f["status"],
                               failures=f["failures"], message=f["message"],
                               model_context=ctx)
        if backend == "echo":
            prompt += "\nECHO_SQL:# [DQ] demo issue draft (echo backend — plumbing test)"
        t0 = time.time()
        try:
            issue = BACKENDS[backend](prompt)
            ok, err = True, None
        except Exception as e:
            issue, ok, err = "", False, str(e)[:300]
        latency = int((time.time() - t0) * 1000)

        con = duckdb.connect(DB)
        log_telemetry(con, backend, f"triage:{backend}", f["unique_id"],
                      None, ok, err, latency, 0)
        con.close()

        if ok:
            out_path = OUT_DIR / f"{f['unique_id'].split('.')[-1]}.md"
            out_path.write_text(issue)
            print(f"Issue draft written: {out_path}")
            print("File it with:  gh issue create --title '<title from draft>' "
                  f"--body-file {out_path}")
        else:
            print(f"Triage failed for {f['unique_id']}: {err}")


if __name__ == "__main__":
    main()
