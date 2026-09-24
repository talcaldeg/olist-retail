-- Grain: one row per stock movement of a (product, seller) pair. Olist has no inventory
-- data, so movements are simulated from the sales and the seeds (docs/assumptions.md):
--   initial_stock  once, on the first day of the pair's first month with sales, sized
--                  as months_of_cover times the pair's average monthly demand;
--   replenishment  each following month, while the pair keeps selling, the units sold
--                  the month before are reordered on day 1 and arrive lead_time_days
--                  later (periodic review, order-up-to);
--   sale           one unit out per stock-consuming sale line, on its purchase date.
-- Stock can go negative: that is a stockout served as a backorder, and it is kept on
-- purpose because stockouts are one of the things the marts measure.
with sales as (
    select sale_line_id, product_id, seller_id, purchase_date
    from {{ ref('fct_venta_linea') }}
    where consumes_stock
),

pairs as (
    select
        product_id,
        seller_id,
        date_trunc(min(purchase_date), month) as first_month,
        date_trunc(max(purchase_date), month) as last_month,
        count(*) as units_sold
    from sales
    group by product_id, seller_id
),

assumptions as (
    select
        pairs.*,
        products.category,
        products.months_of_cover,
        products.lead_time_days,
        costs.unit_cost
    from pairs
    inner join {{ ref('int_producto') }} as products using (product_id)
    inner join {{ ref('int_producto_vendedor') }} as costs using (product_id, seller_id)
),

monthly_sales as (
    select
        product_id,
        seller_id,
        date_trunc(purchase_date, month) as sales_month,
        count(*) as units
    from sales
    group by product_id, seller_id, sales_month
),

initial_stock as (
    select
        product_id,
        seller_id,
        first_month as movement_date,
        'initial_stock' as movement_type,
        cast(greatest(1, ceil(
            units_sold / (date_diff(last_month, first_month, month) + 1) * months_of_cover
        )) as int64) as quantity,
        cast(null as string) as sale_line_id
    from assumptions
),

replenishment as (
    select
        assumptions.product_id,
        assumptions.seller_id,
        date_add(order_month, interval assumptions.lead_time_days day) as movement_date,
        'replenishment' as movement_type,
        monthly_sales.units as quantity,
        cast(null as string) as sale_line_id
    from assumptions
    cross join unnest(generate_date_array(
        date_add(assumptions.first_month, interval 1 month),
        assumptions.last_month,
        interval 1 month
    )) as order_month
    inner join monthly_sales
        on monthly_sales.product_id = assumptions.product_id
        and monthly_sales.seller_id = assumptions.seller_id
        and monthly_sales.sales_month = date_sub(order_month, interval 1 month)
),

sale as (
    select
        product_id,
        seller_id,
        purchase_date as movement_date,
        'sale' as movement_type,
        -1 as quantity,
        sale_line_id
    from sales
),

movements as (
    select * from initial_stock
    union all
    select * from replenishment
    union all
    select * from sale
)

select
    concat(
        movements.product_id, '-', movements.seller_id, '-', movements.movement_type, '-',
        coalesce(movements.sale_line_id, cast(movements.movement_date as string))
    ) as movement_id,
    movements.product_id,
    movements.seller_id,
    assumptions.category,
    movements.movement_date,
    movements.movement_type,
    movements.quantity,
    assumptions.unit_cost,
    movements.quantity * assumptions.unit_cost as movement_value,
    movements.sale_line_id
from movements
inner join assumptions using (product_id, seller_id)
