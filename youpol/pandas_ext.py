"""
Pandas integration for YouPol client.

Adds a ``to_dataframe()`` method to all table endpoints when pandas is installed.

Usage::

    from youpol import YouPol
    import youpol.pandas_ext  # activates .to_dataframe()

    client = YouPol(token="...")
    df = client.videos.to_dataframe(country="FR", limit=100)
"""

from __future__ import annotations

from typing import Any

from youpol.client import _TableEndpoint


def to_dataframe(
    self: _TableEndpoint,
    *,
    select: str | list[str] | None = None,
    order: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    **filters: Any,
):
    """Fetch rows and return as a pandas DataFrame.

    Accepts the same arguments as ``.list()``.

    Returns:
        pandas.DataFrame with one row per record.

    Raises:
        ImportError: If pandas is not installed.
            Install with: ``pip install youpol[pandas]``
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            "pandas is required for to_dataframe(). "
            "Install with: pip install youpol[pandas]"
        )

    from youpol.client import _parse_filters, MAX_PAGE_SIZE

    params = _parse_filters(filters)
    if select:
        params["select"] = ",".join(select) if isinstance(select, list) else select
    if order:
        params["order"] = order
    if offset:
        params["offset"] = offset

    rows = self._session.get_paginated(self._table, params, limit=limit)
    return pd.DataFrame(rows)


# Monkey-patch the base endpoint class
_TableEndpoint.to_dataframe = to_dataframe
