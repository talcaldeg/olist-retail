-- Every stock-consuming sale line leaves exactly one unit, and nothing else leaves stock:
-- the sale movements and the consuming sale lines are the same set.
with sale_movements as (
    select sale_line_id
    from {{ ref('fct_movimiento_stock') }}
    where movement_type = 'sale'
),

consuming_lines as (
    select sale_line_id
    from {{ ref('fct_venta_linea') }}
    where consumes_stock
)

select
    coalesce(sale_movements.sale_line_id, consuming_lines.sale_line_id) as sale_line_id,
    sale_movements.sale_line_id is null as missing_movement
from sale_movements
full outer join consuming_lines using (sale_line_id)
where sale_movements.sale_line_id is null or consuming_lines.sale_line_id is null
