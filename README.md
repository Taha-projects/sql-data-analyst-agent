# SQL Data Analyst Agent

Ask questions in plain English about the Olist Brazilian e-commerce dataset and inspect the SQL and results.

**Live demo:** [Add the deployed app URL here when one exists](#)

## Architecture

```text
Browser question
       |
       v
Streamlit app -----> agent orchestration
                           |
             +-------------+-------------+
             |                           |
             v                           v
      Schema context              LLM proposes JSON
      (read-only DuckDB)             with one SQL query
                                         |
                                         v
                               SQLGlot validator
                                         |
                                  valid SELECT only
                                         |
                                         v
                              Read-only DuckDB executor
                                         |
                                   capped DataFrame
                                         |
                    +--------------------+-------------------+
                    |                    |                   |
                    v                    v                   v
             LLM explanation      Rule-based chart       Run log
             (small sample)       selection
                    |
                    v
             Answer, SQL, data, chart, and attempts in the app
```

The LLM proposes a query. Python validates and decides whether it can run. The LLM does not connect to DuckDB.

## How it works

1. The app builds schema context from the local DuckDB file.
2. The configured OpenAI-compatible model returns JSON containing a proposed SQL query or a refusal.
3. The agent sends proposed SQL through the SQLGlot validator. Invalid SQL is rejected before execution.
4. Valid SQL runs through the executor with read-only access, external access disabled, a result row cap, and a query time limit.
5. The agent records each attempt and may retry after an error, up to the configured limit.
6. For successful queries, the explainer receives only a limited sample of result rows. The chart type is selected with simple column rules, not by the LLM.
7. The app displays the answer, SQL, data, chart, and attempt history.

## Safety layers

- SQL is parsed as DuckDB SQL. Exactly one `SELECT` statement is accepted; a `WITH ... SELECT` is allowed.
- Write and schema-changing statements are rejected.
- Referenced tables must be in the fixed allowlist in `agent/config.py`.
- File-reading, network, and dynamic SQL functions are rejected.
- The executor validates SQL again, opens DuckDB in read-only mode, disables external access, and locks connection configuration.
- Python applies the row cap and timeout. The model cannot choose either value or the retry limit.
- API credentials are read from environment variables and must not be committed.

These controls reduce risk but do not prove that every answer is correct. Review the SQL and result before relying on an answer.

## Evaluation method

`eval/run_eval.py` reads hand-written questions from `eval/questions.yaml` and sends each question through the real agent. It separately validates and executes the gold SQL through the safe executor. `eval/scoring.py` compares result values rather than SQL text, ignoring column labels and order, sorting rows, and rounding floating-point values to two decimal places.

Questions use a `dev` split for development and a `test` split kept for held-out evaluation. Refusal questions pass only when the agent refuses. Block questions pass only when a validator rejection or database block is confirmed and no data is returned. The evaluation runner writes a new CSV for each actual run under `eval/results/`. Do not use development results as the final score or tune against held-out questions.

### Results

These entries are from one actual evaluation run. The held-out question set is small, so this run is not a guarantee of general answer accuracy.

| Split | Outcome summary | Source CSV |
|---|---|---|
| dev | 1/1 passed (diagnostic only; not a final score) | `eval/results/eval-20261120-033847-613257.csv` (local, Git-ignored) |
| test | 4/4 passed in this run | `eval/results/eval-20261120-033847-613257.csv` (local, Git-ignored) |

### Failures and fixes

| Observed failure | Verified fix |
|---|---|

## Run locally

Use Python 3.11 or newer. Run these commands from the project root in PowerShell.

1. Check Python and create a virtual environment:

   ```powershell
   python --version
   python -m venv .venv
   ```

2. Install the pinned dependencies:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env`, then put your own provider key, base URL, and model name in `.env`. Keep `.env` private; it is ignored by Git.

   ```powershell
   Copy-Item .env.example .env
   ```

4. Download the Olist Brazilian E-Commerce Public Dataset from [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Extract the nine required CSV files into `data/raw/`. The preparation script does not download files.

5. Build the local database, run tests, and start the app:

   ```powershell
   .\.venv\Scripts\python.exe -m data.prepare_data
   .\.venv\Scripts\python.exe -m pytest
   .\.venv\Scripts\python.exe -m streamlit run app.py
   ```

The database and raw CSV directory are ignored by Git. `DB_PATH` can point to a different database file; otherwise the app uses `data/retail.duckdb`.

To run the real evaluation, first add valid questions and gold SQL to `eval/questions.yaml`, then run:

```powershell
.\.venv\Scripts\python.exe -m eval.run_eval
```

This makes real calls to the configured model. Each run writes a CSV in `eval/results/`.

## Windows Smart App Control and cloud alternatives

On the development Windows computer, Smart App Control blocked compiled Python package files used by pandas and the OpenAI client. That stopped result conversion and model calls before the app could finish a question. This was a Windows trust-policy decision about those local binaries; it did not indicate that the project SQL or API settings were wrong. Turning Smart App Control off was a local choice made to continue testing, not a requirement of this app. Smart App Control has no per-file allow list; see [Microsoft's Smart App Control FAQ](https://support.microsoft.com/en-gb/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions?pubDate=20261001).

One alternative is GitHub Codespaces or another approved Linux development environment. Codespaces is for development and testing, not the same as publishing the Streamlit app. The repository does not include `.env`, the full raw data, or the DuckDB file, so provide credentials through the environment's secret settings and make a suitable smaller dataset available separately. Do not commit keys or private data.

As checked on 20 November 2026, a personal GitHub Free account includes 120 Codespaces core-hours and 15 GB-month of storage per month. A two-core Codespace uses two core-hours for each hour it runs, so this quota corresponds to 60 hours of two-core runtime. Free Codespaces usage is for personal accounts; organization accounts may have different billing. Check your own billing page and set spending controls before use because quotas and billing rules can change. See [GitHub's included usage table](https://docs.github.com/en/billing/reference/product-usage-included) and [Codespaces billing guide](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces).

## Streamlit Community Cloud deployment notes

- Store the API key in the app's Streamlit Cloud secrets settings. Never put it in source control. The current project reads credentials from environment variables, so secret loading must be connected to the app's runtime settings and verified before deployment. See [Streamlit's secrets guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).
- The full raw dataset and DuckDB file are not in Git. Prepare a smaller dataset for a demo and make its database available to the app at runtime; configure `DB_PATH` accordingly.
- Set a low spending cap for the model provider's API key and monitor its use. A free model label is not a substitute for a provider-side limit.
- Test the deployed app with the same Python version and pinned requirements before sharing it. A deployment URL is not available yet.

## Limitations

- Generated SQL and explanations can be wrong. Inspect the SQL and data for each answer.
- The agent can query only the configured Olist tables. It cannot answer questions that require other data or context.
- Query results are capped, so a displayed table may not contain every row returned by an unrestricted query.
- Evaluation quality depends on clear questions and independently checked gold SQL. The held-out test split must remain separate from development.
- The app has a per-session question limit but no user accounts or authentication.
- Cloud deployment needs a runtime dataset and a verified way to supply secrets; neither is configured by this README.
- This is a learning project and is not described as production-ready.
