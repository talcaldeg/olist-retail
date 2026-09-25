"""Offline tests of the compiler: golden SQL files and the questions it must reject.

The golden files in golden/ are the reviewed SQL for each case. A change to the compiler
that alters any of them fails here until the new SQL is reviewed and regenerated with

    UPDATE_GOLDEN=1 python -m pytest semantic/tests
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from semantic.compiler import SemanticError, compile_query, listar_metricas, load_spec

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
SPEC = load_spec(env={})  # ignore local overrides: golden files name the default dataset

# name -> (metric, dimensions, filters, period)
CASES = {
    "margin_total_default_period": ("gross_margin_pct", [], {}, None),
    "margin_by_family_2018": ("gross_margin_pct", ["category_family"], {}, "2018"),
    "margin_by_month_one_category": (
        "gross_margin_pct", ["month"], {"category": "health_beauty"}, "2018-Q1",
    ),
    "turnover_total_default_period": ("inventory_turnover", [], {}, None),
    "turnover_by_quarter_and_family": (
        "inventory_turnover", ["quarter", "category_family"], {}, {"start": "2017-01", "end": "2018-08"},
    ),
    "stockout_by_month_two_families": (
        "stockout_rate", ["month"], {"category_family": ["electronics", "home"]}, "2018",
    ),
    "stockout_by_year_and_category": ("stockout_rate", ["year", "category"], {}, None),
    "cover_one_month": ("days_of_cover", [], {}, "2018-08"),
    "cover_by_category_one_month": (
        "days_of_cover", ["category"], {"category": "computers_accessories"}, "2018-03",
    ),
    "cover_by_quarter_clipped_period": (
        "days_of_cover", ["quarter", "category_family"], {}, {"start": "2017-02", "end": "2017-07"},
    ),
    "cover_whole_year": ("days_of_cover", ["category_family"], {}, "2017"),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_golden_sql(name):
    metric, dimensions, filters, period = CASES[name]
    sql = compile_query(metric, dimensions, filters, period, spec=SPEC)
    path = GOLDEN_DIR / f"{name}.sql"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(sql, encoding="utf-8", newline="\n")
    assert path.exists(), f"missing golden file {path.name}; run with UPDATE_GOLDEN=1"
    assert sql == path.read_text(encoding="utf-8")


def test_every_golden_file_has_a_case():
    assert {p.stem for p in GOLDEN_DIR.glob("*.sql")} == set(CASES)


def test_same_question_same_sql():
    kwargs = dict(dimensions=["category_family", "month"], filters={"category_family": ["home", "electronics"]})
    a = compile_query("stockout_rate", period="2018", spec=SPEC, **kwargs)
    # "2018" is clipped to the last month with data, so it equals the explicit range.
    b = compile_query("stockout_rate", period={"start": "2018-01", "end": "2018-09"}, spec=SPEC, **kwargs)
    assert a == b
    # Filter values are sorted, so their order in the question does not change the SQL.
    c = compile_query(
        "stockout_rate", ["category_family", "month"],
        {"category_family": ["electronics", "home"]}, "2018", spec=SPEC,
    )
    assert a == c


@pytest.mark.parametrize("metric", sorted(SPEC.metrics))
def test_ratio_column_of_the_mart_is_never_read(metric):
    """The ratio is rebuilt from its parts: the mart's ratio column appears only as the
    output alias, never in the select that reads the mart."""
    sql = compile_query(metric, ["quarter", "category_family"], spec=SPEC)
    base = sql.split("with base as (")[1].split("),\n\nparts as")[0]
    assert metric not in base
    assert re.findall(rf"\b{metric}\b", sql) == [metric, metric]  # header and alias
    for forbidden in ("avg(", "_annualized"):
        assert forbidden not in sql


def test_listar_metricas_exposes_the_four_metrics_and_their_values():
    catalog = listar_metricas(SPEC)
    assert [m["name"] for m in catalog["metrics"]] == [
        "gross_margin_pct", "inventory_turnover", "stockout_rate", "days_of_cover",
    ]
    dims = {d["name"]: d for d in catalog["dimensions"]}
    assert len(dims["category"]["values"]) == 74
    assert len(dims["category_family"]["values"]) == 10


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(metric="net_profit"), "unknown metric"),
        (dict(metric="gross_margin"), "Did you mean gross_margin_pct"),
        (dict(metric="stockout_rate", dimensions=["seller"]), "unknown dimension"),
        (dict(metric="stockout_rate", dimensions=["customer_state"]), "unknown dimension"),
        (dict(metric="stockout_rate", dimensions=["month", "quarter"]), "one time grain"),
        (dict(metric="stockout_rate", dimensions=["month", "month"]), "repeated"),
        (dict(metric="stockout_rate", filters={"category": "helth_beauty"}), "health_beauty"),
        (dict(metric="stockout_rate", filters={"category_family": []}), "no values"),
        (dict(metric="stockout_rate", filters={"month": "2018-01"}), "through period"),
        (dict(metric="stockout_rate", filters={"seller_id": "x"}), "unknown filter"),
        (dict(metric="stockout_rate", period="2019"), "no data"),
        (dict(metric="stockout_rate", period="2015-Q4"), "no data"),
        (dict(metric="stockout_rate", period="2018-13"), "not YYYY-MM"),
        (dict(metric="stockout_rate", period="last quarter"), "not YYYY-MM"),
        (dict(metric="stockout_rate", period={"start": "2018-05", "end": "2018-02"}), "after it ends"),
        (dict(metric="stockout_rate", period={"start": "2016-01", "end": "2016-12"}), "beyond the data"),
        (dict(metric="stockout_rate", period={"start": "2018-01"}), "start and end"),
        (dict(metric="stockout_rate", filters={"category": "x' or '1'='1"}), "is not a category"),
    ],
)
def test_rejected_questions(kwargs, message):
    with pytest.raises(SemanticError, match=re.escape(message)):
        compile_query(spec=SPEC, **kwargs)


def test_year_and_quarter_are_clipped_to_the_data():
    sql = compile_query("stockout_rate", period="2016", spec=SPEC)
    assert "between date '2016-09-01' and date '2016-12-01'" in sql
    sql = compile_query("days_of_cover", period="2018-Q3", spec=SPEC)
    assert "date '2018-07-01' as period_start" in sql
    assert "date '2018-10-01' as period_end" in sql  # September is the last month
