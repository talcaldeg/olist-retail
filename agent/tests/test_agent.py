"""Offline tests of the agent loop and the eval scoring, with a scripted fake model.

No LLM and no BigQuery: the fake returns canned tool calls, and the agent runs dry
(compiles the SQL without running it).
"""

import json
from types import SimpleNamespace

import pytest

from agent.core import ask, normalize_call, tool_schemas
from agent.eval import expected_key, load_questions, score
from semantic.compiler import load_spec

SPEC = load_spec(env={})


def _message(content=None, calls=()):
    tool_calls = [
        SimpleNamespace(
            id=f"call_{i}",
            function=SimpleNamespace(name=name, arguments=json.dumps(args)),
        )
        for i, (name, args) in enumerate(calls)
    ]
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))])


def scripted(*responses):
    """A fake litellm.completion that replays responses and records what it was sent."""
    queue = list(responses)
    seen = []

    def completion(**kwargs):
        seen.append(kwargs)
        return queue.pop(0)

    completion.seen = seen
    return completion


def test_answer_comes_from_the_compiler():
    fake = scripted(
        _message(calls=[("consultar_metrica", {"metric": "stockout_rate", "dimensions": ["quarter"], "period": "2018"})]),
    )
    a = ask("stockouts by quarter in 2018", spec=SPEC, execute=False, completion=fake, model="fake")
    assert a.status == "answered"
    assert a.call == {"metric": "stockout_rate", "dimensions": ["quarter"], "filters": {}, "period": "2018"}
    assert "mart_quiebre_stock" in a.sql
    # The tool result the model saw carries the compiled SQL.
    # A dry run stops at the first query that compiles: one model call, no prose.
    assert len(fake.seen) == 1 and a.text == "Query compiled, not run."


def test_compiler_error_goes_back_to_the_model_and_a_fix_is_kept():
    fake = scripted(
        _message(calls=[("consultar_metrica", {"metric": "stockout_rate", "filters": {"category": ["helth_beauty"]}})]),
        _message(calls=[("consultar_metrica", {"metric": "stockout_rate", "filters": {"category": ["health_beauty"]}})]),
    )
    a = ask("stockouts in health beauty", spec=SPEC, execute=False, completion=fake, model="fake")
    assert [t.ok for t in a.tool_calls] == [False, True]
    assert "Did you mean health_beauty" in a.tool_calls[0].error
    assert a.status == "answered" and a.call["filters"] == {"category": ["health_beauty"]}


def test_no_successful_query_is_a_rejection_whatever_the_prose_says():
    fake = scripted(
        _message(calls=[("consultar_metrica", {"metric": "stockout_rate", "dimensions": ["seller"]})]),
        _message("The stockout rate by seller is 12%."),
    )
    a = ask("stockout rate by seller", spec=SPEC, execute=False, completion=fake, model="fake")
    assert a.status == "rejected" and a.call is None and a.sql is None


class FakeClient:
    """Stands in for bigquery.Client: every query returns one row."""

    def query(self, sql, job_config=None):
        field = SimpleNamespace(name="gross_margin_pct")
        return SimpleNamespace(result=lambda: _Rows([{"gross_margin_pct": 0.395}], [field]))


class _Rows(list):
    def __init__(self, rows, schema):
        super().__init__(rows)
        self.schema = schema


def test_live_answer_uses_the_rows_and_explicit_rejection_wins(monkeypatch):
    import sys
    import types

    fake_bq = types.ModuleType("google.cloud.bigquery")
    fake_bq.QueryJobConfig = lambda **kw: None
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake_bq)
    monkeypatch.setitem(sys.modules, "google.cloud", types.SimpleNamespace(bigquery=fake_bq))

    fake = scripted(
        _message(calls=[("consultar_metrica", {"metric": "gross_margin_pct"})]),
        _message("The gross margin was 39.5%."),
    )
    a = ask("margin", spec=SPEC, client=FakeClient(), completion=fake, model="fake")
    assert a.status == "answered" and a.rows == [{"gross_margin_pct": 0.395}]
    tool_msg = fake.seen[1]["messages"][3]  # the rows went back to the model
    assert tool_msg["role"] == "tool" and "0.395" in tool_msg["content"]

    fake = scripted(
        _message(calls=[("consultar_metrica", {"metric": "gross_margin_pct"})]),
        _message("REJECTED: revenue is not one of the metrics."),
    )
    a = ask("total revenue", spec=SPEC, client=FakeClient(), completion=fake, model="fake")
    assert a.status == "rejected" and a.call is None


def test_unknown_tool_is_refused():
    fake = scripted(
        _message(calls=[("run_sql", {"sql": "select * from raw.orders"})]),
        _message("REJECTED: I cannot run SQL."),
    )
    a = ask("run this sql", spec=SPEC, execute=False, completion=fake, model="fake")
    assert a.status == "rejected" and not a.tool_calls[0].ok


def test_only_two_tools_and_metric_names_are_closed():
    schemas = tool_schemas(SPEC)
    assert [s["function"]["name"] for s in schemas] == ["listar_metricas", "consultar_metrica"]
    props = schemas[1]["function"]["parameters"]["properties"]
    assert props["metric"]["enum"] == list(SPEC.metrics)


def test_period_range_is_split():
    assert normalize_call({"metric": "x", "period": "2017-06:2018-02"})["period"] == {"start": "2017-06", "end": "2018-02"}
    assert normalize_call({"metric": "x", "period": ""})["period"] is None


def test_every_expected_call_in_the_eval_compiles():
    items = load_questions()
    assert len(items) >= 30
    assert len({q["id"] for q in items}) == len(items)
    assert sum(bool(q.get("reject")) for q in items) >= 8
    for q in items:
        if not q.get("reject"):
            expected_key(q["expect"])


def test_scoring_normalizes_equivalent_calls():
    item = {"expect": {"metric": "stockout_rate", "dimensions": ["year", "category_family"], "period": "2018"}}
    got = {"metric": "stockout_rate", "dimensions": ["category_family", "year"], "filters": {}, "period": "2018-01:2018-09"}
    assert score(item, "answered", got)["pass"]
    wrong = dict(got, period="2018-Q1")
    fields = score(item, "answered", wrong)["fields"]
    assert fields == {"metric": True, "dimensions": True, "filters": True, "period": False}


@pytest.mark.parametrize("status, passed", [("rejected", True), ("answered", False)])
def test_trap_passes_only_when_rejected(status, passed):
    assert score({"reject": True}, status, None)["pass"] is passed
