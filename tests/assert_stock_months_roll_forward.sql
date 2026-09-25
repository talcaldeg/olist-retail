-- The monthly stock positions must be a faithful roll-up of the ledger: each month opens
-- where the previous one closed (plus the initial stock in the pair's first month), and
-- each closing balance equals every movement up to the end of that month.
with positions as (
    select * from {{ ref('int_stock_par_mes') }}
),

rolled as (
    select
        product_id,
        seller_id,
        month_start,
        opening_units,
        units_opened,
        closing_units,
        lag(closing_units) over (
            partition by product_id, seller_id order by month_start
        ) as previous_closing
    from positions
),

ledger_to_date as (
    select
        positions.product_id,
        positions.seller_id,
        positions.month_start,
        sum(ledger.quantity) as ledger_balance
    from positions
    inner join {{ ref('int_stock_saldo') }} as ledger
        on ledger.product_id = positions.product_id
        and ledger.seller_id = positions.seller_id
        and ledger.movement_date <= last_day(positions.month_start)
    group by positions.product_id, positions.seller_id, positions.month_start
)

select rolled.*, ledger_to_date.ledger_balance
from rolled
left join ledger_to_date using (product_id, seller_id, month_start)
where rolled.opening_units != coalesce(rolled.previous_closing, 0) + rolled.units_opened
    or rolled.closing_units is distinct from ledger_to_date.ledger_balance
