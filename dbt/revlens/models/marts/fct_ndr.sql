-- Monthly Net Dollar Retention: revenue this month from accounts that existed last month,
-- divided by their revenue last month. Includes churn as zero. The PLG north-star metric.
with months as (
    select distinct invoice_month from {{ ref('fct_mrr_monthly') }}
),
cohort as (
    select
        m.invoice_month,
        prev.account_id,
        prev.mrr as base_mrr,
        coalesce(cur.mrr, 0) as retained_mrr
    from months m
    join {{ ref('fct_mrr_monthly') }} prev
      on prev.invoice_month = m.invoice_month - interval 1 month
    left join {{ ref('fct_mrr_monthly') }} cur
      on cur.account_id = prev.account_id and cur.invoice_month = m.invoice_month
)
select
    invoice_month,
    count(*)                                   as base_accounts,
    round(sum(base_mrr), 2)                    as base_mrr,
    round(sum(retained_mrr), 2)                as retained_mrr,
    round(sum(retained_mrr) / nullif(sum(base_mrr), 0), 4) as ndr,
    count(*) filter (where retained_mrr = 0)   as churned_accounts
from cohort
group by 1
order by 1
