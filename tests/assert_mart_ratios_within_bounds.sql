-- Ratios that cannot leave their range whatever the seeds say: a share of units
-- backordered is between 0 and 1, margin cannot exceed revenue, and stock on hand,
-- turnover and cover are never negative (backorders floor on-hand stock at zero).
select 'stockout_rate' as ratio, month_start, category, stockout_rate as value
from {{ ref('mart_quiebre_stock') }}
where stockout_rate not between 0 and 1

union all

select 'gross_margin_pct', month_start, category, gross_margin_pct
from {{ ref('mart_margen_categoria') }}
where gross_margin_pct > 1

union all

select 'inventory_turnover', month_start, category, inventory_turnover
from {{ ref('mart_rotacion_inventario') }}
where inventory_turnover < 0 or avg_inventory_value < 0

union all

select 'days_of_cover', month_start, category, days_of_cover
from {{ ref('mart_cobertura_stock') }}
where days_of_cover < 0 or closing_on_hand_units < 0
