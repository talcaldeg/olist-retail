"""A metrics agent with two tools and no SQL of its own.

The model sees only listar_metricas and consultar_metrica from semantic/compiler.py. It
routes a question to one metric, its dimensions, filters and period; the compiler writes
the SQL. A question that no metric expresses is rejected: the agent answers without a
successful consultar_metrica call, and the reply starts with REJECTED.

    >>> answer = ask("What was the stockout rate by quarter in 2018?")
    >>> answer.status, answer.call, answer.sql

The model goes through litellm, Gemini's free tier by default (GEMINI_API_KEY, from the
environment or a .env at the repo root). OLIST_AGENT_MODEL switches it to any model
litellm knows, e.g. groq/llama-3.3-70b-versatile with GROQ_API_KEY.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from semantic.compiler import (
    SemanticError,
    Spec,
    _default_spec,
    build_question,
    consultar_metrica,
    listar_metricas,
    to_sql,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "gemini/gemini-3.1-flash-lite"
MAX_STEPS = 6
REJECTED = "REJECTED"

SYSTEM_PROMPT = """\
You answer questions about an online retailer (Olist, Brazil, 2016-09 to 2018-09) with
exactly four metrics, and nothing else:

{metrics}

You never write SQL. You call consultar_metrica with a metric, optional dimensions,
optional filters and an optional period, and the semantic layer writes and runs the
query. Call listar_metricas first if you need the allowed category names.

Routing rules:
- Pick the metric that the question asks for. Do not substitute a related one: revenue,
  sales volume, order counts, prices, delivery times, reviews, customers, sellers,
  regions, forecasts or what-if scenarios are NOT among the metrics.
