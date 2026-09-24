-- One row per product with its category key and the synthetic assumptions attached to
-- it (see docs/assumptions.md). The source leaves two Portuguese categories without an
-- English name and 610 products without any category; both are resolved here. A
-- category that shows up later with no translation keeps its Portuguese name, finds no
-- seed row and fails the not_null tests instead of vanishing into "uncategorized".
with products as (
    select * from {{ ref('stg_products') }}
),

translation as (
    select * from {{ ref('stg_product_category_name_translation') }}
),

categorized as (
    select
        products.product_id,
        coalesce(
            translation.product_category_name_english,
            case products.product_category_name
                when 'portateis_cozinha_e_preparadores_de_alimentos'
                    then 'portable_kitchen_food_preparers'
            end,
            products.product_category_name,
            'uncategorized'
        ) as category
    from products
    left join translation using (product_category_name)
)

select
    categorized.product_id,
    categorized.category,
    category_cost.family as category_family,
    category_cost.cost_ratio,
    initial_stock.months_of_cover,
    lead_time.lead_time_days
from categorized
left join {{ ref('category_cost') }} as category_cost using (category)
left join {{ ref('initial_stock') }} as initial_stock using (category)
left join {{ ref('lead_time') }} as lead_time using (category)
