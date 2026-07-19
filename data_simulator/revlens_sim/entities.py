"""Entity generation: accounts, users, identity graph, CRM + billing shapes."""

import random
import uuid
from datetime import datetime, timedelta, time

from faker import Faker

from . import config as C

fake = Faker()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def pick_segment() -> str:
    names = list(C.SEGMENTS)
    weights = [C.SEGMENTS[s]["weight"] for s in names]
    return random.choices(names, weights)[0]


def gen_accounts():
    """Accounts with a signup date spread across the window (front-loaded growth curve)."""
    accounts = []
    for _ in range(C.N_ACCOUNTS):
        # Growth: more signups later in the window (linear ramp)
        day_offset = int(C.DAYS * (random.random() ** 0.6))
        signup_date = C.START_DATE + timedelta(days=day_offset)
        segment = pick_segment()
        company = fake.company()
        domain = company.lower().replace(",", "").replace(".", "").replace(" ", "").replace("'", "")[:18] + ".com"
        seats = random.randint(*C.SEGMENTS[segment]["seats_range"])
        accounts.append({
            "account_id": _uid("acct"),
            "company_name": company,
            "domain": domain,
            "segment": segment,
            "signup_date": signup_date,
            "seats": seats,
            "trial_converts": random.random() < C.SEGMENTS[segment]["trial_to_paid"],
            "plan": random.choices(["pro", "business"], [0.7, 0.3])[0],
        })
    return accounts


def gen_users(account):
    """Users for an account. Each user has 1-3 devices (anonymous_ids) forming the identity graph."""
    users = []
    n = max(1, int(account["seats"] * random.uniform(0.5, 0.9)))
    for i in range(n):
        first, last = fake.first_name(), fake.last_name()
        user_id = _uid("usr")
        n_devices = random.choices([1, 2, 3], [0.55, 0.33, 0.12])[0]
        # Users join staggered after account signup
        joined = account["signup_date"] + timedelta(days=int(random.expovariate(1 / 5)))
        users.append({
            "user_id": user_id,
            "account_id": account["account_id"],
            "email": f"{first.lower()}.{last.lower()}@{account['domain']}",
            "name": f"{first} {last}",
            "role": "admin" if i == 0 else random.choice(["member", "member", "guest"]),
            "joined_date": joined,
            "anonymous_ids": [_uid("anon") for _ in range(n_devices)],
            "devices": random.choices(C.DEVICES, C.DEVICE_WEIGHTS, k=n_devices),
            "activated": random.random() < 0.62,
        })
    return users


def gen_anonymous_visitors(n):
    """Top-of-funnel visitors who never sign up: anonymous events only."""
    return [{
        "anonymous_id": _uid("anon"),
        "device": random.choices(C.DEVICES, C.DEVICE_WEIGHTS)[0],
        "utm_source": random.choices(C.UTM_SOURCES, C.UTM_WEIGHTS)[0],
        "first_seen": C.START_DATE + timedelta(days=random.randint(0, C.DAYS - 1)),
    } for _ in range(n)]


# ---------------- CRM (HubSpot-shaped) ----------------

def gen_crm(accounts, users_by_account):
    companies, contacts, deals = [], [], []
    for a in accounts:
        domain = a["domain"]
        if random.random() < C.CHAOS["crm_stale_domain_prob"]:
            domain = domain.replace(".com", ".co")  # intentional mismatch vs billing
        companies.append({
            "id": _uid("hub_co"),
            "properties": {
                "name": a["company_name"],
                "domain": domain,
                "industry": fake.bs().split()[-1],
                "numberofemployees": a["seats"] * random.randint(3, 8),
                "lifecyclestage": "customer" if a["trial_converts"] else "opportunity",
                "createdate": datetime.combine(a["signup_date"], time(10, 0)).isoformat(),
            },
        })
        for u in users_by_account[a["account_id"]][:3]:  # only some users exist in CRM
            contacts.append({
                "id": _uid("hub_ct"),
                "properties": {
                    "email": u["email"],
                    "firstname": u["name"].split()[0],
                    "lastname": u["name"].split()[-1],
                    "associatedcompanyid": companies[-1]["id"],
                    "createdate": datetime.combine(u["joined_date"], time(11, 0)).isoformat(),
                },
            })
        if a["segment"] != "self_serve":  # sales-assisted deals only
            close_date = a["signup_date"] + timedelta(days=C.TRIAL_DAYS + random.randint(0, 10))
            deals.append({
                "id": _uid("hub_dl"),
                "properties": {
                    "dealname": f"{a['company_name']} - {a['plan'].title()}",
                    "amount": C.PLANS[a["plan"]]["price_per_seat"] * a["seats"] * 12,
                    "dealstage": "closedwon" if a["trial_converts"] else "closedlost",
                    "closedate": close_date.isoformat(),
                    "associatedcompanyid": companies[-1]["id"],
                },
            })
    return companies, contacts, deals


# ---------------- Billing (Stripe-shaped) ----------------

def gen_billing(accounts, users_by_account, end_date):
    customers, subscriptions, invoices = [], [], []
    for a in accounts:
        if not a["trial_converts"]:
            continue
        admin = users_by_account[a["account_id"]][0]
        cust_id = _uid("cus")
        sub_start = a["signup_date"] + timedelta(days=C.TRIAL_DAYS)
        if sub_start > end_date:
            continue
        customers.append({
            "id": cust_id,
            "object": "customer",
            "email": admin["email"],
            "name": a["company_name"],
            "created": int(datetime.combine(sub_start, time(9, 0)).timestamp()),
            "metadata": {"account_id": a["account_id"]},
        })
        # churn month via geometric draw
        churn_p = C.MONTHLY_LOGO_CHURN[a["segment"]]
        months_alive = 1
        while random.random() > churn_p and months_alive < 24:
            months_alive += 1
        churn_date = sub_start + timedelta(days=30 * months_alive)
        status = "canceled" if churn_date <= end_date else "active"
        seats = a["seats"]
        price = C.PLANS[a["plan"]]["price_per_seat"]
        sub_id = _uid("sub")
        subscriptions.append({
            "id": sub_id,
            "object": "subscription",
            "customer": cust_id,
            "status": status,
            "current_period_start": int(datetime.combine(sub_start, time(0, 0)).timestamp()),
            "canceled_at": int(datetime.combine(churn_date, time(0, 0)).timestamp()) if status == "canceled" else None,
            "items": {"data": [{
                "price": {"id": C.PLANS[a["plan"]]["stripe_price_id"], "unit_amount": price * 100},
                "quantity": seats,
            }]},
        })
        # monthly invoices, with expansion (seat growth) sometimes
        month, cur = 0, sub_start
        while cur <= min(churn_date, end_date):
            if month > 0 and random.random() < C.MONTHLY_EXPANSION_PROB[a["segment"]]:
                seats = int(seats * random.uniform(1.1, 1.4))
            invoices.append({
                "id": _uid("in"),
                "object": "invoice",
                "customer": cust_id,
                "subscription": sub_id,
                "amount_paid": seats * price * 100,
                "currency": "usd",
                "status": "paid" if random.random() > 0.015 else "uncollectible",
                "created": int(datetime.combine(cur, time(2, 0)).timestamp()),
                "lines": {"data": [{"quantity": seats, "price": {"id": C.PLANS[a["plan"]]["stripe_price_id"]}}]},
            })
            month += 1
            cur += timedelta(days=30)
    return customers, subscriptions, invoices
