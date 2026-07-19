"""Streaming consumer: Redpanda -> DuckDB raw layer, with in-flight contract validation.

Pattern: micro-batch append. Poll messages, validate each against the event contract,
append valid ones to raw.events_raw and violations to raw.events_dead_letter_stream —
same quarantine philosophy as batch, applied in-flight. Commits offsets AFTER the
DuckDB append (at-least-once delivery; dedup on event_id in dbt makes it effectively
exactly-once downstream — say exactly this in interviews).

Usage:  python ingestion/stream_consumer.py [--batch-size 200] [--timeout 60]
"""
import argparse
import json
import time
from pathlib import Path

import duckdb
from jsonschema import Draft202012Validator
from kafka import KafkaConsumer

TOPIC = "product-events"
ROOT = Path(__file__).resolve().parents[1]


def flush(con, valid, invalid):
    if valid:
        con.executemany(
            "INSERT INTO raw.events_raw VALUES (?, current_timestamp)",
            [(json.dumps(e),) for e in valid],
        )
    if invalid:
        con.executemany(
            "INSERT INTO raw.events_dead_letter_stream VALUES (?, ?, current_timestamp)",
            [(json.dumps(e), reason) for e, reason in invalid],
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="localhost:9092")
    ap.add_argument("--batch-size", type=int, default=200)
    ap.add_argument("--timeout", type=int, default=60, help="exit after N idle seconds")
    args = ap.parse_args()

    validator = Draft202012Validator(
        json.load(open(ROOT / "contracts" / "product_event.v1.schema.json"))
    )
    con = duckdb.connect(str(ROOT / "revlens.duckdb"))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("""CREATE TABLE IF NOT EXISTS raw.events_raw
                   (raw_json VARCHAR, _loaded_at TIMESTAMPTZ)""")
    con.execute("""CREATE TABLE IF NOT EXISTS raw.events_dead_letter_stream
                   (raw_json VARCHAR, failure_reason VARCHAR, _loaded_at TIMESTAMPTZ)""")

    consumer = KafkaConsumer(
        TOPIC, bootstrap_servers=args.broker, group_id="revlens-loader",
        value_deserializer=lambda m: json.loads(m.decode()),
        enable_auto_commit=False, auto_offset_reset="earliest",
    )
    valid, invalid, total, last_msg = [], [], 0, time.time()
    print("Consuming... (Ctrl+C to stop)")
    try:
        while time.time() - last_msg < args.timeout:
            polled = consumer.poll(timeout_ms=1000)
            for records in polled.values():
                for r in records:
                    last_msg = time.time()
                    errs = list(validator.iter_errors(r.value))
                    (invalid.append((r.value, errs[0].message[:200])) if errs
                     else valid.append(r.value))
                    total += 1
            if len(valid) + len(invalid) >= args.batch_size:
                flush(con, valid, invalid)
                consumer.commit()  # commit AFTER durable write -> at-least-once
                print(f"flushed batch: {len(valid)} valid, {len(invalid)} dead-letter (total {total})")
                valid, invalid = [], []
    except KeyboardInterrupt:
        pass
    flush(con, valid, invalid)
    consumer.commit()
    print(f"Done. {total} consumed.")


if __name__ == "__main__":
    main()
