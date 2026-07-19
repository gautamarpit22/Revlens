"""RevLens data simulator entrypoint.

Usage:
    python generate.py --out ../sample_data [--days 180] [--accounts 400]

Outputs:
    events/events.ndjson          - Segment-style telemetry (incl. identify events + chaos)
    crm/companies|contacts|deals.ndjson  - HubSpot-shaped CRM export
    billing/customers|subscriptions|invoices.ndjson - Stripe-shaped billing export
    manifest.json                 - row counts + generation parameters (for validation)
"""

import argparse
import json
import random
from datetime import timedelta
from pathlib import Path

from revlens_sim import config as C
from revlens_sim import entities, events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../sample_data")
    ap.add_argument("--days", type=int, default=C.DAYS)
    ap.add_argument("--accounts", type=int, default=C.N_ACCOUNTS)
    ap.add_argument("--seed", type=int, default=C.SEED)
    args = ap.parse_args()

    C.DAYS, C.N_ACCOUNTS = args.days, args.accounts
    random.seed(args.seed)
    entities.fake.seed_instance(args.seed)

    end_date = C.START_DATE + timedelta(days=C.DAYS)
    out = Path(args.out)
    for sub in ["events", "crm", "billing"]:
        (out / sub).mkdir(parents=True, exist_ok=True)

    print(f"Generating world: {C.N_ACCOUNTS} accounts over {C.DAYS} days...")
    accounts = entities.gen_accounts()
    users_by_account = {a["account_id"]: entities.gen_users(a) for a in accounts}
    all_users = [u for us in users_by_account.values() for u in us]
    visitors = entities.gen_anonymous_visitors(C.N_ACCOUNTS * C.ANON_VISITOR_MULTIPLIER)

    print("Generating telemetry events...")
    evs = []
    for v in visitors:
        evs.extend(events.visitor_events(v))
    for a in accounts:
        for u in users_by_account[a["account_id"]]:
            evs.extend(events.user_lifecycle_events(u, a, end_date))
    evs = events.chaos_pass(evs)
    events.write_ndjson(evs, out / "events" / "events.ndjson")

    print("Generating CRM (HubSpot-shaped)...")
    companies, contacts, deals = entities.gen_crm(accounts, users_by_account)
    for name, rows in [("companies", companies), ("contacts", contacts), ("deals", deals)]:
        with open(out / "crm" / f"{name}.ndjson", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    print("Generating billing (Stripe-shaped)...")
    customers, subs, invoices = entities.gen_billing(accounts, users_by_account, end_date)
    for name, rows in [("customers", customers), ("subscriptions", subs), ("invoices", invoices)]:
        with open(out / "billing" / f"{name}.ndjson", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    manifest = {
        "seed": args.seed, "days": C.DAYS, "accounts": C.N_ACCOUNTS,
        "counts": {
            "events": len(evs), "users": len(all_users), "visitors": len(visitors),
            "crm_companies": len(companies), "crm_contacts": len(contacts), "crm_deals": len(deals),
            "stripe_customers": len(customers), "stripe_subscriptions": len(subs),
            "stripe_invoices": len(invoices),
        },
    }
    with open(out / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest["counts"], indent=2))
    print(f"Done -> {out.resolve()}")


if __name__ == "__main__":
    main()
