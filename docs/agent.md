# Metrics agent: two tools, no SQL

`agent/core.py` puts a language model in front of the [semantic layer](semantic.md). The
model gets exactly two tools, `listar_metricas` and `consultar_metrica`, and its only job
is routing: pick one of the four metrics, the dimensions to group by, the filters and the
period. The compiler writes the SQL and BigQuery runs it. The model never sees a table
name it could query on its own, and there is no tool that takes SQL.

```python
from agent import ask

answer = ask("What was the stockout rate by quarter in 2018 for the electronics family?")
answer.status   # "answered" or "rejected"
answer.call     # {"metric": "stockout_rate", "dimensions": ["quarter"], ...}
answer.sql      # what the compiler generated
answer.rows     # the result
```

From the shell: `python -m agent "question"` (add `--dry` to compile without running).

## Rejection is decided by the code

A question is answered only if a `consultar_metrica` call went through the compiler. When
none did, the answer is a rejection whatever the model wrote; when the model replies
`REJECTED: ...` after a query, the rejection stands too. The compiler already refuses
unknown metrics, dimensions, filter values and periods outside the data, and its error goes
back to the model, which may fix a typo it points out but is told never to switch metrics
to get an answer. The system prompt lists what is out of scope (revenue, order counts,
delivery times, sellers, regions, forecasts, what-if scenarios, relative dates).

## Model

litellm, with Gemini's free tier by default (`gemini/gemini-3.1-flash-lite`,
`GEMINI_API_KEY` from the environment or a `.env` at the repo root). `OLIST_AGENT_MODEL`
switches to any model litellm knows, e.g. `groq/llama-3.3-70b-versatile` with
`GROQ_API_KEY`. The free tier allows 15 requests a minute; the eval paces itself and waits
out a 429.

## Eval

`agent/eval_questions.yml` holds 33 questions: 23 the metrics answer, some in Spanish or
naming a category in plain English or Portuguese, and 10 traps that must be rejected
(revenue, orders, sellers, regions, delivery time, a forecast, a relative date, a year
without data, raw SQL, a what-if). The prose is not scored. For each question the call is
compared with the expected one field by field (metric, dimensions, filters, period) after
the compiler normalizes both, so `2018` and `2018-01:2018-09` are the same period.

```
python -m agent.eval            # compile only: no BigQuery, one model call per question
python -m agent.eval --live     # run the queries too
python -m agent.eval --report   # also write docs/agent_eval.md
```

In a dry run the loop stops at the first query that compiles, since the call is what gets
scored. The latest results are in [agent_eval.md](agent_eval.md).

## Demo

```
streamlit run agent/demo.py
```

A question in; the answer, the routed call (metric, dimensions, filters, period), the
generated SQL and the result table out, with the tool calls in an expander. Needs
`GEMINI_API_KEY` and BigQuery credentials in `GOOGLE_APPLICATION_CREDENTIALS`.

## Tests

`agent/tests/` runs on every push with a scripted fake model and no network: answers come
from the compiler, a compiler error goes back to the model and a fix is kept, a claim
without a successful query is a rejection, an unknown tool is refused, and the scoring
treats equivalent calls as equal.
