# Semantic layer: questions in, SQL out

`semantic/metrics.yml` defines the only four metrics the project answers, one per mart,
and the dimensions they can be cut by. `semantic/compiler.py` turns a question into SQL
over the marts; no language model is involved, and the same question always compiles to
the same SQL.

| Metric | Mart | Numerator | Denominator |
|---|---|---|---|
| `gross_margin_pct` | `mart_margen_categoria` | sum of `gross_margin` | sum of `revenue` |
| `inventory_turnover` | `mart_rotacion_inventario` | 12 x sum of `cost_of_goods_sold` | sum of `avg_inventory_value` |
| `stockout_rate` | `mart_quiebre_stock` | sum of `units_backordered` | sum of `units_sold` |
| `days_of_cover` | `mart_cobertura_stock` | `closing_on_hand_units` of the period's last month | sum of `units_sold` / days in the period |

A question is a metric plus optional dimensions (`month`, `quarter` or `year`, and
`category`, `category_family`), filters on the categorical dimensions, and a period
(`2018`, `2018-Q1`, `2018-03` or a start and end month; by default the reporting window,
2017-01 to 2018-08).

```python
from semantic import compile_query, consultar_metrica, listar_metricas

print(compile_query("stockout_rate", ["quarter"], {"category_family": "electronics"}, "2018"))
result = consultar_metrica("days_of_cover", ["category"], period="2018-08")
```

From the shell: `python -m semantic` lists the metrics, and
`python -m semantic days_of_cover --by quarter --where category_family=home --period 2018 --sql`
prints the SQL without running it.

## Ratios are recomputed, never averaged

The compiler reads only the parts of each ratio from the mart, sums them over the
requested grouping and divides again. Two metrics need more than a sum:

- **Turnover over several months** is the period's cost of goods sold over its mean
  inventory, scaled to a year. The number of months cancels out, so it is 12 x (sum of
  cost) / (sum of monthly average inventories), for a month, a quarter or 20 months alike.
- **Cover over several months** takes the stock at the end of the period (the closing
  units of its last calendar month) and divides by the average daily sales over the
  period's calendar days, clipped to the requested months. February to March 2017 has 59
  days, whatever quarter it falls in.

## What gets rejected

An unknown metric or dimension, two time grains at once, a filter value that is not in
`seeds/category_cost.csv` (with a suggestion for typos), a filter on time instead of a
period, or a period outside the data (2016-09 to 2018-09). A year or quarter that only
overlaps the data is clipped to it; an explicit start and end must fall inside it.

## Tests

- **Golden files** (`semantic/tests/golden/`): the reviewed SQL for eleven questions.
  Any change in the generated SQL fails until the files are regenerated with
  `UPDATE_GOLDEN=1 python -m pytest` and the diff is reviewed. Runs on every push.
- **Rejections**: eighteen questions that must fail, including an injection attempt in a
  filter value.
- **Live** (`OLIST_LIVE_TESTS=1`, in the monthly refresh): at month x category grain the
  compiled SQL reproduces the ratio column of all four marts row by row, nulls included;
  cover by quarter matches a rebuild in Python from the monthly rows; and the figures in
  [marts.md](marts.md) come out the same (39.5% margin, 16.2% stockouts, 2.45 turns a
  year, 203 days of cover in August 2018, and 37% stockouts with 90 days of cover for
  `computers_accessories` in March 2018).
