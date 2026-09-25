-- metric: days_of_cover
-- dimensions: category_family
-- filters: none
-- period: 2017-01 to 2017-12
with base as (
    select
        category_family,
        month_start,
        date '2017-01-01' as period_start,
        date '2018-01-01' as period_end,
        closing_on_hand_units,
        units_sold
    from `olist-retail-portfolio.dbt_dev.mart_cobertura_stock`
    where month_start between date '2017-01-01' and date '2017-12-01'
),

parts as (
    select
        category_family,
        sum(if(month_start = date_sub(period_end, interval 1 month), closing_on_hand_units, 0)) as closing_on_hand_units,
        sum(units_sold) as units_sold,
        any_value(date_diff(period_end, period_start, day)) as days_in_period
    from base
    group by category_family
)

select
    category_family,
    closing_on_hand_units,
    units_sold,
    days_in_period,
    safe_divide(closing_on_hand_units, units_sold / days_in_period) as days_of_cover
from parts
order by category_family
