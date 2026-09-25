-- The stock ledger: every movement of fct_movimiento_stock with the balance of its
-- (product, seller) right after it. Within a day, receipts come before sales, so a unit
-- that arrives the same day it is sold counts as in stock. A sale that leaves the
-- balance below zero was served from stock the seller did not have: a backorder.
with movements as (
    select * from {{ ref('fct_movimiento_stock') }}
),

ordered as (
    select
        *,
        case movement_type
            when 'initial_stock' then 0
            when 'replenishment' then 1
            else 2
        end as intraday_order
    from movements
)

select
    movement_id,
    product_id,
    seller_id,
    category,
    movement_date,
    movement_type,
    quantity,
    unit_cost,
    sale_line_id,
    sum(quantity) over (
        partition by product_id, seller_id
        order by movement_date, intraday_order, movement_id
        rows between unbounded preceding and current row
    ) as balance_after
from ordered
