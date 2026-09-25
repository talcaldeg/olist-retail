"""Compile a metric question into BigQuery SQL over the marts, and run it.

A question is {metric, dimensions, filters, period}. Everything it may name lives in
semantic/metrics.yml; anything else raises SemanticError before a query is built. The
compiler is deterministic (same question, same SQL, byte for byte), which is what the
golden tests in semantic/tests pin down.

Ratios are never read from the marts. The compiler selects the additive parts, sums them
over the requested grouping and divides again. Stocks (aggregation `last`) take the value
of the last calendar month of each period; daily rates (`per_day`) divide by the calendar
days of the period, clipped to the requested months.

    >>> sql = compile_query("stockout_rate", dimensions=["quarter"], period="2018")
    >>> result = consultar_metrica("stockout_rate", ["category_family"], period="2018-03")

From the shell: python -m semantic [metric] [--by DIM] [--where DIM=V1,V2] [--period P] [--sql]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import os
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

SPEC_PATH = Path(__file__).resolve().parent / "metrics.yml"
REPO_ROOT = SPEC_PATH.parent.parent
MAX_BYTES_BILLED = 1_000_000_000  # same guard as profiles.yml

TIME_GRAINS = ("month", "quarter", "year")
AGGREGATIONS = ("sum", "last")


class SemanticError(ValueError):
    """The question cannot be expressed with the metrics and dimensions defined."""


# --- spec -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Part:
    column: str
    aggregation: str
    per_day: bool = False


@dataclass(frozen=True)
class Metric:
    name: str
    label: str
    question: str
    description: str
    model: str
    numerator: Part
    denominator: Part
    multiplier: int
    unit: str


@dataclass(frozen=True)
class Dimension:
    name: str
    kind: str  # "time" or "categorical"
    description: str
    grain: str | None = None
    column: str | None = None
    values: frozenset[str] | None = None


@dataclass(frozen=True)
class Spec:
    project: str
    dataset: str
    data_range: tuple[dt.date, dt.date]
    default_period: tuple[dt.date, dt.date]
    dimensions: dict[str, Dimension]
    metrics: dict[str, Metric]


def load_spec(path: Path = SPEC_PATH, env: Mapping[str, str] | None = None) -> Spec:
    """Read metrics.yml. `env` overrides project and dataset like profiles.yml does."""
    env = os.environ if env is None else env
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = path.resolve().parent.parent

    dimensions = {}
    for name, d in raw["dimensions"].items():
        values = None
        if "values_from" in d:
            src = d["values_from"]
            with open(root / src["file"], encoding="utf-8", newline="") as f:
                values = frozenset(row[src["column"]] for row in csv.DictReader(f))
        if d["kind"] == "time" and d.get("grain") not in TIME_GRAINS:
            raise ValueError(f"metrics.yml: dimension {name} has an unknown grain")
        dimensions[name] = Dimension(
            name=name,
            kind=d["kind"],
            description=d["description"],
            grain=d.get("grain"),
            column=d.get("column"),
            values=values,
        )

    metrics = {}
    for name, m in raw["metrics"].items():
        parts = [Part(**m["numerator"]), Part(**m["denominator"])]
        for p in parts:
            if p.aggregation not in AGGREGATIONS:
                raise ValueError(f"metrics.yml: {name} uses aggregation {p.aggregation}")
        metrics[name] = Metric(
            name=name,
            label=m["label"],
            question=m["question"],
            description=" ".join(m["description"].split()),
            model=m["model"],
            numerator=parts[0],
            denominator=parts[1],
            multiplier=m.get("multiplier", 1),
            unit=m["unit"],
        )

    return Spec(
        project=env.get("OLIST_GCP_PROJECT", raw["source"]["project"]),
        dataset=env.get("OLIST_DBT_DATASET", raw["source"]["dataset"]),
        data_range=(_month(raw["data_range"]["start"]), _month(raw["data_range"]["end"])),
        default_period=(
            _month(raw["default_period"]["start"]),
            _month(raw["default_period"]["end"]),
        ),
        dimensions=dimensions,
        metrics=metrics,
    )


_SPEC: Spec | None = None


def _default_spec() -> Spec:
    global _SPEC
    if _SPEC is None:
        _SPEC = load_spec()
    return _SPEC


# --- question -------------------------------------------------------------------------


@dataclass(frozen=True)
class Question:
    """A validated question: every name exists and every value is allowed."""

    metric: Metric
    dimensions: tuple[Dimension, ...]
    filters: tuple[tuple[Dimension, tuple[str, ...]], ...]
    period: tuple[dt.date, dt.date]  # first and last month, inclusive

    @property
    def time(self) -> Dimension | None:
        return next((d for d in self.dimensions if d.kind == "time"), None)


def _month(text: str) -> dt.date:
    try:
        return dt.datetime.strptime(str(text), "%Y-%m").date()
    except ValueError:
        raise SemanticError(f"month {text!r} is not YYYY-MM") from None


def _add_months(month: dt.date, n: int) -> dt.date:
    index = month.year * 12 + month.month - 1 + n
    return dt.date(index // 12, index % 12 + 1, 1)


def parse_period(period: Any, spec: Spec) -> tuple[dt.date, dt.date]:
    """None, "YYYY", "YYYY-Qn", "YYYY-MM" or {"start": "YYYY-MM", "end": "YYYY-MM"}."""
    if period is None:
        start, end = spec.default_period
    elif isinstance(period, Mapping):
        if set(period) != {"start", "end"}:
            raise SemanticError("period needs exactly the keys start and end")
        start, end = _month(period["start"]), _month(period["end"])
    elif isinstance(period, str) and re.fullmatch(r"\d{4}", period):
        start, end = dt.date(int(period), 1, 1), dt.date(int(period), 12, 1)
    elif isinstance(period, str) and (m := re.fullmatch(r"(\d{4})-Q([1-4])", period)):
        start = dt.date(int(m[1]), 3 * int(m[2]) - 2, 1)
        end = _add_months(start, 2)
    elif isinstance(period, str):
        start = end = _month(period)
    else:
        raise SemanticError(f"period {period!r} is not understood")

    if start > end:
        raise SemanticError(f"period starts ({start:%Y-%m}) after it ends ({end:%Y-%m})")
    first, last = spec.data_range
    # A year or quarter that overlaps the data is clipped to it; a period with no data
    # at all is an error, not an empty answer.
    if end < first or start > last:
        raise SemanticError(
            f"no data for {start:%Y-%m} to {end:%Y-%m}: the marts cover "
            f"{first:%Y-%m} to {last:%Y-%m}"
        )
    if isinstance(period, Mapping) and (start < first or end > last):
        raise SemanticError(
            f"period {start:%Y-%m} to {end:%Y-%m} goes beyond the data "
            f"({first:%Y-%m} to {last:%Y-%m})"
        )
    return max(start, first), min(end, last)


def _suggest(value: str, options: Iterable[str]) -> str:
    close = difflib.get_close_matches(value, sorted(options), n=3)
    return f" Did you mean {', '.join(close)}?" if close else ""


def build_question(
    metric: str,
    dimensions: Iterable[str] = (),
    filters: Mapping[str, str | Iterable[str]] | None = None,
    period: Any = None,
    spec: Spec | None = None,
) -> Question:
    spec = spec or _default_spec()

    if metric not in spec.metrics:
        raise SemanticError(
            f"unknown metric {metric!r}; defined: {', '.join(spec.metrics)}."
            + _suggest(metric, spec.metrics)
        )

    if isinstance(dimensions, str):
        dimensions = [dimensions]
    dims = []
    for name in dimensions:
        if name not in spec.dimensions:
            raise SemanticError(
                f"unknown dimension {name!r}; defined: {', '.join(spec.dimensions)}."
                + _suggest(name, spec.dimensions)
            )
        if any(d.name == name for d in dims):
            raise SemanticError(f"dimension {name!r} is repeated")
        dims.append(spec.dimensions[name])
    if sum(d.kind == "time" for d in dims) > 1:
        raise SemanticError("group by one time grain at most (month, quarter or year)")

    parsed_filters = []
    for name, value in sorted((filters or {}).items()):
        dim = spec.dimensions.get(name)
        if dim is None:
            raise SemanticError(f"unknown filter {name!r}." + _suggest(name, spec.dimensions))
        if dim.kind == "time":
            raise SemanticError(f"filter time through period, not {name!r}")
        values = (value,) if isinstance(value, str) else tuple(value)
        if not values:
            raise SemanticError(f"filter {name!r} has no values")
        for v in values:
            if dim.values is not None and v not in dim.values:
                raise SemanticError(
                    f"{v!r} is not a {name}." + _suggest(v, dim.values)
                )
        parsed_filters.append((dim, tuple(sorted(set(values)))))

    return Question(
        metric=spec.metrics[metric],
        dimensions=tuple(dims),
        filters=tuple(parsed_filters),
        period=parse_period(period, spec),
    )


# --- SQL ------------------------------------------------------------------------------


def _date(d: dt.date) -> str:
    return f"date '{d:%Y-%m-%d}'"


def _string(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _describe(q: Question) -> str:
    dims = ", ".join(d.name for d in q.dimensions) or "none"
    filters = "; ".join(f"{d.name} in ({', '.join(v)})" for d, v in q.filters) or "none"
    start, end = q.period
    return (
        f"-- metric: {q.metric.name}\n"
        f"-- dimensions: {dims}\n"
        f"-- filters: {filters}\n"
        f"-- period: {start:%Y-%m} to {end:%Y-%m}\n"
    )


def to_sql(q: Question, spec: Spec) -> str:
    m = q.metric
    start, end = q.period
    end_excl = _add_months(end, 1)
    parts = (m.numerator, m.denominator)
    needs_bounds = any(p.aggregation == "last" or p.per_day for p in parts)
    time = q.time

    # base: one row per mart row in the period, with the grouping columns and the parts.
    base_cols = []
    for d in q.dimensions:
        if d.kind == "time":
            base_cols.append(f"date_trunc(month_start, {d.grain}) as {d.name}")
        else:
            base_cols.append(f"{d.column} as {d.name}" if d.column != d.name else d.name)
    if needs_bounds:
        base_cols.append("month_start")
        if time is None:
            base_cols += [f"{_date(start)} as period_start", f"{_date(end_excl)} as period_end"]
        else:
            bucket = f"date_trunc(month_start, {time.grain})"
            base_cols += [
                f"greatest({bucket}, {_date(start)}) as period_start",
                f"least(date_add({bucket}, interval 1 {time.grain}), {_date(end_excl)})"
                " as period_end",
            ]
    base_cols += list(dict.fromkeys(p.column for p in parts))

    where = [f"month_start between {_date(start)} and {_date(end)}"]
    for d, values in q.filters:
        if len(values) == 1:
            where.append(f"{d.column} = {_string(values[0])}")
        else:
            where.append(f"{d.column} in ({', '.join(_string(v) for v in values)})")

    # parts: the additive parts summed per group. A stock counts only in the last
    # calendar month of its period.
    group = [d.name for d in q.dimensions]
    part_cols = list(group)
    for p in dict.fromkeys(parts):
        if p.aggregation == "sum":
            part_cols.append(f"sum({p.column}) as {p.column}")
        else:
            part_cols.append(
                f"sum(if(month_start = date_sub(period_end, interval 1 month), "
                f"{p.column}, 0)) as {p.column}"
            )
    if needs_bounds:
        part_cols.append("any_value(date_diff(period_end, period_start, day)) as days_in_period")

    def term(p: Part) -> str:
        return f"{p.column} / days_in_period" if p.per_day else p.column

    ratio = f"safe_divide({term(m.numerator)}, {term(m.denominator)})"
    if m.multiplier != 1:
        ratio = f"{m.multiplier} * {ratio}"

    final_cols = group + list(dict.fromkeys(p.column for p in parts))
    if needs_bounds:
        final_cols.append("days_in_period")
    final_cols.append(f"{ratio} as {m.name}")

    table = f"`{spec.project}.{spec.dataset}.{m.model}`"
    indent = ",\n        "
    sql = (
        _describe(q)
        + "with base as (\n"
        + "    select\n        "
        + indent.join(base_cols)
        + f"\n    from {table}\n"
        + "    where "
        + "\n        and ".join(where)
        + "\n),\n\n"
        + "parts as (\n"
        + "    select\n        "
        + indent.join(part_cols)
        + "\n    from base"
        + (f"\n    group by {', '.join(group)}" if group else "")
        + "\n)\n\n"
        + "select\n    "
        + ",\n    ".join(final_cols)
        + "\nfrom parts"
        + (f"\norder by {', '.join(group)}" if group else "")
        + "\n"
    )
    return sql


def compile_query(
    metric: str,
    dimensions: Iterable[str] = (),
    filters: Mapping[str, str | Iterable[str]] | None = None,
    period: Any = None,
    spec: Spec | None = None,
) -> str:
    spec = spec or _default_spec()
    return to_sql(build_question(metric, dimensions, filters, period, spec), spec)


# --- the two tools the agent gets -------------------------------------------------------


def listar_metricas(spec: Spec | None = None) -> dict[str, Any]:
    """What can be asked: metrics, dimensions with their allowed values, and periods."""
    spec = spec or _default_spec()
    return {
        "metrics": [
            {
                "name": m.name,
                "label": m.label,
                "question": m.question,
                "unit": m.unit,
                "description": m.description,
            }
            for m in spec.metrics.values()
        ],
        "dimensions": [
            {
                "name": d.name,
                "kind": d.kind,
                "description": d.description,
                **({"values": sorted(d.values)} if d.values is not None else {}),
            }
            for d in spec.dimensions.values()
        ],
        "periods": {
            "data": f"{spec.data_range[0]:%Y-%m} to {spec.data_range[1]:%Y-%m}",
            "default": f"{spec.default_period[0]:%Y-%m} to {spec.default_period[1]:%Y-%m}",
            "formats": ["YYYY", "YYYY-Qn", "YYYY-MM", {"start": "YYYY-MM", "end": "YYYY-MM"}],
        },
    }


@dataclass
class Result:
    metric: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]] = field(default_factory=list)


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.date):
        return value.isoformat()
    return value


def consultar_metrica(
    metric: str,
    dimensions: Iterable[str] = (),
    filters: Mapping[str, str | Iterable[str]] | None = None,
    period: Any = None,
    *,
    spec: Spec | None = None,
    client: Any = None,
) -> Result:
    """Compile the question and run it on BigQuery. No LLM involved."""
    spec = spec or _default_spec()
    sql = compile_query(metric, dimensions, filters, period, spec)

    from google.cloud import bigquery  # only needed to run, not to compile

    client = client or bigquery.Client(project=spec.project)
    job = client.query(
        sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)
    )
    rows = job.result()
    columns = [f.name for f in rows.schema]
    return Result(
        metric=metric,
        sql=sql,
        columns=columns,
        rows=[{c: _plain(r[c]) for c in columns} for r in rows],
    )


# --- command line -----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("metric", nargs="?", help="metric name; omit to list them")
    parser.add_argument("--by", action="append", default=[], help="dimension (repeatable)")
    parser.add_argument(
        "--where", action="append", default=[], metavar="DIM=V1,V2", help="filter (repeatable)"
    )
    parser.add_argument("--period", help="YYYY, YYYY-Qn, YYYY-MM or YYYY-MM:YYYY-MM")
    parser.add_argument("--sql", action="store_true", help="print the SQL without running it")
    args = parser.parse_args(argv)

    if not args.metric:
        for m in listar_metricas()["metrics"]:
            print(f"{m['name']:<20} {m['question']}")
        return 0

    filters = {}
    for item in args.where:
        name, _, values = item.partition("=")
        filters[name] = values.split(",")
    period: Any = args.period
    if period and ":" in period:
        start, end = period.split(":")
        period = {"start": start, "end": end}

    try:
        if args.sql:
            print(compile_query(args.metric, args.by, filters, period), end="")
            return 0
        result = consultar_metrica(args.metric, args.by, filters, period)
    except SemanticError as e:
        print(f"rejected: {e}", file=sys.stderr)
        return 2

    print(result.sql)
    print("\t".join(result.columns))
    for row in result.rows:
        print("\t".join("" if v is None else str(v) for v in row.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
