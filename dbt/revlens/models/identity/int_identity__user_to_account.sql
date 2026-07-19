-- user_id -> account_id + email, from identify events (earliest wins).
with claims as (
    select
        user_id,
        account_id,
        lower(email) as email,
        event_ts,
        row_number() over (partition by user_id order by event_ts) as rn
    from {{ ref('stg_events') }}
    where event_name = 'identify' and user_id is not null and account_id is not null
)
select user_id, account_id, email, event_ts as joined_at
from claims where rn = 1
