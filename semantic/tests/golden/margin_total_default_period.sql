-- metric: gross_margin_pct
-- dimensions: none
-- filters: none
-- period: 2017-01 to 2018-08
with base as (
    select
        gross_margin,
        revenue
    from `olist-retail-portfolio.dbt_dev.mart_margen_categoria`
    where month_start between date '2017-01-01' and date '2018-08-01'
),

parts as (
    select
        sum(gross_margin) as gross_margin,
        sum(revenue) as revenue
    from base
)

select
    gross_margin,
    revenue,
    safe_divide(gross_margin, revenue) as gross_margin_pct
from parts
