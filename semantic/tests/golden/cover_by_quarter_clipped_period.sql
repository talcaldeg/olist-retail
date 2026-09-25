-- metric: days_of_cover
-- dimensions: quarter, category_family
-- filters: none
-- period: 2017-02 to 2017-07
with base as (
    select
        date_trunc(month_start, quarter) as quarter,
        category_family,
        month_start,
        greatest(date_trunc(month_start, quarter), date '2017-02-01') as period_start,
        least(date_add(date_trunc(month_start, quarter), interval 1 quarter), date '2017-08-01') as period_end,
        closing_on_hand_units,
        units_sold
    from `olist-retail-portfolio.dbt_dev.mart_cobertura_stock`
    where month_start between date '2017-02-01' and date '2017-07-01'
),

parts as (
    select
        quarter,
        category_family,
        sum(if(month_start = date_sub(period_end, interval 1 month), closing_on_hand_units, 0)) as closing_on_hand_units,
        sum(units_sold) as units_sold,
        any_value(date_diff(period_end, period_start, day)) as days_in_period
    from base
    group by quarter, category_family
)

select
    quarter,
    category_family,
    closing_on_hand_units,
    units_sold,
    days_in_period,
    safe_divide(closing_on_hand_units, units_sold / days_in_period) as days_of_cover
from parts
order by quarter, category_family
