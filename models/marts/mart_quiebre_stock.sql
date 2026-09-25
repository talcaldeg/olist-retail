-- Question: how often is a customer sold something the seller does not have?
-- Grain: month x category. A unit is backordered when its sale takes the pair's balance
-- below zero (int_stock_saldo). Stockout rate = backordered units / units sold.
with positions as (
    select * from {{ ref('int_stock_par_mes') }}
),

families as (
    select category, family as category_family from {{ ref('category_cost') }}
)

select
    positions.month_start,
    positions.category,
    families.category_family,
    {{ in_reporting_window('positions.month_start') }} as in_reporting_window,
    sum(positions.units_sold) as units_sold,
    sum(positions.units_backordered) as units_backordered,
    safe_divide(sum(positions.units_backordered), sum(positions.units_sold))
        as stockout_rate,
    countif(positions.units_sold > 0) as pairs_selling,
    countif(positions.units_backordered > 0) as pairs_with_backorders,
    countif(positions.closing_units < 0) as pairs_short_at_close,
    sum(greatest(-positions.closing_units, 0)) as units_owed_at_close
from positions
inner join families using (category)
group by positions.month_start, positions.category, families.category_family
