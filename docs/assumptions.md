# Assumptions behind cost and inventory

Olist publishes what customers bought, from whom and at what price. It does not publish
what those products cost the seller or how much stock the seller held. No public retail
dataset does: Favorita, M5 and Online Retail II were checked and have the same gap.
Without cost and stock there is no margin, no stock turnover and no days of cover, which
are the questions a retail business actually asks.

This project does not drop those questions. It fills the gap with three small, versioned
assumptions in `seeds/`, applies them the same way everywhere, and says so here. Every
figure that depends on them is synthetic. Every figure that does not (units, revenue,
freight, delivery times, category mix) is real.

## What is real and what is assumed

| Measure | Source | Real or assumed |
|---|---|---|
| Units, revenue, freight, order status, dates | Olist | Real |
| Which categories sell, when, where | Olist | Real |
| Unit cost, gross margin | `category_cost.csv` applied to real prices | Assumed |
| Stock on hand, stockouts, stock value, turnover | Simulated from real sales with `initial_stock.csv` and `lead_time.csv` | Assumed |

A consequence worth stating plainly: because unit cost is a fixed share of price, the
margin *rate* of a category is exactly `1 - cost_ratio`. A dashboard showing fashion with a
higher margin rate than electronics is showing the assumption, not a finding. What the
data does decide is the mix: how much of the revenue, and therefore of the margin, comes
from each category.

## The three seeds

All three are keyed by category (74 keys: the 71 English names Olist provides, two
categories Olist left untranslated, and `uncategorized` for the 610 products with no
category). Categories are grouped into ten families and every category in a family gets
the family's value, so each value is one decision and not 74. To change an assumption,
edit the CSV and run `dbt build`; `tests/assert_seeds_within_bounds.sql` rejects a cost
ratio outside (0, 1), a non-positive cover, a lead time outside 1-180 days and a category
placed in different families across the three files.

| Family | Categories (examples) | Cost ratio | Months of cover | Lead time (days) |
|---|---|---|---|---|
| electronics | computers, telephony, audio, consoles_games | 0.80 | 2.0 | 30 |
| appliances | home_appliances, small_appliances, air_conditioning | 0.75 | 2.0 | 25 |
| food | food, drinks, flowers | 0.70 | 1.0 | 7 |
| tools_construction | garden_tools, auto, construction_tools_* | 0.65 | 2.5 | 20 |
| books_media | books_*, stationery, dvds_blu_ray | 0.65 | 2.0 | 10 |
| leisure | sports_leisure, toys, pet_shop, musical_instruments | 0.60 | 2.0 | 30 |
| other | market_place, security_and_services, uncategorized | 0.60 | 1.5 | 20 |
| home | bed_bath_table, furniture_*, housewares | 0.55 | 2.0 | 20 |
| beauty_health | health_beauty, perfumery, baby | 0.55 | 1.5 | 15 |
| fashion | fashion_*, watches_gifts, luggage_accessories | 0.45 | 3.0 | 45 |

The values are illustrative and were not taken from any published benchmark. They encode
orderings that are widely held in retail and easy to argue about in a review:

- **Cost ratio.** Commodity electronics and appliances sell on thin margins; fashion,
  beauty and home goods carry wide ones; food sits in between.
- **Months of cover.** Perishables are held short; slow, bulky or seasonal lines (tools,
  fashion) are held longer.
- **Lead time.** Imported or made-to-order goods (fashion collections, electronics,
  leisure) take weeks; food and books are restocked within days.

## How the seeds are applied

**Unit cost.** For each product and seller, `unit_cost = cost_ratio x average selling
price` of that pair (`int_producto_vendedor`). Using the pair's average rather than each
line's price means one standard cost per item, as a real inventory ledger would have: a
line sold on discount shows a thinner margin (334 shipped lines sell below standard cost,
306 of them electronics), and sales and stock are valued with the same number.

**Stock.** Stock is held per product and seller, because 1,225 products are sold by more
than one seller. `fct_movimiento_stock` simulates three kinds of movement:

1. *Opening stock*, on the first day of the pair's first month with sales, equal to
   `months_of_cover x` the pair's average monthly demand over its active months (at least
   one unit).
2. *Replenishment*, a periodic-review policy: on the first day of every following month
   in which the pair still sells, the seller reorders what it sold the month before, and
   the order arrives `lead_time_days` later.
3. *Sale*, one unit out on the purchase date of every order that was not canceled or
   unavailable.

Summing the quantities up to a date gives stock on hand. A negative balance is a stockout
where the order was accepted and served late (a backorder); it is kept rather than capped
because stockouts are one of the things this project measures.

## What the assumptions produce

With the values above (build of 24-Sep-2026): 34,212 product-seller pairs with stock,
16.2% of units sold while the pair was out of stock, and 653 pairs ending the period
below zero. That stockout rate is high for a real retailer and has an identifiable cause:
Olist grew several-fold between early 2017 and 2018, and a policy that only replaces last
month's sales always lags a growing demand. The marts can show that, and the seeds are the
lever to test a different policy.

## Known limits

- **Look-ahead.** Opening stock is sized with the pair's demand over its whole life, which
  a real seller would not have known on day one. It is the price of having a plausible
  opening balance for 34,000 pairs without inventing a forecast.
- **One unit per line.** Olist records one row per unit sold, so every sale moves one unit.
- **No returns, write-offs or transfers between sellers.** Canceled orders never consume
  stock; delivered orders are never reversed.
- **Receipts after the last sale.** A pair stops reordering after its last month with
  sales, and a replenishment ordered that month can arrive after the dataset ends.
