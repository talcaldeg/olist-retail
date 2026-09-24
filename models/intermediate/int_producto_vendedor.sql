-- One row per (product, seller): the unit that holds stock, since 1,225 products are
-- sold by more than one seller. The standard unit cost is the category cost ratio
-- applied to the pair's average selling price. Sales and stock both use it, so the
-- cost of goods sold and the value of the stock that left always agree.
with lines as (
    select * from {{ ref('stg_order_items') }}
),

products as (
    select * from {{ ref('int_producto') }}
)

select
    lines.product_id,
    lines.seller_id,
    round(avg(lines.price), 2) as avg_price,
    round(avg(lines.price) * any_value(products.cost_ratio), 2) as unit_cost
from lines
inner join products using (product_id)
group by lines.product_id, lines.seller_id
