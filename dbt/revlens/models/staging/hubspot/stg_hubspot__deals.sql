-- Sales-assisted deals (mid-market/enterprise only; self-serve converts without a deal).
select
    id                                             as crm_deal_id,
    properties ->> '$.dealname'                    as deal_name,
    try_cast(properties ->> '$.amount' as decimal(12,2)) as deal_amount_annual,
    properties ->> '$.dealstage'                   as deal_stage,
    try_cast(properties ->> '$.closedate' as date) as close_date,
    properties ->> '$.associatedcompanyid'         as crm_company_id
from {{ source('raw', 'hubspot_deals') }}
