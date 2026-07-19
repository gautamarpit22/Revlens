# Orchestration (Dagster)

## Run the UI locally
```bash
export DBT_PROFILES_DIR=$PWD/dbt/revlens/profiles   # from repo root
dagster dev -f orchestration/definitions.py
```
Open http://localhost:3000 — Assets tab shows the full lineage graph
(simulator -> 7 bronze tables -> 14 dbt models). Click "Materialize all".

## Daily schedule
`daily_0600` runs the whole graph at 06:00. In the UI: Overview -> Schedules -> toggle on.
GitHub Actions mirrors this (cron in .github/workflows/ci.yml) so it runs even with your laptop off.

## Chaos drill (incident visibility demo)
```bash
REVLENS_CHAOS=1 dagster dev -f orchestration/definitions.py
```
Materialize all: hubspot_companies FAILS (simulated CRM outage), events/billing still load.
The UI shows exactly which asset failed and why — this is the "how do you know when it breaks" answer.

## Streaming path (Redpanda)
```bash
docker compose up -d                         # Redpanda + console (localhost:8080)
python ingestion/stream_producer.py --rate 20 --limit 2000   # terminal 1: live events
python ingestion/stream_consumer.py                          # terminal 2: validate + load
```
Consumer pattern: micro-batch append, contract validation in-flight (violations ->
raw.events_dead_letter_stream), offsets committed AFTER durable write (at-least-once;
event_id dedup in dbt => effectively exactly-once downstream).
