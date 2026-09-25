-- One row per (product, seller) and month, from the pair's first month to the last month
-- with sales in the data. A pair that stops selling keeps its stock on the books until
-- the end: unsold stock is part of what turnover and cover measure. Receipts that would
-- arrive after the last month fall outside the window and are left out.
--
-- The opening balance includes the initial stock, which arrives on day 1 of the pair's
-- first month, so the first month is not averaged against an empty shelf.
with ledger as (
    select * from {{ ref('int_stock_saldo') }}
),

last_month as (
    select date_trunc(max(purchase_date), month) as month_start
    from {{ ref('fct_venta_linea') }}
    where consumes_stock
),

pairs as (
    select
        product_id,
        seller_id,
        any_value(category) as category,
        any_value(unit_cost) as unit_cost,
        date_trunc(min(movement_date), month) as first_month
    from ledger
    group by product_id, seller_id
),

spine as (
    select pairs.*, month_start
    from pairs
    cross join last_month
    cross join unnest(generate_date_array(
        pairs.first_month, last_month.month_start, interval 1 month
    )) as month_start
),

monthly as (
    select
        product_id,
        seller_id,
        date_trunc(movement_date, month) as month_start,
        sum(if(movement_type = 'initial_stock', quantity, 0)) as units_opened,
        sum(if(movement_type = 'replenishment', quantity, 0)) as units_received,
        sum(if(movement_type = 'sale', -quantity, 0)) as units_sold,
        countif(movement_type = 'sale' and balance_after < 0) as units_backordered
    from ledger
    group by product_id, seller_id, month_start
),

flows as (
    select
        spine.product_id,
        spine.seller_id,
        spine.category,
        spine.unit_cost,
        spine.month_start,
        coalesce(monthly.units_opened, 0) as units_opened,
        coalesce(monthly.units_received, 0) as units_received,
        coalesce(monthly.units_sold, 0) as units_sold,
        coalesce(monthly.units_backordered, 0) as units_backordered
    from spine
    left join monthly using (product_id, seller_id, month_start)
),

balances as (
    select
        *,
        sum(units_opened + units_received - units_sold) over (
            partition by product_id, seller_id
            order by month_start
            rows between unbounded preceding and current row
        ) as closing_units
    from flows
)

select
    product_id,
    seller_id,
    category,
    month_start,
    unit_cost,
    closing_units - units_received + units_sold as opening_units,
    units_opened,
    units_received,
    units_sold,
    units_backordered,
    closing_units,
    -- A negative balance is owed to customers, not held: on-hand stock floors at zero
    -- per pair, before any aggregation, so one pair's backorders never hide another's
    -- shelf.
    greatest(closing_units - units_received + units_sold, 0) as opening_on_hand,
    greatest(closing_units, 0) as closing_on_hand
from balances
