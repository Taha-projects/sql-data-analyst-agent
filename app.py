"""Streamlit entry point for the SQL Data Analyst Agent."""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent.agent import AgentResult, answer_question
from agent.charts import choose_chart
from agent.config import (
    EXPLAIN_MAX_ROWS,
    MAX_ATTEMPTS,
    MAX_ROWS,
    MODEL_NAME,
    QUERY_TIMEOUT_SECONDS,
)
from agent.explain import explain_result
from agent.logger import log_question

SESSION_QUESTION_LIMIT = 10
EXAMPLE_QUESTIONS = (
    "How many orders are in the dataset?",
    "Which product categories have the most products?",
    "What is the total recorded payment value by payment type?",
    "How many orders were delivered each month?",
)


def _select_example(question: str) -> None:
    """Place a sample question into the input for easy first use."""
    st.session_state["question_input"] = question


def _initialize_session() -> None:
    """Create per-browser state so each session has its own question limit."""
    defaults = {
        "questions_used": 0,
        "question_input": "",
        "last_result": None,
        "last_explanation": "",
        "app_error": "",
        "explanation_error": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _run_question(question: str) -> None:
    """Call the agent once and store a safe, presentable result."""
    st.session_state["questions_used"] += 1
    st.session_state["app_error"] = ""
    st.session_state["last_explanation"] = ""
    st.session_state["explanation_error"] = False
    try:
        result = answer_question(question)
    except Exception:
        st.session_state["last_result"] = None
        st.session_state["app_error"] = (
            "I could not process that question. Check that the dataset and "
            "model settings are available, then try again."
        )
        return

    st.session_state["last_result"] = result
    try:
        log_question(result)
    except OSError:
        st.session_state["app_error"] = (
            "The result is ready, but the run could not be added to the local log."
        )

    if result.status == "answered" and result.dataframe is not None:
        try:
            st.session_state["last_explanation"] = explain_result(
                question, result.sql, result.dataframe
            )
        except Exception:
            st.session_state["explanation_error"] = True


def _show_sidebar() -> None:
    """Show dataset details and fixed safety limits without edit controls."""
    st.sidebar.header("About the data")
    st.sidebar.write(
        "Olist Brazilian e-commerce data, stored locally in DuckDB. "
        "It includes orders, customers, products, payments, reviews, sellers, "
        "and related tables."
    )
    st.sidebar.subheader("Model and safety limits")
    st.sidebar.caption(f"Model: {MODEL_NAME or 'Not configured'}")
    st.sidebar.caption(f"Maximum result rows: {MAX_ROWS}")
    st.sidebar.caption(f"Query timeout: {QUERY_TIMEOUT_SECONDS} seconds")
    st.sidebar.caption(f"Maximum SQL attempts: {MAX_ATTEMPTS}")
    st.sidebar.caption(f"Rows sent for explanation: {EXPLAIN_MAX_ROWS}")
    used = st.session_state["questions_used"]
    st.sidebar.caption(f"Questions this session: {used}/{SESSION_QUESTION_LIMIT}")
    st.sidebar.subheader("Example questions")
    for index, example in enumerate(EXAMPLE_QUESTIONS):
        st.sidebar.button(
            example,
            key=f"example_{index}",
            on_click=_select_example,
            args=(example,),
        )


def _show_attempts(result: AgentResult) -> None:
    """Display every attempt and its recorded error for transparency."""
    with st.expander("What the agent did"):
        if not result.attempts:
            st.write("No SQL attempts were recorded.")
        for attempt in result.attempts:
            st.markdown(f"**Attempt {attempt.number}**")
            st.code(attempt.sql or "-- No SQL was generated", language="sql")
            if attempt.stage_failed:
                st.write(f"Failed during: {attempt.stage_failed}")
                st.write(f"Error: {attempt.error_message}")
            else:
                st.write("No failure was recorded for this attempt.")
            st.caption(f"Attempt time: {attempt.latency_s:.2f} seconds")


def _show_result(result: AgentResult) -> None:
    """Place the latest answer in the requested result tabs."""
    answer_tab, sql_tab, data_tab, chart_tab = st.tabs(
        ["Answer", "SQL", "Data", "Chart"]
    )
    with answer_tab:
        if result.status == "answered":
            if st.session_state["explanation_error"]:
                st.info(
                    "The query ran, but I could not prepare its short explanation. "
                    "Review the SQL and result table."
                )
            else:
                st.write(st.session_state["last_explanation"] or result.answer_text)
        elif result.status == "refused":
            st.info("I couldn’t answer this from the available dataset.")
            st.write(result.answer_text)
        else:
            st.error(
                "I couldn’t complete this question safely. Try rephrasing it or "
                "choosing a simpler question."
            )
    with sql_tab:
        st.code(result.sql or "-- No SQL was generated", language="sql")
    with data_tab:
        if result.dataframe is None:
            st.write("There is no result table for this question.")
        else:
            st.dataframe(result.dataframe, use_container_width=True)
    with chart_tab:
        _show_chart(result)
    _show_attempts(result)


def _show_chart(result: AgentResult) -> None:
    """Render only chart types selected by the simple chart rules."""
    if result.dataframe is None:
        st.write("There is no result table to chart.")
        return
    choice = choose_chart(result.dataframe)
    if choice is None:
        st.write("These results do not have a clear category or date chart.")
    elif choice.kind == "bar":
        st.bar_chart(result.dataframe, x=choice.x_column, y=choice.y_column)
    else:
        st.line_chart(result.dataframe, x=choice.x_column, y=choice.y_column)


def main() -> None:
    """Render the question form and results for one browser session."""
    st.set_page_config(page_title="SQL Data Analyst Agent", page_icon="📊")
    _initialize_session()
    st.title("SQL Data Analyst Agent")
    _show_sidebar()
    st.write("Ask a question about the Olist retail dataset in plain English.")
    st.text_area("Your question", key="question_input", height=100)
    limit_reached = st.session_state["questions_used"] >= SESSION_QUESTION_LIMIT
    if st.button("Ask", type="primary", disabled=limit_reached):
        question = st.session_state["question_input"].strip()
        if not question:
            st.warning("Type a question first.")
        elif limit_reached:
            st.error("You have reached the 10-question limit for this session.")
        else:
            with st.spinner("Checking the question and running a safe query..."):
                _run_question(question)
            st.rerun()

    if limit_reached:
        st.info("This session has used all 10 questions.")
    if st.session_state["app_error"]:
        st.error(st.session_state["app_error"])
    result = st.session_state["last_result"]
    if result is not None:
        _show_result(result)
    st.caption(
        "This app is read-only and uses a small dataset. Its answers can be wrong; "
        "please check the SQL before relying on the result."
    )


if __name__ == "__main__":
    main()
