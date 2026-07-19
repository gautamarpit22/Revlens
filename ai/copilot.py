"""Chat with RevLens: NL -> governed SQL -> answer, with production guardrails.

Pipeline per question:
  1. Build prompt = semantic context (dbt docs) + question
  2. LLM generates SQL (backend pluggable: ollama | anthropic | echo)
  3. GUARDRAILS validate the SQL (hard gate, not a suggestion):
       - must parse as a single SELECT (sqlglot)  -> no DML/DDL ever
       - may reference ONLY allowed mart tables   -> no raw/staging/PII surface
       - LIMIT 1000 auto-applied if absent        -> no runaway scans
  4. Execute on a READ-ONLY DuckDB connection (defense in depth: even if a
     guardrail missed something, the connection cannot write)
  5. Log everything to main.ai_telemetry (latency, success, sql, backend)

Usage:
  python ai/copilot.py "What was total MRR last month?"
  REVLENS_AI_BACKEND=ollama  (default) | anthropic | echo
"""

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import duckdb
import sqlglot
from sqlglot import exp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from semantic_context import ALLOWED_MODELS, build_context

ROOT = Path(__file__).resolve().parents[1]
DB = os.environ.get("REVLENS_DB_PATH", str(ROOT / "revlens.duckdb"))

SYSTEM = """You translate business questions into DuckDB SQL over the semantic layer below.
Rules:
- Output ONLY the SQL, no explanation, no markdown fences.
- Single SELECT statement; query ONLY the listed tables (schema `main`).
- Column descriptions and METRIC DEFINITIONS below are authoritative: if a column or
  formula there answers the question, use it exactly; otherwise compute with aggregates.
- Return only the columns needed to answer (grouping columns included when grouping).
"""


# ---------------- Backends ----------------

def llm_ollama(prompt: str, model: str = None) -> str:
    model = model or os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps({"model": model, "prompt": prompt, "stream": False,
                         "options": {"temperature": 0}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["response"]


def llm_anthropic(prompt: str, model: str = None) -> str:
    model = model or "claude-haiku-4-5-20251001"
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": model, "max_tokens": 500,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Content-Type": "application/json",
                 "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["content"][0]["text"]


def llm_echo(prompt: str, model: str = None) -> str:
    """CI/plumbing backend: expects the SQL to be embedded in the prompt after ECHO_SQL:.
    Used by the eval harness to test the pipeline without any model. Not a real backend."""
    m = re.search(r"ECHO_SQL:(.*)$", prompt, re.S)
    return m.group(1).strip() if m else "SELECT 1"


BACKENDS = {"ollama": llm_ollama, "anthropic": llm_anthropic, "echo": llm_echo}


# ---------------- Guardrails ----------------

class GuardrailViolation(Exception):
    pass


def clean_sql(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^```(sql)?\s*|\s*```$", "", s, flags=re.I | re.M).strip()
    return s.rstrip(";")


def validate_sql(sql: str) -> str:
    try:
        statements = sqlglot.parse(sql, dialect="duckdb")
    except Exception as e:
        raise GuardrailViolation(f"SQL does not parse: {e}")
    if len(statements) != 1:
        raise GuardrailViolation("Exactly one statement allowed")
    stmt = statements[0]
    if not isinstance(stmt, exp.Select) and not (
        isinstance(stmt, exp.With) and isinstance(stmt.this, exp.Select)
    ):
        raise GuardrailViolation("Only SELECT statements are allowed")
    # CTE names are legal to reference; everything else must be an allowed mart.
    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    for table in stmt.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names:
            continue
        if name not in [m.lower() for m in ALLOWED_MODELS]:
            raise GuardrailViolation(f"Table '{name}' is outside the semantic layer")
    # Auto-limit
    if not stmt.args.get("limit"):
        sql = f"{sql}\nLIMIT 1000"
    return sql


# ---------------- Telemetry ----------------

def log_telemetry(con, backend, model, question, sql, success, error, latency_ms, rows):
    con.execute("""CREATE TABLE IF NOT EXISTS main.ai_telemetry (
        ts TIMESTAMPTZ, backend VARCHAR, model VARCHAR, question VARCHAR,
        generated_sql VARCHAR, success BOOLEAN, error VARCHAR,
        latency_ms INTEGER, rows_returned INTEGER)""")
    con.execute("INSERT INTO main.ai_telemetry VALUES (current_timestamp,?,?,?,?,?,?,?,?)",
                [backend, model, question, sql, success, error, latency_ms, rows])


# ---------------- Main ask() ----------------

def ask(question: str, backend: str = None, echo_sql: str = None):
    backend = backend or os.environ.get("REVLENS_AI_BACKEND", "ollama")
    prompt = f"{SYSTEM}\n{build_context()}\nQuestion: {question}\nSQL:"
    if backend == "echo" and echo_sql:
        prompt += f"\nECHO_SQL:{echo_sql}"

    t0 = time.time()
    sql, error, rows_df, ro = None, None, None, None
    try:
        sql = validate_sql(clean_sql(BACKENDS[backend](prompt)))
        # Query runs on a READ-ONLY connection. NOTE: connections are strictly
        # sequential (open->use->close) — DuckDB forbids mixed-config connections
        # to one file in the same process (single-writer engine).
        ro = duckdb.connect(DB, read_only=True)
        rows_df = ro.execute(sql).fetchdf()
        success = True
    except Exception as e:
        error, success = str(e)[:300], False
    finally:
        try:
            ro.close()  # ALWAYS close, even on failure
        except Exception:
            pass
    latency = int((time.time() - t0) * 1000)
    rw = duckdb.connect(DB)  # telemetry write, opened only after ro is closed
    log_telemetry(rw, backend, os.environ.get("OLLAMA_MODEL", backend), question,
                  sql, success, error, latency, len(rows_df) if rows_df is not None else 0)
    rw.close()
    return {"success": success, "sql": sql, "error": error,
            "latency_ms": latency, "result": rows_df}


if __name__ == "__main__":
    out = ask(" ".join(sys.argv[1:]) or "What was total MRR last month?")
    print("SQL:\n", out["sql"], "\n")
    print(out["result"] if out["success"] else f"BLOCKED/FAILED: {out['error']}")
