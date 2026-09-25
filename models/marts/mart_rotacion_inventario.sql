-- Question: how many times a year does each category turn its inventory?
-- Grain: month x category. Turnover = cost of goods sold / average inventory at cost,
-- where the month's average inventory is the mean of opening and closing on-hand stock.
-- The annualized figure multiplies the monthly one by 12; across several months, sum the
-- parts and divide again rather than averaging this column.
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
    sum(positions.units_sold * positions.unit_cost) as cost_of_goods_sold,
    sum((positions.opening_on_hand + positions.closing_on_hand) / 2 * positions.unit_cost)
        as avg_inventory_value,
    safe_divide(
        sum(positions.units_sold * positions.unit_cost),
        sum((positions.opening_on_hand + positions.closing_on_hand) / 2 * positions.unit_cost)
    ) as inventory_turnover,
    12 * safe_divide(
        sum(positions.units_sold * positions.unit_cost),
        sum((positions.opening_on_hand + positions.closing_on_hand) / 2 * positions.unit_cost)
    ) as inventory_turnover_annualized
from positions
inner join families using (category)
group by positions.month_start, positions.category, families.category_family
