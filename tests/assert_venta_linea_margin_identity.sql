-- Gross margin is price minus unit cost, and a unit always costs something.
select sale_line_id, price, unit_cost, gross_margin
from {{ ref('fct_venta_linea') }}
where gross_margin != price - unit_cost
    or unit_cost <= 0
