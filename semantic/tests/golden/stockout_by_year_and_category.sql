-- metric: stockout_rate
-- dimensions: year, category
-- filters: none
-- period: 2017-01 to 2018-08
with base as (
    select
        date_trunc(month_start, year) as year,
        category,
        units_backordered,
        units_sold
    from `olist-retail-portfolio.dbt_dev.mart_quiebre_stock`
    where month_start between date '2017-01-01' and date '2018-08-01'
),

parts as (
    select
        year,
        category,
        sum(units_backordered) as units_backordered,
        sum(units_sold) as units_sold
    from base
    group by year, category
)

select
    year,
    category,
    units_backordered,
    units_sold,
    safe_divide(units_backordered, units_sold) as stockout_rate
from parts
order by year, category
