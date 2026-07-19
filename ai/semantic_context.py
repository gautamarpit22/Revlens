"""Semantic context builder: dbt manifest -> LLM-ready schema context.

The copilot NEVER sees raw tables or invents joins. Its entire world is the GOLD layer
(marts) as documented in dbt: model descriptions, column descriptions, and curated
metric definitions. This is why Phase 2's "docs are load-bearing" rule existed.

Output: a compact context block injected into every copilot prompt.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dbt" / "revlens" / "target" / "manifest.json"

# Only these models are queryable by the copilot (the semantic layer surface).
ALLOWED_MODELS = ["fct_events", "dim_accounts", "fct_mrr_monthly", "fct_ndr", "fct_revenue_attribution"]

# Curated metric definitions — the copilot's business glossary.
METRICS = """
METRIC DEFINITIONS (authoritative — always use these formulas):
- MRR: sum(mrr) from fct_mrr_monthly for a given invoice_month.
- NDR (Net Dollar Retention): use fct_ndr.ndr directly; NEVER recompute it.
- Churned accounts in month M: fct_ndr.churned_accounts for that month.
- Signup->paid conversion by channel: fct_revenue_attribution.signup_to_paid_rate.
- "Paying account": an account with at least one row in fct_mrr_monthly.
- Months are month-start dates (invoice_month). "Last month" = max(invoice_month).
"""


def build_context() -> str:
    import duckdb
    manifest = json.loads(MANIFEST.read_text())
    doc_cols = {}   # model -> {col: description}
    doc_model = {}  # model -> description
    for node in manifest["nodes"].values():
        if node.get("resource_type") == "model" and node["name"] in ALLOWED_MODELS:
            doc_model[node["name"]] = (node.get("description") or "").strip()
            doc_cols[node["name"]] = {c: (m.get("description") or "").strip()
                                      for c, m in node.get("columns", {}).items()}
    # Live schema gives the FULL column list + types; docs add meaning where present.
    con = duckdb.connect(str(ROOT / "revlens.duckdb"), read_only=True)
    lines = ["SEMANTIC LAYER — the ONLY tables you may query (schema: main):", ""]
    for model in ALLOWED_MODELS:
        lines.append(f"TABLE main.{model}: {doc_model.get(model, '')}")
        for col, ctype in con.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='main' and table_name=? order by ordinal_position", [model]
        ).fetchall():
            desc = doc_cols.get(model, {}).get(col, "")
            lines.append(f"  - {col} ({ctype})" + (f": {desc}" if desc else ""))
        lines.append("")
    con.close()
    lines.append(METRICS)
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_context())
