"""Live tests: the compiled SQL, run on BigQuery, agrees with the marts and with the
figures published in docs/marts.md.

Skipped unless OLIST_LIVE_TESTS=1, since they need credentials for the GCP project:

    OLIST_LIVE_TESTS=1 python -m pytest semantic/tests
"""

from __future__ import annotations

import datetime as dt
import math
import os
from collections import defaultdict

import pytest

from semantic.compiler import consultar_metrica, load_spec

pytestmark = pytest.mark.skipif(
    os.environ.get("OLIST_LIVE_TESTS") != "1", reason="set OLIST_LIVE_TESTS=1 to query BigQuery"
)

SPEC = load_spec()
FULL = {"start": f"{SPEC.data_range[0]:%Y-%m}", "end": f"{SPEC.data_range[1]:%Y-%m}"}

# metric -> the mart column that holds the same ratio at month x category grain
MART_RATIO = {
    "gross_margin_pct": "gross_margin_pct",
    "inventory_turnover": "inventory_turnover_annualized",
    "stockout_rate": "stockout_rate",
    "days_of_cover": "days_of_cover",
}


@pytest.fixture(scope="module")
def client():
    from google.cloud import bigquery

    return bigquery.Client(project=SPEC.project)


def mart_rows(client, model):
    sql = f"select * from `{SPEC.project}.{SPEC.dataset}.{model}`"
    return [dict(r.items()) for r in client.query(sql).result()]


def close(a, b, rel=1e-9):
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=1e-9)


def one(metric, **kwargs):
    rows = consultar_metrica(metric, **kwargs).rows
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize("metric", sorted(MART_RATIO))
def test_month_by_category_equals_the_mart(client, metric):
    """At the mart's own grain, summing the parts and dividing again gives back the ratio
    column of every row, nulls included."""
    result = consultar_metrica(metric, ["month", "category"], period=FULL, client=client)
    got = {(r["month"], r["category"]): r[metric] for r in result.rows}
    model = SPEC.metrics[metric].model
    expected = {
        (r["month_start"].isoformat(), r["category"]): r[MART_RATIO[metric]]
        for r in mart_rows(client, model)
    }
    assert got.keys() == expected.keys()
    wrong = [k for k in got if not close(got[k], expected[k])]
    assert not wrong, f"{len(wrong)} rows differ, e.g. {wrong[:3]}"


def test_cover_by_quarter_uses_last_month_stock_and_calendar_days(client):
    """Rebuild days of cover per quarter and family in Python from the monthly mart rows
    and compare: stock from the quarter's last month, sales over the quarter's days."""
    period = {"start": "2017-02", "end": "2018-08"}  # starts and ends mid-quarter
    result = consultar_metrica(
        "days_of_cover", ["quarter", "category_family"], period=period, client=client
    )
    start, end = dt.date(2017, 2, 1), dt.date(2018, 8, 1)
    stock, sold, months = defaultdict(float), defaultdict(float), defaultdict(set)
    rows = [r for r in mart_rows(client, "mart_cobertura_stock") if start <= r["month_start"] <= end]
    for r in rows:
        m = r["month_start"]
        q = dt.date(m.year, 3 * ((m.month - 1) // 3) + 1, 1)
        months[q].add(m)
    last = {q: max(ms) for q, ms in months.items()}
    for r in rows:
        m = r["month_start"]
        q = dt.date(m.year, 3 * ((m.month - 1) // 3) + 1, 1)
        key = (q.isoformat(), r["category_family"])
        sold[key] += float(r["units_sold"])
        if m == last[q]:
            stock[key] += float(r["closing_on_hand_units"])

    def days(q):
        first = max(q, start)
        after = min(dt.date(q.year + (q.month + 2) // 12, (q.month + 2) % 12 + 1, 1),
                    dt.date(2018, 9, 1))
        return (after - first).days

    assert {r["days_in_period"] for r in result.rows if r["quarter"] == "2017-01-01"} == {59}
    for r in result.rows:
        key = (r["quarter"], r["category_family"])
        q = dt.date.fromisoformat(r["quarter"])
        assert r["days_in_period"] == days(q)
        expected = stock[key] / (sold[key] / days(q)) if sold[key] else None
        assert close(r["days_of_cover"], expected), key


def test_totals_reconcile_with_the_raw_data(client):
    row = one("gross_margin_pct", period=FULL, client=client)
    assert round(row["revenue"], 2) == 13_494_400.74


def test_headline_figures_of_docs_marts(client):
    assert round(one("gross_margin_pct", period=FULL, client=client)["gross_margin_pct"], 3) == 0.395
    assert round(one("stockout_rate", period=FULL, client=client)["stockout_rate"], 3) == 0.162
    assert round(one("inventory_turnover", client=client)["inventory_turnover"], 2) == 2.45
    assert round(one("days_of_cover", period="2018-08", client=client)["days_of_cover"]) == 203

    computers = {"category": "computers_accessories"}
    assert round(one("stockout_rate", filters=computers, period="2018-03", client=client)["stockout_rate"], 2) == 0.37
    assert round(one("days_of_cover", filters=computers, period="2018-03", client=client)["days_of_cover"]) == 90
