-- Paid invoices are the ONLY source of truth for revenue (not deals, not subscriptions).
select
    id                                  as stripe_invoice_id,
    customer                            as stripe_customer_id,
    subscription                        as stripe_subscription_id,
    amount_paid / 100.0                 as amount_usd,
    status                              as invoice_status,
    to_timestamp(created)               as invoiced_at,
    date_trunc('month', to_timestamp(created)) as invoice_month,
    lines.data[1].quantity              as seat_count
from {{ source('raw', 'stripe_invoices') }}
