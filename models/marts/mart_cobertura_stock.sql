-- Question: how many days of sales does the stock on hand cover?
-- Grain: month x category. Days of cover = closing on-hand units / average daily units
-- sold in the month. Null when the category sold nothing that month: stock with no
-- demand has no finite cover, and the value tied up in it still shows in
-- closing_inventory_value.
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
    extract(day from last_day(positions.month_start)) as days_in_month,
    sum(positions.units_sold) as units_sold,
    sum(positions.closing_on_hand) as closing_on_hand_units,
    sum(positions.closing_on_hand * positions.unit_cost) as closing_inventory_value,
    countif(positions.closing_on_hand > 0 and positions.units_sold = 0)
        as pairs_stocked_without_sales,
    safe_divide(
        sum(positions.closing_on_hand),
        sum(positions.units_sold) / extract(day from last_day(positions.month_start))
    ) as days_of_cover
from positions
inner join families using (category)
group by positions.month_start, positions.category, families.category_family