- Dimensions are only what the question groups or breaks down by ("by quarter", "per
  category", "each family"). A category or family the question names is a filter, not a
  dimension.
- Periods: "2018" for a year, "2018-Q1" for a quarter, "2018-03" for a month,
  "2017-06:2018-02" for a range of months. Leave the period empty when the question names
  none (the default is 2017-01 to 2018-08). Relative dates ("last month", "this year")
  have no reference point here: reject them.
- Category and family values are the English snake_case names from listar_metricas. Map a
  plain-English or Portuguese name to one of them only when the match is unambiguous.
- If a tool call fails, read the error. Fix a typo it points out, but never switch to a
  different metric to get an answer.

If the question cannot be answered with one call to one of the four metrics, do not call
consultar_metrica. Reply with a first line "{rejected}: <reason in one sentence>", and name
what the project can answer instead.

When the query works, answer in one to three sentences in the language of the question,
with the figures from the result and the period they cover.
"""


# --- tools ------------------------------------------------------------------------------


def tool_schemas(spec: Spec) -> list[dict[str, Any]]:
    """Function declarations in the OpenAI format litellm translates for each provider."""
    categorical = [d for d in spec.dimensions.values() if d.kind == "categorical"]
    return [
        {
            "type": "function",
            "function": {
                "name": "listar_metricas",
                "description": (
                    "List the four metrics, the dimensions they can be cut by, the "
                    "allowed category and category_family values, and the periods with data."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "consultar_metrica",
                "description": (
                    "Compute one metric, optionally grouped by dimensions, filtered by "
                    "category or category_family, over a period. Returns the SQL the "
                    "semantic layer generated and the result rows, or the reason the "
                    "question was rejected."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {"type": "string", "enum": list(spec.metrics)},
                        "dimensions": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(spec.dimensions)},
                            "description": "Group by these. At most one of month, quarter, year.",
                        },
                        "filters": {
                            "type": "object",
                            "properties": {
                                d.name: {"type": "array", "items": {"type": "string"}}
                                for d in categorical
                            },
                            "description": "Keep only these values of category or category_family.",
                        },
                        "period": {
                            "type": "string",
                            "description": "YYYY, YYYY-Qn, YYYY-MM or YYYY-MM:YYYY-MM. Empty for the default.",
                        },
                    },
                    "required": ["metric"],
                },
            },
        },
    ]


def normalize_call(args: dict[str, Any]) -> dict[str, Any]:
    """Tool arguments as the compiler takes them: period strings with ':' become ranges."""
    period = args.get("period") or None
    if isinstance(period, str) and ":" in period:
        start, _, end = period.partition(":")
        period = {"start": start.strip(), "end": end.strip()}
    filters = {k: v for k, v in (args.get("filters") or {}).items() if v not in (None, [], "")}
    return {
        "metric": args.get("metric", ""),
        "dimensions": list(args.get("dimensions") or []),
        "filters": filters,
        "period": period,
    }


# --- agent loop -------------------------------------------------------------------------


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    ok: bool
    error: str | None = None


@dataclass
class Answer:
    question: str
    status: str  # "answered", "rejected" or "error"
    text: str
    call: dict[str, Any] | None = None  # the last consultar_metrica that worked
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env", override=False)


def _completion(**kwargs: Any) -> Any:
    import litellm

    return litellm.completion(**kwargs)


def _system_prompt(spec: Spec) -> str:
    metrics = "\n".join(
        f"- {m.name} ({m.unit}): {m.question} {m.description}" for m in spec.metrics.values()
    )
    return SYSTEM_PROMPT.format(metrics=metrics, rejected=REJECTED)


def _run_tool(
    name: str, args: dict[str, Any], spec: Spec, execute: bool, client: Any
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run one tool. Returns (payload for the model, result for the Answer or None)."""
    if name == "listar_metricas":
        return listar_metricas(spec), None
    if name != "consultar_metrica":
        raise SemanticError(f"unknown tool {name!r}")

    call = normalize_call(args)
    if not execute:
        question = build_question(**call, spec=spec)
        sql = to_sql(question, spec)
        return (
            {"sql": sql, "rows": "not run (dry run): answer that the query compiled"},
            {"call": call, "sql": sql, "columns": [], "rows": []},
        )
    result = consultar_metrica(**call, spec=spec, client=client)
    return (
        {"sql": result.sql, "columns": result.columns, "rows": result.rows[:60]},
        {"call": call, "sql": result.sql, "columns": result.columns, "rows": result.rows},
    )


def ask(
    question: str,
    *,
    model: str | None = None,
    spec: Spec | None = None,
    execute: bool = True,
    client: Any = None,
    completion: Callable[..., Any] | None = None,
) -> Answer:
    """Route a question to one metric and answer it, or reject it."""
    _load_dotenv()
    spec = spec or _default_spec()
    model = model or os.environ.get("OLIST_AGENT_MODEL", DEFAULT_MODEL)
    completion = completion or _completion

    messages: list[Any] = [
        {"role": "system", "content": _system_prompt(spec)},
        {"role": "user", "content": question},
    ]
    answer = Answer(question=question, status="error", text="", model=model)
    last: dict[str, Any] | None = None

    for _ in range(MAX_STEPS):
        response = completion(
            model=model,
            messages=messages,
            tools=tool_schemas(spec),
            tool_choice="auto",
            temperature=0,
            num_retries=int(os.environ.get("OLIST_AGENT_RETRIES", "4")),
        )
        message = response.choices[0].message
        calls = getattr(message, "tool_calls", None) or []
        messages.append(message)

        if not calls:
            answer.text = (message.content or "").strip()
            break

        for tc in calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                payload, result = _run_tool(name, args, spec, execute, client)
                answer.tool_calls.append(ToolCall(name, args, ok=True))
                if result is not None:
                    last = result
            except SemanticError as e:
                payload = {"rejected": str(e)}
                answer.tool_calls.append(ToolCall(name, args, ok=False, error=str(e)))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(payload, default=str),
                }
            )
    else:
        answer.text = f"{REJECTED}: no answer within {MAX_STEPS} steps."

    # The code decides, not the prose: without a query that worked there is no answer.
    if last is not None and not re.match(rf"\s*{REJECTED}\b", answer.text):
        answer.status = "answered"
        answer.call, answer.sql = last["call"], last["sql"]
        answer.columns, answer.rows = last["columns"], last["rows"]
    else:
        answer.status = "rejected"
    return answer


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Ask the metrics agent one question.")
    parser.add_argument("question")
    parser.add_argument("--model", help=f"litellm model id (default {DEFAULT_MODEL})")
    parser.add_argument("--dry", action="store_true", help="compile the SQL, do not run it")
    args = parser.parse_args(argv)

    a = ask(args.question, model=args.model, execute=not args.dry)
    print(f"[{a.status}] {a.text}")
    if a.call:
        print(json.dumps(a.call, ensure_ascii=False))
        print(a.sql)
        for row in a.rows[:20]:
            print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
