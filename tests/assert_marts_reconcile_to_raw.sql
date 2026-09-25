-- The margin mart must add up to the raw Olist tables month by month, read straight from
-- the source and bypassing staging, the facts and the category mapping: same units and
-- same revenue for every order that was not canceled or unavailable.
with raw as (
    select
        date_trunc(date(orders.order_purchase_timestamp), month) as month_start,
        count(*) as units,
        sum(cast(items.price as numeric)) as revenue
    from {{ source('olist', 'order_items') }} as items
    inner join {{ source('olist', 'orders') }} as orders using (order_id)
    where orders.order_status not in ('canceled', 'unavailable')
    group by month_start
),

mart as (
    select month_start, sum(units_sold) as units, sum(revenue) as revenue
    from {{ ref('mart_margen_categoria') }}
    group by month_start
)

select
    coalesce(raw.month_start, mart.month_start) as month_start,
    raw.units as raw_units,
    mart.units as mart_units,
    raw.revenue as raw_revenue,
    mart.revenue as mart_revenue
from raw
full outer join mart using (month_start)
where raw.units is distinct from mart.units or raw.revenue is distinct from mart.revenue
