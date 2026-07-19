"""Load simulator NDJSON output into DuckDB `raw` schema.

Design decisions (mirror production ingestion):
- Events land AS-IS as raw JSON strings (raw.events_raw). No parsing, no filtering here —
  typing/dedup/dead-lettering is dbt's job. Raw layer is append-only and replayable.
- CRM/billing are API-shaped exports; loaded via read_json_auto into typed raw tables.
- Idempotent: full refresh per run (CREATE OR REPLACE). Incremental loading arrives in Phase 3
  with Dagster partitions.

Usage: python ingestion/load_duckdb.py [--db revlens.duckdb] [--data sample_data]
"""

import argparse
from pathlib import Path

import duckdb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="revlens.duckdb")
    ap.add_argument("--data", default="sample_data")
    args = ap.parse_args()
    data = Path(args.data)

    con = duckdb.connect(args.db)
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")

    # --- events: as-landed JSON lines ---
    con.execute(f"""
        CREATE OR REPLACE TABLE raw.events_raw AS
        SELECT json AS raw_json, current_timestamp AS _loaded_at
        FROM read_ndjson_objects('{data}/events/events.ndjson')
    """)

    # --- CRM (HubSpot-shaped) ---
    for obj in ["companies", "contacts", "deals"]:
        con.execute(f"""
            CREATE OR REPLACE TABLE raw.hubspot_{obj} AS
            SELECT *, current_timestamp AS _loaded_at
            FROM read_json_auto('{data}/crm/{obj}.ndjson')
        """)

    # --- Billing (Stripe-shaped) ---
    for obj in ["customers", "subscriptions", "invoices"]:
        con.execute(f"""
            CREATE OR REPLACE TABLE raw.stripe_{obj} AS
            SELECT *, current_timestamp AS _loaded_at
            FROM read_json_auto('{data}/billing/{obj}.ndjson')
        """)

    for (t,) in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='raw' ORDER BY 1"
    ).fetchall():
        n = con.execute(f"SELECT count(*) FROM raw.{t}").fetchone()[0]
        print(f"raw.{t}: {n:,} rows")


if __name__ == "__main__":
    main()
