"""
Classifier filter builder — fluent API for constructing the ``p_model_filters``
JSONB payload consumed by the ``search_sentences_v2`` (and forthcoming
``search_transcriptions_v2``/``search_comments_v2``) RPCs exposed at
https://data.you-pol.com/.

The JSONB shape the server expects:

    {
      "<storage_key>": {                    # per single-label model
         "label":    "political_yes",       # optional, exact label match
         "prob_min": 0.7,                   # optional, float in [0, 1]
         "prob_max": 1.0                    # optional
      },
      "<storage_key>": {                    # per multi-label model
         "active":   ["racist", "homophobic"]  # OR across active[] entries
      },
      "video_pct": {                        # cross-filter on parent video
         "<storage_key>": {
            "min":   30,                    # optional, percentage 0..100
            "max":   100,                   # optional
            "scope": "all" | "tsp" | "cp"   # optional (default "all")
         }
      }
    }

Usage::

    from youpol import YouPol
    from youpol.filters import ModelFilter

    f = (ModelFilter()
         .label('pol_detect', 'political_yes')
         .prob_range('pol_detect', min=0.85)
         .video_pct('pol_detect', min=30, scope='tsp'))

    payload = f.build()
    # → call the RPC via the Session:
    sess = client._session   # (internal — future-proof helper TBD)
    rows = sess.get('/rpc/search_sentences_v2', params={
        **f.to_rpc_params('immigration'),
    })

All methods return ``self`` so calls can be chained. ``build()`` returns a
plain dict ready to JSON-encode; ``to_rpc_params(query, **kwargs)`` returns
a dict suitable for POST-to-PostgREST.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable, Optional


class ModelFilter:
    """Fluent builder for the ``p_model_filters`` JSONB payload."""

    def __init__(self) -> None:
        self._data: dict = {}

    # -- Single-label model criteria ---------------------------------------

    def label(self, storage_key: str, label: str) -> "ModelFilter":
        """Keep rows whose predicted label for ``storage_key`` is exactly
        ``label``. Overrides any prior ``label(...)`` call for the same key.
        """
        self._data.setdefault(storage_key, {})["label"] = str(label)
        return self

    def prob_range(
        self,
        storage_key: str,
        *,
        min: Optional[float] = None,
        max: Optional[float] = None,
    ) -> "ModelFilter":
        """Restrict the probability of the predicted label. Both bounds are
        optional and live in the [0, 1] range.
        """
        entry = self._data.setdefault(storage_key, {})
        if min is not None:
            entry["prob_min"] = float(min)
        if max is not None:
            entry["prob_max"] = float(max)
        return self

    # -- Multi-label model criteria ----------------------------------------

    def active_any(
        self, storage_key: str, labels: Iterable[str]
    ) -> "ModelFilter":
        """Multi-label: keep rows where the classifier flagged AT LEAST ONE
        of ``labels`` as active.
        """
        vals = [str(l) for l in labels if str(l).strip()]
        if vals:
            self._data.setdefault(storage_key, {})["active"] = vals
        return self

    # -- Parent-video aggregate cross-filter --------------------------------

    def video_pct(
        self,
        storage_key: str,
        *,
        min: Optional[float] = None,
        max: Optional[float] = None,
        scope: str = "all",
    ) -> "ModelFilter":
        """Cross-filter on the parent video's aggregate percentage of the
        classifier's positive label.

        ``scope`` is one of:
          - ``"all"`` → combine transcripts + comments (default)
          - ``"tsp"`` → only transcript sentences
          - ``"cp"``  → only comment sentences

        ``min``/``max`` are percentages in 0..100. Only meaningful for
        sentence- / segment-level searches (``search_sentences_v2``,
        ``search_transcriptions_v2``); ignored for comment search.
        """
        if scope not in ("all", "tsp", "cp"):
            raise ValueError(f"scope must be 'all' | 'tsp' | 'cp', got {scope!r}")
        vpct = self._data.setdefault("video_pct", {})
        entry = vpct.setdefault(storage_key, {})
        if min is not None:
            entry["min"] = float(min)
        if max is not None:
            entry["max"] = float(max)
        entry["scope"] = scope
        return self

    # -- Housekeeping -------------------------------------------------------

    def reset(self, storage_key: Optional[str] = None) -> "ModelFilter":
        """Clear filters. With no arg, wipe everything; with a storage_key,
        clear just that model's criteria (including any ``video_pct`` entry).
        """
        if storage_key is None:
            self._data = {}
        else:
            self._data.pop(storage_key, None)
            if "video_pct" in self._data:
                self._data["video_pct"].pop(storage_key, None)
                if not self._data["video_pct"]:
                    self._data.pop("video_pct", None)
        return self

    def is_empty(self) -> bool:
        return not self._data

    def build(self) -> Optional[dict]:
        """Return the JSONB-ready dict (or ``None`` if no filter is set)."""
        return deepcopy(self._data) if self._data else None

    # -- RPC convenience ----------------------------------------------------

    def to_rpc_params(
        self,
        query: str,
        *,
        ideas: Optional[list] = None,
        country: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        channel: Optional[str] = None,
        page_num: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Build the parameter dict for ``search_sentences_v2`` / its future
        siblings. Callers still decide which RPC to POST against.
        """
        return {
            "p_query":         query,
            "p_ideas":         ideas,
            "p_country":       country,
            "p_model_filters": self.build(),
            "p_year_from":     year_from,
            "p_year_to":       year_to,
            "p_channel":       channel,
            "p_page_num":      page_num,
            "p_page_size":     page_size,
        }

    def __repr__(self) -> str:
        return f"ModelFilter({self._data!r})"
