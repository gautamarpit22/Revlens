-- CRM contacts. Email is the join key to product users (stg_events.email via identify).
select
    id                                        as crm_contact_id,
    lower(properties ->> '$.email')           as email,
    properties ->> '$.firstname'              as first_name,
    properties ->> '$.lastname'               as last_name,
    properties ->> '$.associatedcompanyid'    as crm_company_id
from {{ source('raw', 'hubspot_contacts') }}
