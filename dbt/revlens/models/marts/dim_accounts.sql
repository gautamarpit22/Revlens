-- One row per account: identity spine + first-touch acquisition channel + revenue status.
with first_touch as (
    select
        account_id,
        utm_source,
        event_ts,
        row_number() over (partition by account_id order by event_ts) as rn
    from {{ ref('fct_events') }}
    where account_id is not null and utm_source is not null
)
select
    s.account_id,
    s.company_name,
    s.email_domain,
    s.crm_company_id,
    s.stripe_customer_id,
    s.is_crm_matched,
    s.is_billing_matched,
    ft.utm_source as first_touch_channel,
    ft.event_ts   as first_touch_at
from {{ ref('int_identity__account_spine') }} s
left join first_touch ft on s.account_id = ft.account_id and ft.rn = 1
