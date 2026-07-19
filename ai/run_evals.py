"""Eval harness: run every golden question through the copilot, grade against ground truth.

Grading = RESULT equivalence, not SQL string match: the model's SQL and the truth SQL
both execute; results are normalized (rounded, sorted, column names ignored) and compared.
Different-but-correct SQL passes; plausible-but-wrong SQL fails. This is the number that
goes in the README.

Usage:
  python ai/run_evals.py                       # backend from REVLENS_AI_BACKEND (default ollama)
  python ai/run_evals.py --backend echo        # plumbing test (uses truth SQL; must score 100%)
  python ai/run_evals.py --backend anthropic   # final scoring run (needs ANTHROPIC_API_KEY)
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from copilot import ask, DB

GOLDEN = Path(__file__).parent / "evals" / "golden_set.jsonl"


def normalize(df):
    if df is None:
        return None
    out = df.copy()
    for c in out.columns:
        if out[c].dtype.kind == "f":
            out[c] = out[c].round(2)
    out.columns = range(len(out.columns))
    vals = [tuple(str(v) for v in row) for row in out.itertuples(index=False)]
    return sorted(vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=None)
    args = ap.parse_args()

    items = [json.loads(l) for l in open(GOLDEN)]
    passed, failed = [], []
    for it in items:
        con = duckdb.connect(DB, read_only=True)
        truth = normalize(con.execute(it["truth_sql"]).fetchdf())
        con.close()  # must close before ask() opens its own connections
        out = ask(it["question"], backend=args.backend, echo_sql=it["truth_sql"])
        got = normalize(out["result"]) if out["success"] else None
        def subset_match(truth_rows, got_rows):
            if truth_rows is None or got_rows is None: return False
            if len(truth_rows) != len(got_rows): return False
            n_t = len(truth_rows[0]) if truth_rows else 0
            n_g = len(got_rows[0]) if got_rows else 0
            if n_t > n_g: return False
            from itertools import permutations, combinations
            for cols in combinations(range(n_g), n_t):
                for perm in permutations(cols):
                    proj = sorted(tuple(r[i] for i in perm) for r in got_rows)
                    if proj == truth_rows: return True
            return False
        ok = out["success"] and (got == truth or subset_match(truth, got))
        (passed if ok else failed).append(it["id"])
        status = "PASS" if ok else f"FAIL ({out['error'] or 'wrong result'})"
        print(f"[{status[:60]:<60}] {it['id']}")
    acc = len(passed) / len(items)
    print(f"\nAccuracy: {len(passed)}/{len(items)} = {acc:.0%}")
    if failed:
        print("Failed:", ", ".join(failed))
    sys.exit(0 if acc >= 0.6 else 1)


if __name__ == "__main__":
    main()
