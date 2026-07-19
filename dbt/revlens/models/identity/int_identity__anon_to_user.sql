-- The identity graph, edge list: anonymous_id -> user_id, built from `identify` events.
-- Rules:
--   1. Earliest identify wins (first-writer). Later conflicting claims are flagged, not applied —
--      a device suddenly mapping to a second user is either shared-device or instrumentation bug.
--   2. Mapping is retroactive: pre-signup anonymous events get stitched to the user in fct_events.
with identify_events as (
    select
        anonymous_id,
        user_id,
        event_ts,
        row_number() over (partition by anonymous_id order by event_ts) as claim_rank
    from {{ ref('stg_events') }}
    where event_name = 'identify'
      and anonymous_id is not null
      and user_id is not null
)

select
    anonymous_id,
    user_id,
    event_ts as first_identified_at,
    count(*) over (partition by anonymous_id) > 1
        or max(user_id) over (partition by anonymous_id) != min(user_id) over (partition by anonymous_id)
        as had_conflicting_claims
from identify_events
where claim_rank = 1
