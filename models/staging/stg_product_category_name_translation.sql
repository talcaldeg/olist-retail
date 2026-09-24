-- Does not cover every category found in products (13 products fall outside it); the
-- gap is handled where the translation is joined, not hidden here.
select
    product_category_name,
    product_category_name_english
from {{ source('olist', 'product_category_name_translation') }}
