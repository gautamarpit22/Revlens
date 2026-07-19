"""Live event producer: replays simulator events to Redpanda in real time.

Simulates a production event stream (Segment -> Kafka). Reads generated events and
publishes them to the `product-events` topic at a configurable rate.

Usage:  python ingestion/stream_producer.py [--rate 20] [--limit 2000]
Requires: docker compose up -d   (Redpanda on localhost:9092)
"""
import argparse
import json
import time

from kafka import KafkaProducer

TOPIC = "product-events"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="sample_data/events/events.ndjson")
    ap.add_argument("--rate", type=float, default=20, help="events per second")
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--broker", default="localhost:9092")
    args = ap.parse_args()

    producer = KafkaProducer(
        bootstrap_servers=args.broker,
        value_serializer=lambda v: json.dumps(v).encode(),
        key_serializer=lambda k: (k or "").encode(),
    )
    sent = 0
    with open(args.events) as f:
        for line in f:
            ev = json.loads(line)
            # key by identity -> same user's events stay ordered within a partition
            key = ev.get("user_id") or ev.get("anonymous_id") or ""
            producer.send(TOPIC, key=key, value=ev)
            sent += 1
            if sent >= args.limit:
                break
            time.sleep(1.0 / args.rate)
    producer.flush()
    print(f"Produced {sent} events to '{TOPIC}'")


if __name__ == "__main__":
    main()
