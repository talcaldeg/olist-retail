select
    customer_id,
    customer_unique_id,
    {{ zip_prefix('customer_zip_code_prefix') }} as customer_zip_code_prefix,
    customer_city,
    upper(customer_state) as customer_state
from {{ source('olist', 'customers') }}
