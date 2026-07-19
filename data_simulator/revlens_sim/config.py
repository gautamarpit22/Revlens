"""World configuration for the RevLens data simulator.

NotionClone: a fictional PLG collaboration SaaS.
All probabilities are per-relevant-unit (day / session / event) and tuned to
produce a realistic funnel:  visitor -> signup -> activation -> trial -> paid -> (churn|expand)
"""

from datetime import date

SEED = 42

# Simulation window
START_DATE = date(2025, 7, 1)
DAYS = 180  # 6 months of history

# Company scale
N_ACCOUNTS = 400            # companies that ever sign up
ANON_VISITOR_MULTIPLIER = 6  # anonymous visitors per eventual signup (top of funnel)

SEGMENTS = {
    "self_serve": {"weight": 0.75, "seats_range": (1, 8),   "trial_to_paid": 0.28},
    "mid_market": {"weight": 0.20, "seats_range": (5, 40),  "trial_to_paid": 0.45},
    "enterprise": {"weight": 0.05, "seats_range": (25, 200), "trial_to_paid": 0.60},
}

PLANS = {
    "free":     {"price_per_seat": 0,  "stripe_price_id": "price_free_000"},
    "pro":      {"price_per_seat": 10, "stripe_price_id": "price_pro_010"},
    "business": {"price_per_seat": 24, "stripe_price_id": "price_biz_024"},
}

TRIAL_DAYS = 14

# Behaviour probabilities
DAILY_ACTIVE_PROB = {"self_serve": 0.35, "mid_market": 0.45, "enterprise": 0.55}
MONTHLY_LOGO_CHURN = {"self_serve": 0.045, "mid_market": 0.02, "enterprise": 0.008}
MONTHLY_EXPANSION_PROB = {"self_serve": 0.03, "mid_market": 0.08, "enterprise": 0.12}

# Weekly seasonality multiplier on activity (Mon..Sun)
DOW_ACTIVITY = [1.15, 1.2, 1.2, 1.15, 1.0, 0.45, 0.35]

# Event catalogue (name -> weight within an active session)
SESSION_EVENTS = {
    "page_viewed": 0.30,
    "doc_created": 0.14,
    "doc_edited": 0.26,
    "comment_added": 0.10,
    "search_performed": 0.08,
    "integration_used": 0.05,
    "member_invited": 0.04,
    "export_performed": 0.03,
}

# Activation = doc_created >= 3 within first 7 days (used implicitly by behaviour ramps)
ACTIVATION_BOOST = 1.6  # activated users are more active

# Data-quality chaos (intentional, for DQ framework to catch later)
CHAOS = {
    "late_arriving_event_prob": 0.015,   # event lands 1-3 days late
    "duplicate_event_prob": 0.004,
    "null_user_agent_prob": 0.02,
    "malformed_event_prob": 0.002,       # violates contract -> dead letter demo
    "crm_stale_domain_prob": 0.03,       # CRM domain typo vs billing email domain
}

DEVICES = ["desktop_web", "mobile_web", "ios_app", "android_app"]
DEVICE_WEIGHTS = [0.62, 0.18, 0.12, 0.08]

UTM_SOURCES = ["google", "twitter", "linkedin", "producthunt", "direct", "newsletter"]
UTM_WEIGHTS = [0.34, 0.10, 0.16, 0.08, 0.24, 0.08]
