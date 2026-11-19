"""Placeholder for validating model-proposed SQL."""


def validate(sql: str) -> tuple[bool, str, str | None]:
    """Describe requirements 1–4: allow one SELECT statement (WITH is allowed);
    parse DuckDB SQL and reject write or schema-changing statements; allow only
    configured tables; and block file-reading and network functions.
    """
    raise NotImplementedError("The student will implement SQL validation.")
