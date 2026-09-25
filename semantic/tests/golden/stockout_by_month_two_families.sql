-- metric: stockout_rate
-- dimensions: month
-- filters: category_family in (electronics, home)
-- period: 2018-01 to 2018-09
with base as (
    select
        date_trunc(month_start, month) as month,
        units_backordered,
        units_sold
    from `olist-retail-portfolio.dbt_dev.mart_quiebre_stock`
    where month_start between date '2018-01-01' and date '2018-09-01'
        and category_family in ('electronics', 'home')
),

parts as (
    select
        month,
        sum(units_backordered) as units_backordered,
        sum(units_sold) as units_sold
    from base
    group by month
)

select
    month,
    units_backordered,
    units_sold,
    safe_divide(units_backordered, units_sold) as stockout_rate
from parts
order by month
