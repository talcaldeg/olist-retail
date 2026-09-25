-- Question: which categories make money, and how much of each sale is margin?
-- Grain: month x category. Only lines that shipped (consumes_stock): a canceled order
-- is neither revenue nor cost of goods. Revenue is the item price; freight goes to the
-- carrier and is left out.
with lines as (
    select *, date_trunc(purchase_date, month) as month_start
    from {{ ref('fct_venta_linea') }}
    where consumes_stock
)

select
    month_start,
    category,
    any_value(category_family) as category_family,
    {{ in_reporting_window('month_start') }} as in_reporting_window,
    sum(quantity) as units_sold,
    count(distinct order_id) as orders,
    sum(price) as revenue,
    sum(unit_cost * quantity) as cost_of_goods_sold,
    sum(gross_margin) as gross_margin,
    safe_divide(sum(gross_margin), sum(price)) as gross_margin_pct
from lines
group by month_start, category
