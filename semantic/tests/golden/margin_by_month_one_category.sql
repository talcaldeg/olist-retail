-- metric: gross_margin_pct
-- dimensions: month
-- filters: category in (health_beauty)
-- period: 2018-01 to 2018-03
with base as (
    select
        date_trunc(month_start, month) as month,
        gross_margin,
        revenue
    from `olist-retail-portfolio.dbt_dev.mart_margen_categoria`
    where month_start between date '2018-01-01' and date '2018-03-01'
        and category = 'health_beauty'
),

parts as (
    select
        month,
        sum(gross_margin) as gross_margin,
        sum(revenue) as revenue
    from base
    group by month
)

select
    month,
    gross_margin,
    revenue,
    safe_divide(gross_margin, revenue) as gross_margin_pct
from parts
order by month
