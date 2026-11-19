"""Executes validated SQL using a read-only database connection."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas


def execute(sql: str) -> pandas.DataFrame:
    """Document safety requirements 5–7: connect read-only, disable external
    access, lock configuration, cap returned rows, and stop queries at timeout.
    """
    raise NotImplementedError("The student will implement SQL execution.")
