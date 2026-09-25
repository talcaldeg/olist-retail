-- metric: gross_margin_pct
-- dimensions: category_family
-- filters: none
-- period: 2018-01 to 2018-09
with base as (
    select
        category_family,
        gross_margin,
        revenue
    from `olist-retail-portfolio.dbt_dev.mart_margen_categoria`
    where month_start between date '2018-01-01' and date '2018-09-01'
),

parts as (
    select
        category_family,
        sum(gross_margin) as gross_margin,
        sum(revenue) as revenue
    from base
    group by category_family
)

select
    category_family,
    gross_margin,
    revenue,
    safe_divide(gross_margin, revenue) as gross_margin_pct
from parts
order by category_family
