-- All valid telemetry with identity RESOLVED: pre-signup anonymous events are retroactively
-- attributed to the user (and account) they later became. This is what makes first-touch
-- attribution possible.
select
    e.event_id,
    e.event_name,
    e.event_ts,
    e.device_type,
    e.page,
    e.utm_source,
    coalesce(e.user_id, m.user_id)          as user_id,
    coalesce(e.account_id, ua.account_id)   as account_id,
    e.user_id is null and m.user_id is not null as is_stitched,
    e.anonymous_id
from {{ ref('stg_events') }} e
left join {{ ref('int_identity__anon_to_user') }} m
  on e.anonymous_id = m.anonymous_id
left join {{ ref('int_identity__user_to_account') }} ua
  on coalesce(e.user_id, m.user_id) = ua.user_id
where e.event_name != 'identify'
