# Marts: four business questions

Each mart answers one question at month x category grain and stores the additive parts of
its ratio next to the ratio. To report a quarter or a category family, sum the parts and
divide again; averaging the ratio column gives a wrong answer. Cost and stock rest on the
synthetic seeds described in [assumptions.md](assumptions.md).

| Mart | Question | Ratio | Parts |
|---|---|---|---|
| `mart_margen_categoria` | Which categories make money? | `gross_margin_pct` | `gross_margin`, `revenue` |
| `mart_rotacion_inventario` | How fast does stock turn? | `inventory_turnover` | `cost_of_goods_sold`, `avg_inventory_value` |
| `mart_quiebre_stock` | How often is a sale not in stock? | `stockout_rate` | `units_backordered`, `units_sold` |
| `mart_cobertura_stock` | How many days does the shelf last? | `days_of_cover` | `closing_on_hand_units`, `units_sold`, `days_in_month` |

## Definitions that are choices

- **Shipped lines only.** Canceled and unavailable orders are neither revenue nor stock
  movements. Revenue is the item price; freight is excluded.
- **On-hand stock floors at zero per pair, before aggregating.** A seller that owes three
  units to customers does not hold minus three units, and summing signed balances across
  pairs would let one pair's backorders hide another pair's shelf.
- **Average inventory** of a month is the mean of opening and closing on-hand stock. The
  opening of a pair's first month includes its initial stock, which arrives on day 1.
- **Stock stays on the books after a pair stops selling.** Nothing in Olist says the
  seller cleared it, so it keeps weighing on turnover and cover until the end of the data.
- **Reporting window.** Olist has three sparse months in 2016 and one sale in September
  2018. Marts keep every month so they reconcile with the raw data, and
  `in_reporting_window` flags 2017-01 to 2018-08 as the comparable months.

## How the numbers were checked

Four singular tests run on every `dbt build`:

- `assert_marts_reconcile_to_raw`: units and revenue per month equal a query on the raw
  Olist tables that bypasses staging, the facts and the category mapping.
- `assert_marts_agree_with_each_other`: the four marts count the same units for every
  month and category, and margin and turnover report the same cost of goods sold, although
  one side is built from sale lines and the other from stock movements.
- `assert_stock_months_roll_forward`: every month opens where the previous one closed, and
  every closing balance equals the ledger up to that date.
- `assert_mart_ratios_within_bounds`: rates stay in their range whatever the seeds say.

One cell was also checked by hand: `health_beauty` in March 2018 has 670 units and
BRL 89,759.44 of revenue both in the mart and in a direct query on the raw tables by the
Portuguese category name.

## What the marts show (build of 24-Sep-2026)

- **Totals.** 112,101 shipped units and BRL 13,494,400.74 of revenue, equal to the raw
  data to the cent. Gross margin is 39.5% overall.
- **Stockouts and idle stock at the same time.** 16.2% of units were sold while the pair
  was out of stock, yet at the end of August 2018 the shelf held 203 days of that month's
  sales, and inventory turned 2.45 times a year over the reporting window.
- **Why both.** The stock sits in the long tail. Of the 47,333 units on hand at the end
  of August 2018, 85% belonged to pairs that sold nothing that month and 61% to pairs whose
  no sale since April. Meanwhile the pairs that do sell run out: in March 2018,
  `computers_accessories` backordered 37% of its units with 90 days of cover on paper.
  The replenishment policy reorders last month's sales for every pair alike, so it
  neither clears slow stock nor keeps up with growing items.

These figures depend on the seeds: the pattern (stockouts next to idle stock) comes from
the real demand, while the levels come from the assumed cover and lead times.
