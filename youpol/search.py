"""
Semantic + hybrid search over the YouPol corpus.

Wraps three concerns into a single ergonomic surface:

1. **Query encoding** — calls ``/api/encode-query`` on the server, which
   proxies to the loopback Qwen3-Embedding-8B daemon. The daemon hosts a
   single model instance shared by every gunicorn worker, so the 16 GB
   weights don't need to be loaded client-side. Optional Qwen3
   *instructions* (instruction-aware retrieval) are supported — they
   produce a more focused embedding tied to the user's stated intent
   (e.g. "find passages defending immigration", "find counter-arguments
   to X", "find passages with similar rhetorical framing").

2. **RPC dispatch** — exposes four ``search_*_v2`` RPCs (full transcripts,
   speaker segments, sentences, comments) with a uniform call signature.
   Each RPC supports three modes:

      - ``"fts"`` (default) — PostgreSQL full-text search, exact words.
      - ``"semantic"`` — Qwen3 embedding similarity (cosine).
      - ``"hybrid"`` — Reciprocal Rank Fusion of FTS + semantic.

3. **Classifier cross-filters** — every search RPC accepts a
   ``model_filter`` (a :class:`~youpol.filters.ModelFilter` instance) so
   you can intersect a semantic query with arbitrary classifier
   predictions (e.g. "find sentences semantically close to *immigration
   policy* AND classified ``political_yes`` with prob ≥ 0.8 AND part of a
   video whose comment-side political percentage is ≥ 30 %").

The server falls back to FTS automatically when ``mode='semantic'`` is
requested but no embeddings exist yet for the target table; the client
mirrors that behaviour by setting ``mode='fts'`` whenever the embedding
daemon returns 503.

Usage::

    from youpol import YouPol
    from youpol.filters import ModelFilter

    cli = YouPol(token="...")

    # Plain semantic — finds passages SEMANTICALLY close to the query,
    # not just lexical matches.
    hits = cli.search.full_transcripts(
        "désastre migratoire",
        mode="semantic",
        page_size=10,
    )

    # Instruction-aware: bias retrieval toward a specific intent.
    hits = cli.search.sentences(
        "politique migratoire",
        mode="semantic",
        instruction="Find passages defending open immigration",
        country="FR",
    )

    # Hybrid + classifier intersection: rank by RRF(FTS, semantic), keep
    # only rows the pol_detect classifier flagged as political with
    # confidence ≥ 0.8.
    flt = (ModelFilter()
           .label("pol_detect", "political_yes")
           .prob_range("pol_detect", min=0.8))
    hits = cli.search.sentences(
        "immigration",
        mode="hybrid",
        model_filter=flt,
        page_size=20,
    )

The :class:`Search` namespace is exposed as ``client.search`` on every
:class:`~youpol.YouPol` instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests

from youpol.filters import ModelFilter

# Default encoder endpoint. We hardcode the Flask host because PostgREST
# only routes /rpc/* — query encoding has to hit the Flask app directly
# at /api/encode-query. The base_url is captured at client construction
# time so callers running against a staging/dev environment get the
# right host automatically.
_ENCODE_PATH = "/api/encode-query"


class SemanticUnavailable(RuntimeError):
    """Raised when the encoder daemon is unreachable.

    Caught internally by :class:`Search`: when the server returns 503 on
    ``/api/encode-query`` the call falls back to ``mode='fts'`` so the
    user still gets results, just lexical ones. Re-raised if the caller
    explicitly set ``fallback_fts=False``.
    """


@dataclass(slots=True)
class SearchResult:
    """One result row from a ``search_*_v2`` RPC.

    The schema varies by RPC — some columns only exist on certain
    endpoints (e.g. ``speaker``, ``segment_order`` for transcript /
    speaker segment results; ``like_count`` for comments). All rows
    share ``rank``, ``total_count`` and a free-form ``extras`` dict
    holding everything else PostgREST returned, including ``headline``
    (HTML-marked snippet) and the model_labels JSONB.
    """

    rank: float
    total_count: int
    extras: dict

    def __getitem__(self, key: str) -> Any:
        return self.extras[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.extras.get(key, default)


class Search:
    """Semantic + hybrid search over the YouPol corpus.

    Bound to a parent :class:`~youpol.YouPol` instance. The methods
    follow the four corpus levels:

    - :meth:`full_transcripts` — video-level transcripts
    - :meth:`transcriptions` — speaker-segment level
    - :meth:`sentences` — sentence-segmented transcripts
    - :meth:`comments` — raw comments

    Each returns a list of :class:`SearchResult`.
    """

    def __init__(self, session, base_url: str):
        # `session` is the underlying YouPol _Session (requests.Session
        # wrapper carrying the Bearer token + Accept headers).
        self._session = session
        self._base_url = base_url.rstrip("/")

    # ── Query encoding ───────────────────────────────────────────────────
    def encode(
        self,
        query: str,
        *,
        instruction: Optional[str] = None,
        timeout: float = 30.0,
    ) -> list[float]:
        """Encode a search query into a 1024-dim Qwen3 embedding.

        Returns a plain ``list[float]`` ready to feed back to a search
        RPC as ``p_query_vec``. Raises :class:`SemanticUnavailable` if
        the encoder daemon is down (the server returns HTTP 503 with a
        ``"fallback": "fts"`` payload).

        Args:
            query: The text to encode.
            instruction: Optional Qwen3 instruction biasing retrieval
                toward a specific intent. Per Qwen3 docs this yields
                +1–5 % retrieval quality. Examples:
                    - ``"Find passages defending open immigration"``
                    - ``"Find counter-arguments to climate skepticism"``
                    - ``"Find passages with similar rhetorical framing"``
            timeout: Seconds before giving up on the server.

        Returns:
            1024-dim list of floats. Already L2-normalized; can be
            passed straight to the search RPCs.
        """
        url = f"{self._base_url}{_ENCODE_PATH}"
        payload: dict[str, Any] = {"q": query}
        if instruction:
            payload["instruction"] = instruction
        resp = self._session._session.post(url, json=payload, timeout=timeout)
        if resp.status_code == 503:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            raise SemanticUnavailable(
                body.get("detail") or "encoder daemon unavailable"
            )
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msg = body.get("error") or body.get("message") or resp.text
            except Exception:
                msg = resp.text
            raise RuntimeError(
                f"/api/encode-query failed: HTTP {resp.status_code} {msg[:200]}"
            )
        return resp.json()["vector"]

    # ── RPC plumbing ─────────────────────────────────────────────────────
    def _format_qvec(self, vec: list[float]) -> str:
        """pgvector accepts a halfvec literal as a bracketed comma list."""
        return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

    def _resolve_mode(
        self,
        mode: str,
        query: str,
        instruction: Optional[str],
        fallback_fts: bool,
    ) -> tuple[str, Optional[str]]:
        """Encode the query if needed; return (mode, qvec_str).

        Returns ``mode='fts', qvec=None`` if encoding fails AND
        ``fallback_fts=True``. Otherwise re-raises
        :class:`SemanticUnavailable`.
        """
        if mode not in ("fts", "semantic", "hybrid"):
            raise ValueError(f"mode must be 'fts' | 'semantic' | 'hybrid', got {mode!r}")
        if mode == "fts":
            return ("fts", None)
        try:
            vec = self.encode(query, instruction=instruction)
            return (mode, self._format_qvec(vec))
        except SemanticUnavailable:
            if fallback_fts:
                return ("fts", None)
            raise

    def _post_rpc(self, rpc: str, body: dict) -> list[SearchResult]:
        url = f"{self._base_url}/rpc/{rpc}"
        # Use the underlying requests.Session directly — the
        # _Session.get() helper only handles GET. We piggy-back on the
        # same auth headers.
        resp = self._session._session.post(url, json=body, timeout=60)
        if resp.status_code >= 400:
            try:
                err = resp.json()
                msg = err.get("message", resp.text)
                code = err.get("code", "")
            except Exception:
                msg, code = resp.text, ""
            raise RuntimeError(
                f"RPC {rpc} failed: HTTP {resp.status_code} {code} {msg[:300]}"
            )
        rows = resp.json()
        out: list[SearchResult] = []
        for r in rows:
            rank = float(r.pop("rank", 0.0)) if r else 0.0
            total = int(r.pop("total_count", len(rows))) if r else 0
            out.append(SearchResult(rank=rank, total_count=total, extras=r))
        return out

    def _common_params(
        self,
        query: str,
        *,
        ideas: Optional[list[str]],
        country: Optional[str],
        year_from: Optional[int],
        year_to: Optional[int],
        channel: Optional[str],
        page_num: int,
        page_size: int,
        suppressed_filter: Optional[str],
        platform: Optional[str],
        model_filter: Optional[ModelFilter],
    ) -> dict:
        return {
            "p_query":             query,
            "p_ideas":             ideas,
            "p_country":           country,
            "p_model_filters":     model_filter.build() if model_filter else None,
            "p_year_from":         year_from,
            "p_year_to":           year_to,
            "p_channel":           channel,
            "p_page_num":          page_num,
            "p_page_size":         page_size,
            "p_suppressed_filter": suppressed_filter,
            "p_platform":          platform,
        }

    # ── Search endpoints ─────────────────────────────────────────────────
    def full_transcripts(
        self,
        query: str,
        *,
        mode: str = "fts",
        instruction: Optional[str] = None,
        ideas: Optional[list[str]] = None,
        country: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        channel: Optional[str] = None,
        page_num: int = 1,
        page_size: int = 20,
        suppressed_filter: Optional[str] = None,
        platform: Optional[str] = None,
        model_filter: Optional[ModelFilter] = None,
        fallback_fts: bool = True,
    ) -> list[SearchResult]:
        """Search at the video level (mean-pooled full-transcript embedding).

        Best for "find videos that talk about X". Returns one row per
        video; ``extras`` includes the cleaned transcript and a marked
        ``headline`` snippet.
        """
        mode_eff, qvec = self._resolve_mode(mode, query, instruction, fallback_fts)
        body = self._common_params(
            query,
            ideas=ideas, country=country, year_from=year_from,
            year_to=year_to, channel=channel,
            page_num=page_num, page_size=page_size,
            suppressed_filter=suppressed_filter, platform=platform,
            model_filter=model_filter,
        )
        body["p_search_type"] = mode_eff
        if qvec is not None:
            body["p_query_vec"] = qvec
        return self._post_rpc("search_full_transcripts_v2", body)

    def transcriptions(
        self,
        query: str,
        *,
        mode: str = "fts",
        instruction: Optional[str] = None,
        ideas: Optional[list[str]] = None,
        country: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        channel: Optional[str] = None,
        page_num: int = 1,
        page_size: int = 20,
        suppressed_filter: Optional[str] = None,
        platform: Optional[str] = None,
        model_filter: Optional[ModelFilter] = None,
        fallback_fts: bool = True,
    ) -> list[SearchResult]:
        """Search at the speaker-segment level (one row per speaker turn).

        Best for "find specific moments inside a video". Each row carries
        the segment's text, the surrounding video metadata, and the
        per-segment ``pol_detect`` columns.
        """
        mode_eff, qvec = self._resolve_mode(mode, query, instruction, fallback_fts)
        body = self._common_params(
            query,
            ideas=ideas, country=country, year_from=year_from,
            year_to=year_to, channel=channel,
            page_num=page_num, page_size=page_size,
            suppressed_filter=suppressed_filter, platform=platform,
            model_filter=model_filter,
        )
        body["p_search_type"] = mode_eff
        if qvec is not None:
            body["p_query_vec"] = qvec
        return self._post_rpc("search_transcriptions_v2", body)

    def sentences(
        self,
        query: str,
        *,
        mode: str = "fts",
        instruction: Optional[str] = None,
        ideas: Optional[list[str]] = None,
        country: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        channel: Optional[str] = None,
        page_num: int = 1,
        page_size: int = 20,
        suppressed_filter: Optional[str] = None,
        platform: Optional[str] = None,
        model_filter: Optional[ModelFilter] = None,
        fallback_fts: bool = True,
    ) -> list[SearchResult]:
        """Search at the sentence level (transcript_speakers_processed).

        Finest granularity for transcripts. Each row is a single sentence
        with its own ``pol_detect`` and any other active classifier
        columns. This is the main retrieval target for SIED-style
        sentence augmentation pipelines.
        """
        mode_eff, qvec = self._resolve_mode(mode, query, instruction, fallback_fts)
        body = self._common_params(
            query,
            ideas=ideas, country=country, year_from=year_from,
            year_to=year_to, channel=channel,
            page_num=page_num, page_size=page_size,
            suppressed_filter=suppressed_filter, platform=platform,
            model_filter=model_filter,
        )
        body["p_search_type"] = mode_eff
        if qvec is not None:
            body["p_query_vec"] = qvec
        return self._post_rpc("search_sentences_v2", body)

    def comments(
        self,
        query: str,
        *,
        mode: str = "fts",
        instruction: Optional[str] = None,
        ideas: Optional[list[str]] = None,
        country: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        min_likes: int = 0,
        page_num: int = 1,
        page_size: int = 20,
        suppressed_filter: Optional[str] = None,
        platform: Optional[str] = None,
        model_filter: Optional[ModelFilter] = None,
        fallback_fts: bool = True,
    ) -> list[SearchResult]:
        """Search YouTube + TikTok comments (raw, one row per comment).

        ``min_likes`` lets you filter out low-engagement comments; the
        rest of the parameters behave the same as the transcript-side
        searches. Note: comments are the lowest-priority tier of the
        embedding backfill (~19 M rows), so ``mode='semantic'`` may
        silently degrade to FTS for a while after initial deployment.
        """
        mode_eff, qvec = self._resolve_mode(mode, query, instruction, fallback_fts)
        body = {
            "p_query":             query,
            "p_ideas":             ideas,
            "p_country":           country,
            "p_model_filters":     model_filter.build() if model_filter else None,
            "p_min_likes":         min_likes,
            "p_year_from":         year_from,
            "p_year_to":           year_to,
            "p_page_num":          page_num,
            "p_page_size":         page_size,
            "p_suppressed_filter": suppressed_filter,
            "p_platform":          platform,
            "p_search_type":       mode_eff,
        }
        if qvec is not None:
            body["p_query_vec"] = qvec
        return self._post_rpc("search_comments_v2", body)
