-- Grain: one row per order item. Olist records one row per unit, so quantity is always
-- 1; it is kept explicit so sums read as units and not as row counts.
with lines as (
    select * from {{ ref('stg_order_items') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
),

sellers as (
    select * from {{ ref('stg_sellers') }}
),

products as (
    select * from {{ ref('int_producto') }}
),

pairs as (
    select * from {{ ref('int_producto_vendedor') }}
)

select
    concat(lines.order_id, '-', cast(lines.order_item_id as string)) as sale_line_id,
    lines.order_id,
    lines.order_item_id,
    lines.product_id,
    lines.seller_id,
    customers.customer_unique_id,
    customers.customer_state,
    sellers.seller_state,
    products.category,
    products.category_family,
    orders.order_status,
    {{ consumes_stock('orders.order_status') }} as consumes_stock,
    orders.order_status = 'delivered' as is_delivered,
    orders.purchased_at,
    date(orders.purchased_at) as purchase_date,
    orders.delivered_to_customer_at,
    orders.estimated_delivery_at,
    1 as quantity,
    lines.price,
    lines.freight_value,
    pairs.unit_cost,
    lines.price - pairs.unit_cost as gross_margin
from lines
inner join orders using (order_id)
inner join customers using (customer_id)
inner join sellers using (seller_id)
inner join products using (product_id)
inner join pairs using (product_id, seller_id)
