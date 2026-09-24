-- The fact must neither drop nor duplicate order items on its joins: same row count and
-- same revenue as staging.
with staging as (
    select count(*) as lines, sum(price) as revenue from {{ ref('stg_order_items') }}
),

fact as (
    select count(*) as lines, sum(price) as revenue from {{ ref('fct_venta_linea') }}
)

select staging.*, fact.lines as fact_lines, fact.revenue as fact_revenue
from staging cross join fact
where staging.lines != fact.lines or staging.revenue != fact.revenue
