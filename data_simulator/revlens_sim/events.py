"""Telemetry event stream generation.

Produces Segment-style events:
  - anonymous browsing (anonymous_id only)
  - `identify` events that alias anonymous_id -> user_id  (identity resolution raw material)
  - authenticated product sessions with realistic event mixes
Chaos is injected on purpose: late arrivals, duplicates, nulls, malformed events.
"""

import json
import random
import uuid
from datetime import datetime, timedelta, time

from . import config as C


def _event_id() -> str:
    return f"evt_{uuid.uuid4().hex}"


def _base(name, ts, anonymous_id=None, user_id=None, device=None, **props):
    return {
        "event_id": _event_id(),
        "event_name": name,
        "event_ts": ts.isoformat() + "Z",
        "received_ts": ts.isoformat() + "Z",  # mutated for late arrivals
        "anonymous_id": anonymous_id,
        "user_id": user_id,
        "device_type": device,
        "user_agent": None if random.random() < C.CHAOS["null_user_agent_prob"] else "Mozilla/5.0",
        "properties": props,
        "schema_version": "1.0.0",
    }


def _apply_chaos(ev):
    out = [ev]
    r = random.random()
    if r < C.CHAOS["late_arriving_event_prob"]:
        late = datetime.fromisoformat(ev["event_ts"].rstrip("Z")) + timedelta(days=random.randint(1, 3))
        ev["received_ts"] = late.isoformat() + "Z"
    if random.random() < C.CHAOS["duplicate_event_prob"]:
        out.append(dict(ev))  # exact duplicate, same event_id
    if random.random() < C.CHAOS["malformed_event_prob"]:
        bad = dict(ev)
        bad.pop("event_ts")            # contract violation
        bad["event_name"] = 123        # wrong type
        out.append(bad)
    return out


def _rand_time(day):
    return datetime.combine(day, time(random.randint(6, 22), random.randint(0, 59), random.randint(0, 59)))


def visitor_events(visitor):
    """Anonymous top-of-funnel browsing: 1-2 short visits, mostly page views."""
    evs = []
    for _ in range(random.choices([1, 2], [0.8, 0.2])[0]):
        day = visitor["first_seen"] + timedelta(days=random.randint(0, 5))
        ts = _rand_time(day)
        for _ in range(random.randint(1, 4)):
            ts += timedelta(seconds=random.randint(20, 240))
            evs.append(_base("page_viewed", ts, anonymous_id=visitor["anonymous_id"],
                             device=visitor["device"],
                             page=random.choice(["/", "/pricing", "/features", "/blog", "/templates"]),
                             utm_source=visitor["utm_source"]))
    return evs


def user_lifecycle_events(user, account, end_date):
    """Full journey: anonymous browse -> signup -> identify (per device) -> daily product usage."""
    evs = []
    primary_anon = user["anonymous_ids"][0]
    signup_day = user["joined_date"]
    if signup_day > end_date:
        return evs

    # pre-signup anonymous browsing on primary device
    ts = _rand_time(signup_day) - timedelta(hours=random.randint(1, 48))
    for page in random.sample(["/", "/pricing", "/features", "/templates"], k=random.randint(1, 3)):
        evs.append(_base("page_viewed", ts, anonymous_id=primary_anon, device=user["devices"][0],
                         page=page, utm_source=random.choices(C.UTM_SOURCES, C.UTM_WEIGHTS)[0]))
        ts += timedelta(minutes=random.randint(1, 9))

    # signup + identify on primary device
    evs.append(_base("signed_up", ts, anonymous_id=primary_anon, device=user["devices"][0],
                     method=random.choice(["google_oauth", "email", "sso"])))
    evs.append(_base("identify", ts + timedelta(seconds=2), anonymous_id=primary_anon,
                     user_id=user["user_id"], device=user["devices"][0],
                     email=user["email"], account_id=account["account_id"]))

    # secondary devices get identified days later (cross-device stitching material)
    for anon, dev in list(zip(user["anonymous_ids"], user["devices"]))[1:]:
        d = signup_day + timedelta(days=random.randint(1, 21))
        if d <= end_date:
            t2 = _rand_time(d)
            evs.append(_base("page_viewed", t2 - timedelta(minutes=1), anonymous_id=anon, device=dev, page="/login"))
            evs.append(_base("identify", t2, anonymous_id=anon, user_id=user["user_id"],
                             device=dev, email=user["email"], account_id=account["account_id"]))

    # daily usage
    active_p = C.DAILY_ACTIVE_PROB[account["segment"]] * (C.ACTIVATION_BOOST if user["activated"] else 0.6)
    day = signup_day
    ramp_docs = 0
    while day <= end_date:
        if random.random() < active_p * C.DOW_ACTIVITY[day.weekday()]:
            anon_idx = random.randrange(len(user["anonymous_ids"]))
            ts = _rand_time(day)
            evs.append(_base("session_started", ts, anonymous_id=user["anonymous_ids"][anon_idx],
                             user_id=user["user_id"], device=user["devices"][anon_idx],
                             account_id=account["account_id"]))
            n_ev = random.randint(3, 15)
            names = random.choices(list(C.SESSION_EVENTS), list(C.SESSION_EVENTS.values()), k=n_ev)
            for name in names:
                ts += timedelta(seconds=random.randint(15, 300))
                props = {"account_id": account["account_id"]}
                if name == "doc_created":
                    ramp_docs += 1
                    props["doc_id"] = f"doc_{uuid.uuid4().hex[:10]}"
                if name == "member_invited":
                    props["invitee_domain"] = account["domain"]
                evs.append(_base(name, ts, anonymous_id=user["anonymous_ids"][anon_idx],
                                 user_id=user["user_id"], device=user["devices"][anon_idx], **props))
        day += timedelta(days=1)
    return evs


def chaos_pass(events):
    out = []
    for ev in events:
        out.extend(_apply_chaos(ev))
    return out


def write_ndjson(events, path):
    events.sort(key=lambda e: e.get("received_ts") or e.get("event_ts") or "9999")
    with open(path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
