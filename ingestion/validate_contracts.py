"""Validate an NDJSON event file against a JSON Schema contract.
Prints pass/fail counts and a sample of violations (dead-letter preview)."""
import json, sys
from jsonschema import Draft202012Validator

events_path, schema_path = sys.argv[1], sys.argv[2]
validator = Draft202012Validator(json.load(open(schema_path)))
ok = bad = 0
samples = []
with open(events_path) as f:
    for line in f:
        ev = json.loads(line)
        errs = list(validator.iter_errors(ev))
        if errs:
            bad += 1
            if len(samples) < 3:
                samples.append((ev.get("event_id", "?"), errs[0].message[:90]))
        else:
            ok += 1
print(f"valid: {ok:,} | dead-letter: {bad:,} ({bad/(ok+bad)*100:.3f}%)")
for eid, msg in samples:
    print(f"  DLQ sample {eid}: {msg}")
