-- metric: inventory_turnover
-- dimensions: none
-- filters: none
-- period: 2017-01 to 2018-08
with base as (
    select
        cost_of_goods_sold,
        avg_inventory_value
    from `olist-retail-portfolio.dbt_dev.mart_rotacion_inventario`
    where month_start between date '2017-01-01' and date '2018-08-01'
),

parts as (
    select
        sum(cost_of_goods_sold) as cost_of_goods_sold,
        sum(avg_inventory_value) as avg_inventory_value
    from base
)

select
    cost_of_goods_sold,
    avg_inventory_value,
    12 * safe_divide(cost_of_goods_sold, avg_inventory_value) as inventory_turnover
from parts
