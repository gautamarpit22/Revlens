-- THE closed loop: acquisition channel -> product signups -> paid conversion -> lifetime revenue.
-- First-touch model (the earliest pre-signup anonymous event's utm_source, recoverable only
-- because of identity stitching). Answers: "which channel brings customers who actually pay?"
with account_revenue as (
    select account_id, sum(mrr) as total_revenue, count(distinct invoice_month) as months_paying
    from {{ ref('fct_mrr_monthly') }}
    group by 1
)
select
    coalesce(a.first_touch_channel, '(unattributed)') as channel,
    count(*)                                          as accounts_signed_up,
    count(r.account_id)                               as accounts_paying,
    round(count(r.account_id) * 1.0 / count(*), 3)    as signup_to_paid_rate,
    round(coalesce(sum(r.total_revenue), 0), 2)       as total_revenue_usd,
    round(coalesce(sum(r.total_revenue), 0) / nullif(count(r.account_id), 0), 2) as revenue_per_paying_account
from {{ ref('dim_accounts') }} a
left join account_revenue r using (account_id)
group by 1
order by total_revenue_usd desc
