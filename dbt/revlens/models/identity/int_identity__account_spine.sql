-- One row per product account, resolved across all three systems:
--   product account_id  <- deterministic ->  stripe (customers.metadata.account_id)
--   product account_id  <- probabilistic ->  CRM company (user email domain = company domain)
-- CRM match rate is intentionally <100% (simulated stale domains); unmatched rate is a
-- tracked DQ metric, not silently ignored.
with account_domains as (
    select
        account_id,
        split_part(email, '@', 2) as email_domain,
        count(*) as n_users,
        row_number() over (partition by account_id order by count(*) desc) as rn
    from {{ ref('int_identity__user_to_account') }}
    group by 1, 2
),

primary_domain as (
    select account_id, email_domain from account_domains where rn = 1
),

-- CRM has duplicate company records per domain (a very common real-world CRM problem).
-- Survivorship rule: oldest record wins. Without this, the domain join fans out and
-- breaks account uniqueness — caught by the unique test on this model.
crm_companies_deduped as (
    select *
    from (
        select *,
               row_number() over (partition by domain order by crm_created_at, crm_company_id) as rn
        from {{ ref('stg_hubspot__companies') }}
    )
    where rn = 1
),

crm_match as (
    select d.account_id, c.crm_company_id, c.company_name, c.lifecycle_stage
    from primary_domain d
    left join crm_companies_deduped c
      on d.email_domain = c.domain
),

billing_match as (
    select account_id, stripe_customer_id
    from {{ ref('stg_stripe__customers') }}
    where account_id is not null
)

select
    d.account_id,
    d.email_domain,
    m.crm_company_id,
    m.company_name,
    m.lifecycle_stage,
    b.stripe_customer_id,
    m.crm_company_id is not null   as is_crm_matched,
    b.stripe_customer_id is not null as is_billing_matched
from primary_domain d
left join crm_match m using (account_id)
left join billing_match b using (account_id)
