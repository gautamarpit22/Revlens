"""RevLens orchestration: Dagster asset graph.

Asset graph (mirrors the medallion flow):

    generate_sample_data                     (simulator; demo/CI stand-in for real sources)
        v
    events_raw, hubspot_*, stripe_*          (Bronze: one asset per raw table)
        v
    dbt assets (all 14 models + tests)       (Silver + Gold, via dagster-dbt)

Design notes:
- One asset PER raw table: a CRM outage doesn't block event/billing loads, and the
  Dagster UI shows exactly which table failed.
- dbt models appear individually in the graph (dagster-dbt parses the manifest); the
  translator maps dbt sources onto the Bronze assets so lineage is continuous end-to-end.
- daily_0600 schedule runs everything; failures surface per-asset.
- REVLENS_CHAOS=1 makes hubspot_companies fail on purpose (incident-visibility demo).
"""

import os
import subprocess
from pathlib import Path

import duckdb
from dagster import (
    AssetExecutionContext,
    AssetKey,
    Definitions,
    MaterializeResult,
    MetadataValue,
    ScheduleDefinition,
    asset,
    define_asset_job,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "revlens.duckdb"
DATA_DIR = REPO_ROOT / "sample_data"

dbt_project = DbtProject(
    project_dir=REPO_ROOT / "dbt" / "revlens",
    profiles_dir=REPO_ROOT / "dbt" / "revlens" / "profiles",
)
os.environ.setdefault("REVLENS_DB_PATH", str(DB_PATH))
dbt_project.prepare_if_dev()


@asset(group_name="simulator", compute_kind="python")
def generate_sample_data(context: AssetExecutionContext) -> MaterializeResult:
    """Run the deterministic world simulator (demo/CI only; production = real source systems)."""
    days = os.environ.get("REVLENS_SIM_DAYS", "180")
    accounts = os.environ.get("REVLENS_SIM_ACCOUNTS", "400")
    subprocess.run(
        ["python3", "generate.py", "--out", str(DATA_DIR), "--days", days, "--accounts", accounts],
        cwd=REPO_ROOT / "data_simulator", check=True, capture_output=True,
    )
    n = sum(1 for _ in open(DATA_DIR / "events" / "events.ndjson"))
    return MaterializeResult(metadata={"events_generated": MetadataValue.int(n)})


def _load_table(table: str, sql: str) -> int:
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(sql)
    return con.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0]


def _make_raw_asset(table: str, src_path: str, reader: str, group: str, chaos: bool = False):
    @asset(name=table, deps=[generate_sample_data], group_name=group, compute_kind="duckdb")
    def _raw_asset(context: AssetExecutionContext) -> MaterializeResult:
        if chaos and os.environ.get("REVLENS_CHAOS") == "1":
            raise Exception("CHAOS DRILL: simulated CRM API outage (HTTP 503). "
                            "Other Bronze assets still materialize — failure isolation works.")
        n = _load_table(table, f"""
            CREATE OR REPLACE TABLE raw.{table} AS
            SELECT {'json AS raw_json,' if reader == 'ndjson_objects' else '*,'}
                   current_timestamp AS _loaded_at
            FROM read_{'ndjson_objects' if reader == 'ndjson_objects' else 'json_auto'}('{DATA_DIR}/{src_path}')
        """)
        return MaterializeResult(metadata={"rows": MetadataValue.int(n)})
    return _raw_asset


RAW_SPECS = [
    ("events_raw",            "events/events.ndjson",      "ndjson_objects", "bronze_events",  False),
    ("hubspot_companies",     "crm/companies.ndjson",      "json_auto",      "bronze_crm",     True),
    ("hubspot_contacts",      "crm/contacts.ndjson",       "json_auto",      "bronze_crm",     False),
    ("hubspot_deals",         "crm/deals.ndjson",          "json_auto",      "bronze_crm",     False),
    ("stripe_customers",      "billing/customers.ndjson",  "json_auto",      "bronze_billing", False),
    ("stripe_subscriptions",  "billing/subscriptions.ndjson", "json_auto",   "bronze_billing", False),
    ("stripe_invoices",       "billing/invoices.ndjson",   "json_auto",      "bronze_billing", False),
]
raw_assets = [_make_raw_asset(*spec) for spec in RAW_SPECS]


class Translator(DagsterDbtTranslator):
    """Map each dbt source onto its Bronze asset -> continuous end-to-end lineage."""
    def get_asset_key(self, dbt_resource_props):
        if dbt_resource_props["resource_type"] == "source":
            return AssetKey([dbt_resource_props["name"]])
        return super().get_asset_key(dbt_resource_props)


@dbt_assets(manifest=dbt_project.manifest_path, dagster_dbt_translator=Translator())
def revlens_dbt(context: AssetExecutionContext, dbt: DbtCliResource):
    """All dbt models + tests; each model is its own asset in the lineage graph."""
    yield from dbt.cli(["build"], context=context).stream()


daily_job = define_asset_job("daily_pipeline", selection="*")

defs = Definitions(
    assets=[generate_sample_data, *raw_assets, revlens_dbt],
    jobs=[daily_job],
    schedules=[ScheduleDefinition(job=daily_job, cron_schedule="0 6 * * *", name="daily_0600")],
    resources={"dbt": DbtCliResource(project_dir=dbt_project)},
)
