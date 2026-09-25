-- The four marts describe the same sales from two sides (sale lines and stock
-- movements): for every month and category they must count the same units, and the
-- margin and turnover marts the same cost of goods sold. Stock marts also carry months
-- with no sales, which the margin mart does not, so missing rows count as zero.
with margin as (
    select month_start, category, units_sold, cost_of_goods_sold
    from {{ ref('mart_margen_categoria') }}
),

turnover as (
    select month_start, category, units_sold, cost_of_goods_sold
    from {{ ref('mart_rotacion_inventario') }}
),

stockout as (
    select month_start, category, units_sold from {{ ref('mart_quiebre_stock') }}
),

cover as (
    select month_start, category, units_sold from {{ ref('mart_cobertura_stock') }}
),

compared as (
    select
        month_start,
        category,
        coalesce(margin.units_sold, 0) as margin_units,
        coalesce(turnover.units_sold, 0) as turnover_units,
        coalesce(stockout.units_sold, 0) as stockout_units,
        coalesce(cover.units_sold, 0) as cover_units,
        coalesce(margin.cost_of_goods_sold, 0) as margin_cogs,
        coalesce(turnover.cost_of_goods_sold, 0) as turnover_cogs
    from margin
    full outer join turnover using (month_start, category)
    full outer join stockout using (month_start, category)
    full outer join cover using (month_start, category)
)

select *
from compared
where margin_units != turnover_units
    or margin_units != stockout_units
    or margin_units != cover_units
    or margin_cogs != turnover_cogs
