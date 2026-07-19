-- Quarantine for contract-violating events, with machine-readable failure reason.
-- Feeds the DQ dashboard (Phase 3) and the AI triage agent (Phase 5).
with parsed as (
    select
        raw_json,
        raw_json ->> '$.event_id'                        as event_id,
        try_cast(raw_json ->> '$.event_ts' as timestamp) as event_ts,
        raw_json ->> '$.anonymous_id'                    as anonymous_id,
        raw_json ->> '$.user_id'                         as user_id,
        _loaded_at
    from {{ source('raw', 'events_raw') }}
)
select
    event_id,
    raw_json,
    case
        when event_ts is null then 'missing_or_invalid_event_ts'
        when json_type(raw_json -> '$.event_name') != 'VARCHAR' then 'event_name_not_string'
        when anonymous_id is null and user_id is null then 'no_identity'
        else 'unknown_violation'
    end as failure_reason,
    _loaded_at
from parsed
where event_ts is null
   or json_type(raw_json -> '$.event_name') != 'VARCHAR'
   or (anonymous_id is null and user_id is null)
