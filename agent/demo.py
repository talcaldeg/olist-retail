"""Streamlit demo: a question in, the SQL the semantic layer wrote and its result out.

    streamlit run agent/demo.py

Needs GEMINI_API_KEY (or the key of the model in OLIST_AGENT_MODEL) and BigQuery
credentials in GOOGLE_APPLICATION_CREDENTIALS.

Deployed (Streamlit Community Cloud), both come from the app's secrets instead:
GEMINI_API_KEY at the root and a service account key under [gcp_service_account]. With
those secrets present the demo runs in public mode: the model is fixed, questions are
capped per visitor and per day, and long questions are refused, so a stranger cannot spend
the free-tier quota or point the app at another provider.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
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
PER_VISITOR = 10  # questions per browser session, public mode
PER_DAY = 150  # questions per UTC day across all visitors, public mode
MAX_CHARS = 300


def _public_mode() -> bool:
    """Move the deployed app's secrets into the environment. True when they exist."""
    try:
        secrets = st.secrets.to_dict()
    except Exception:  # no secrets.toml: running locally, keys come from .env and the shell
        return False
    if "gcp_service_account" not in secrets:
        return False
    for key, value in secrets.items():
        if isinstance(value, str):
            os.environ.setdefault(key, value)
    path = Path(tempfile.gettempdir()) / "olist_demo_sa.json"
    path.write_text(json.dumps(secrets["gcp_service_account"]), encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)
    return True


@st.cache_resource
def _daily_counter() -> dict[str, int]:
    """Shared by every session of this app process."""
    return {}


st.set_page_config(page_title="Olist metrics agent", page_icon="📊", layout="wide")
PUBLIC = _public_mode()
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
    if PUBLIC:
        model = DEFAULT_MODEL
        st.markdown(f"Model: `{model}` (free tier). Up to {PER_VISITOR} questions per visit.")
    else:
        model = st.text_input("Model (litellm id)", value=DEFAULT_MODEL)
    execute = st.toggle("Run the query on BigQuery", value=True)
    st.markdown("[Source code and tests](https://github.com/talcaldeg/olist-retail)")

example = st.selectbox("Try an example", [""] + EXAMPLES, index=0)
question = st.text_input(
    "Question",
    value=example,
    max_chars=MAX_CHARS,
    placeholder="Ask about margin, turnover, stockouts or cover",
)

if st.button("Ask", type="primary", disabled=not question.strip()):
    if PUBLIC:
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        counter = _daily_counter()
        asked = st.session_state.get("asked", 0)
        if asked >= PER_VISITOR:
            st.warning(
                f"This demo allows {PER_VISITOR} questions per visit. "
                "Clone the repo to run it with your own key."
            )
            st.stop()
        if counter.get(today, 0) >= PER_DAY:
            st.warning("The demo reached its daily limit on the free tier. Please come back tomorrow.")
            st.stop()
        if today not in counter:
            counter.clear()  # a new day starts from zero
        counter[today] = counter.get(today, 0) + 1
        st.session_state["asked"] = asked + 1
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
