-- Each (product, seller) opens with exactly one positive initial_stock, dated on or
-- before its first sale or replenishment; replenishments only bring units in.
with by_pair as (
    select
        product_id,
        seller_id,
        countif(movement_type = 'initial_stock') as openings,
        min(if(movement_type = 'initial_stock', quantity, null)) as opening_quantity,
        min(if(movement_type = 'initial_stock', movement_date, null)) as opened_on,
        min(if(movement_type != 'initial_stock', movement_date, null)) as first_other_movement,
        countif(movement_type = 'replenishment' and quantity <= 0) as empty_replenishments
    from {{ ref('fct_movimiento_stock') }}
    group by product_id, seller_id
)

select *
from by_pair
where openings != 1
    or opening_quantity <= 0
    or first_other_movement < opened_on
    or empty_replenishments > 0
