# Decision log

This file records decisions that affect the project's safety, operation, or evaluation. It does not contain credentials or measured evaluation results.

## 2026-11-20 — Keep the model outside the database boundary

**Decision:** The model proposes a JSON response containing SQL. Python validates the SQL and controls all database access.

**Reason:** Model output is untrusted input. Keeping database access in code makes the safety rules enforceable and testable.

**Consequence:** The agent only executes a query after validation. Model refusal, parse failure, validation failure, and execution failure are recorded as attempts.

## 2026-11-20 — Use a narrow, read-only DuckDB query path

**Decision:** Permit one parsed `SELECT` against configured Olist tables. Open DuckDB read-only, disable external access, lock configuration, cap returned rows, and interrupt overlong queries.

**Reason:** The app needs read access to the retail data, not permission to change the database or read arbitrary files.

**Consequence:** SQL that does not meet these rules is rejected. The model cannot change row, time, or retry limits.

## 2026-11-20 — Keep the approved stack and explicit data handling

**Decision:** Use the project's fixed Python package list, and prepare the local DuckDB file from manually downloaded Olist CSVs. Do not commit raw CSV files, database files, or API credentials.

**Reason:** The project is a learning exercise with a clear and repeatable data path. Private local files and credentials do not belong in Git.

**Consequence:** A new machine needs its own data and secret setup before the local app or evaluation can run.

## 2026-11-20 — Keep schema relationships hand-written

**Decision:** Store the Olist relationship descriptions in configuration rather than infer joins from column names.

**Reason:** Similar names do not prove that two fields form a valid join. A human-written list is reviewable.

**Consequence:** When the schema or intended joins change, update the list deliberately and review it with the data model.

## 2026-11-20 — Keep explanations and charts constrained

**Decision:** Send only a small capped sample of query rows to the explainer; require its numeric claims to match numbers in those rows. Select charts with simple code rules, not another model decision.

**Reason:** Result values and text may be untrusted, and chart choice should be predictable.

**Consequence:** The explanation may be brief or unavailable if it cannot meet the checks. Some valid query results will have no chart.

## 2026-11-20 — Separate development from held-out evaluation

**Decision:** Keep `dev` questions for iteration and reserve `test` questions for final evaluation. Compare result values against validated and executed gold SQL; do not compare SQL text.

**Reason:** Tuning against final questions would make the held-out evaluation unreliable.

**Consequence:** Report a final test result only after real evaluation runs include a reviewed test split. No measured results are recorded in this log.

## 2026-11-20 — Document the Windows Smart App Control block

**Decision:** Record the local Windows block and use another permitted environment as the security-preserving alternative.

**Reason:** Event Viewer identified the `VerifiedAndReputableDesktop` Smart App Control policy blocking compiled package files used by pandas and the OpenAI client. Those imports are needed to return query results and call the model. This is a Windows code-trust decision, not a SQL validation or API configuration failure.

**Consequence:** The project owner turned Smart App Control off locally to continue testing. This is a host security choice, not a project requirement or a recommendation to disable the feature. Microsoft documents that Smart App Control has no individual app allow-list. If the feature should remain on, use another computer or an approved Linux environment instead. A different Python version is not guaranteed to avoid the same block.

## 2026-11-20 — Consider GitHub Codespaces only after checking quotas

**Decision:** Document Codespaces as an optional Linux development and test environment, not as the app's deployment host.

**Reason:** A Linux environment can avoid this Windows-specific package-load policy, while keeping the policy enabled on the Windows computer.

**Consequence:** At the time checked, GitHub Free personal accounts include 120 Codespaces core-hours and 15 GB-month of storage monthly. A two-core Codespace consumes two core-hours for each running hour. Organization accounts and future plans can differ; check billing and budget settings first. The project still needs secrets supplied through the environment and a smaller dataset made available because `.env`, raw CSVs, and DuckDB files are excluded from Git.

## 2026-11-20 — Treat cloud deployment as follow-up work

**Decision:** Keep Community Cloud deployment notes in the README without claiming that deployment is already configured.

**Reason:** Community Cloud has a secrets interface, but this app currently reads its provider configuration from environment variables. The local DuckDB file is also not in the repository.

**Consequence:** Before deployment, connect Streamlit secrets to the app's existing configuration safely, prepare a smaller database available at runtime, and set a provider-side API spending limit. Keep credentials and data out of source control.
