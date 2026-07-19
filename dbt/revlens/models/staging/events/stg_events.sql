-- Typed, contract-checked, deduplicated telemetry events.
-- Invalid events are excluded here and captured in stg_events_dead_letter (never dropped silently).
with parsed as (
    select
        raw_json ->> '$.event_id'                            as event_id,
        raw_json ->> '$.event_name'                          as event_name,
        json_type(raw_json -> '$.event_name')                as event_name_json_type,
        try_cast(raw_json ->> '$.event_ts' as timestamp)     as event_ts,
        try_cast(raw_json ->> '$.received_ts' as timestamp)  as received_ts,
        raw_json ->> '$.anonymous_id'                        as anonymous_id,
        raw_json ->> '$.user_id'                             as user_id,
        raw_json ->> '$.device_type'                         as device_type,
        raw_json ->> '$.properties.account_id'               as account_id,
        raw_json ->> '$.properties.page'                     as page,
        raw_json ->> '$.properties.utm_source'               as utm_source,
        raw_json ->> '$.properties.email'                    as email,
        raw_json ->> '$.schema_version'                      as schema_version,
        _loaded_at
    from {{ source('raw', 'events_raw') }}
),

valid as (
    select *
    from parsed
    where event_id is not null
      and event_name is not null
      and event_name_json_type = 'VARCHAR'  -- excludes non-string chaos (event_name: 123)
      and event_ts is not null
      and (anonymous_id is not null or user_id is not null)
),

deduped as (
    select
        *,
        row_number() over (partition by event_id order by received_ts nulls last) as _rn
    from valid
)

select
    event_id, event_name, event_ts, received_ts, anonymous_id, user_id,
    device_type, account_id, page, utm_source, email, schema_version,
    date_diff('hour', event_ts, received_ts) as arrival_delay_hours
from deduped
where _rn = 1
