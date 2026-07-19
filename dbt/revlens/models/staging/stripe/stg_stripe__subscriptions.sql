-- One row per subscription with flattened first line item (single-product company).
select
    id                                          as stripe_subscription_id,
    customer                                    as stripe_customer_id,
    status,
    to_timestamp(current_period_start)          as period_start_at,
    to_timestamp(try_cast(canceled_at as bigint))    as canceled_at,  -- explicit cast: read_json_auto's inferred type drifts (JSON vs BIGINT) with null density
    items.data[1].price.id                      as stripe_price_id,
    items.data[1].price.unit_amount / 100.0     as unit_price_usd,
    items.data[1].quantity                      as seat_count
from {{ source('raw', 'stripe_subscriptions') }}
