"""Streamlit demo: a question in, the SQL the semantic layer wrote and its result out.

    streamlit run agent/demo.py

Needs GEMINI_API_KEY (or the key of the model in OLIST_AGENT_MODEL) and BigQuery
credentials in GOOGLE_APPLICATION_CREDENTIALS.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agent.core import DEFAULT_MODEL, ask  # noqa: E402
from semantic.compiler import listar_metricas  # noqa: E402

EXAMPLES = [
    "What was the stockout rate by quarter in 2018 for the electronics family?",
    "How many days of cover did we have at the end of August 2018?",
    "Which categories in the home family had the best margin in the second quarter of 2018?",
    "¿Cuál fue la rotación de inventario de cada familia en el primer trimestre de 2018?",
    "What was the total revenue in 2017?",
    "Show the stockout rate by seller.",
]
PERCENT = {"gross_margin_pct", "stockout_rate"}

st.set_page_config(page_title="Olist metrics agent", page_icon="📊", layout="wide")
st.title("Olist metrics agent")
st.caption(
    "Four metrics, two tools. The model picks a metric, dimensions, filters and a period; "
    "the semantic layer writes the SQL. Anything the metrics cannot express is rejected."
)

with st.sidebar:
    st.subheader("What it can answer")
    catalog = listar_metricas()
    for m in catalog["metrics"]:
        st.markdown(f"**{m['label']}** (`{m['name']}`)  \n{m['question']}")
    st.markdown(
        "Cut by `month`, `quarter` or `year`, and by `category` (74) or "
        f"`category_family` (10). Data: {catalog['periods']['data']}."
    )
    model = st.text_input("Model (litellm id)", value=DEFAULT_MODEL)
    execute = st.toggle("Run the query on BigQuery", value=True)

example = st.selectbox("Try an example", [""] + EXAMPLES, index=0)
question = st.text_input("Question", value=example, placeholder="Ask about margin, turnover, stockouts or cover")

if st.button("Ask", type="primary", disabled=not question.strip()):
    with st.spinner("Routing the question (on the free tier this can take half a minute)..."):
        try:
            answer = ask(question.strip(), model=model.strip() or None, execute=execute)
        except Exception as e:  # provider or BigQuery errors, shown instead of a traceback
            st.error(f"The call failed: {e}")
            st.stop()

    if answer.status == "answered":
        st.success(answer.text or "Done.")
    else:
        st.warning(answer.text or "Rejected.")

    if answer.call:
        c = answer.call
        period = c["period"]
        if isinstance(period, dict):
            period = f"{period['start']} to {period['end']}"
        filters = "; ".join(f"{k} = {', '.join(v)}" for k, v in c["filters"].items())
        st.markdown(
            f"**Metric** `{c['metric']}` &nbsp; **Dimensions** "
            f"`{', '.join(c['dimensions']) or 'none'}` &nbsp; **Filters** `{filters or 'none'}`"
            f" &nbsp; **Period** `{period or 'default (2017-01 to 2018-08)'}`"
        )

        st.subheader("Result")
        if answer.rows:
            # The metric right after the grouping columns; its parts after it.
            order = c["dimensions"] + [c["metric"]]
            df = pd.DataFrame(answer.rows, columns=answer.columns)
            df = df[order + [col for col in df.columns if col not in order]]
            if c["metric"] in PERCENT:
                df[c["metric"]] = df[c["metric"]] * 100
            st.dataframe(
                df,
                hide_index=True,
                column_config={
                    c["metric"]: st.column_config.NumberColumn(
                        format="%.1f%%" if c["metric"] in PERCENT else "%.2f"
                    )
                },
            )
        else:
            st.info("The query was compiled but not run.")

        st.subheader("Generated SQL")
        st.code(answer.sql, language="sql")

    with st.expander("Tool calls"):
        for t in answer.tool_calls:
            st.markdown(f"`{t.name}` {'ok' if t.ok else 'rejected: ' + (t.error or '')}")
            if t.arguments:
                st.json(t.arguments)
