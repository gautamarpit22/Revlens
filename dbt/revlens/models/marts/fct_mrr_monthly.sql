-- Account-month MRR ledger from PAID invoices, with movement classification:
-- new / expansion / contraction / churned / retained. NDR is derived from this in fct_ndr.
with invoice_mrr as (
    select
        i.invoice_month,
        c.account_id,
        sum(i.amount_usd) as mrr
    from {{ ref('stg_stripe__invoices') }} i
    join {{ ref('stg_stripe__customers') }} c using (stripe_customer_id)
    where i.invoice_status = 'paid'
    group by 1, 2
),

with_prev as (
    select
        *,
        lag(mrr) over (partition by account_id order by invoice_month) as prev_mrr,
        lag(invoice_month) over (partition by account_id order by invoice_month) as prev_month
    from invoice_mrr
),

classified as (
    select
        invoice_month,
        account_id,
        mrr,
        coalesce(prev_mrr, 0) as prev_mrr,
        case
            when prev_mrr is null or prev_month < invoice_month - interval 35 day then 'new'
            when mrr > prev_mrr then 'expansion'
            when mrr < prev_mrr then 'contraction'
            else 'retained'
        end as movement
    from with_prev
)

select * from classified
