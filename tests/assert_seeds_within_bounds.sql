-- Guards the hand-edited seeds: a cost ratio outside (0, 1) would book a loss or a free
-- product on every sale, and the three seeds must place each category in one family.
select category, 'cost_ratio out of (0, 1)' as problem
from {{ ref('category_cost') }}
where cost_ratio <= 0 or cost_ratio >= 1

union all

select category, 'months_of_cover not positive'
from {{ ref('initial_stock') }}
where months_of_cover <= 0

union all

select category, 'lead_time_days outside 1-180'
from {{ ref('lead_time') }}
where lead_time_days not between 1 and 180

union all

select category_cost.category, 'family differs between seeds'
from {{ ref('category_cost') }} as category_cost
full outer join {{ ref('initial_stock') }} as initial_stock using (category)
full outer join {{ ref('lead_time') }} as lead_time using (category)
where category_cost.family is null
    or initial_stock.family is null
    or lead_time.family is null
    or category_cost.family != initial_stock.family
    or category_cost.family != lead_time.family
