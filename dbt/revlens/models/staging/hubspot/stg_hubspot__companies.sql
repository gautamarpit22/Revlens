-- CRM companies, un-nested from HubSpot's properties wrapper. Domain is normalized
-- lowercase; note ~3% have stale/typo domains vs billing (handled in identity layer).
select
    id                                            as crm_company_id,
    properties ->> '$.name'                       as company_name,
    lower(properties ->> '$.domain')              as domain,
    properties ->> '$.industry'                   as industry,
    try_cast(properties ->> '$.numberofemployees' as int) as employee_count,
    properties ->> '$.lifecyclestage'             as lifecycle_stage,
    try_cast(properties ->> '$.createdate' as timestamp) as crm_created_at
from {{ source('raw', 'hubspot_companies') }}
