-- Billing customers. metadata.account_id gives a DETERMINISTIC link to the product account
-- (checkout embeds it) — this is the identity spine between billing and product.
select
    id                                   as stripe_customer_id,
    lower(email)                         as email,
    name                                 as customer_name,
    to_timestamp(created)                as billing_created_at,
    metadata ->> '$.account_id'          as account_id
from {{ source('raw', 'stripe_customers') }}
