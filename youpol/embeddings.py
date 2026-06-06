"""
Raw embedding export over the YouPol corpus (researcher+ only).

The YouPol database stores a Qwen3-Embedding-8B vector (``halfvec(1024)``) for
every transcript sentence, speaker segment, full transcript, and processed
comment. :class:`Embeddings` lets a **researcher**- or **writer**-tier token
pull those raw vectors in bulk, reproducibly, without running the 16 GB model
locally — the heavy lifting stays on the server.

Two surfaces:

1. **Bulk export** — :meth:`Embeddings.sentences` (and the segment / full-
   transcript / comment siblings) stream every matching row through a
   dedicated keyset-paginated RPC (``get_*_embeddings_v2``). Keyset pagination
   on the primary key makes a full-corpus pull O(rows) instead of the O(rows²)
   that OFFSET paging over millions of rows would cost. Each row carries its
   identifiers, the parent video's channel / date / ideas / country, and the
   embedding as a plain ``list[float]``.

2. **Query / passage encoding** — :meth:`Embeddings.encode` encodes arbitrary
   text into the *same* 1024-dim Qwen3 space via the server's encoder daemon,
   so a prototype built from seed passages is directly comparable to the
   exported corpus vectors (no local model, no version skew).

Example — pull every French far-right *political* sentence embedding and build
an NRx-prototype cosine drift, exactly as in the ``you-pol-nrx`` paper::

    from youpol import YouPol
    import numpy as np

    cli = YouPol(token="<researcher token>")

    rows = cli.embeddings.sentences(
        ideas=["Far_right"], country="FR", platform="youtube",
        pol_detect_label="political_yes", pol_detect_prob_min=0.5,
        page_size=2000,
    )
    X = np.asarray([r["embedding"] for r in rows], dtype=np.float32)

    seed = ["Les hiérarchies naturelles organisent la société.",
            "La démocratie est inefficace et doit être remplacée."]
    proto = np.asarray(cli.embeddings.encode(seed), dtype=np.float32).mean(0)
    proto /= np.linalg.norm(proto)
    nrx_score = X @ proto                      # cosine to the NRx prototype

Access tier: the ``get_*_embeddings_v2`` RPCs are granted to **researcher** and
**writer** only. With a lower tier the call raises :class:`EmbeddingAccessDenied`.
Bulk pulls count against the token's *transcription* quota.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from youpol.filters import ModelFilter


class EmbeddingAccessDenied(RuntimeError):
    """Raised when the token's tier is below ``researcher`` for an export RPC."""


class EmbeddingsUnavailable(RuntimeError):
    """Raised when :meth:`Embeddings.encode` cannot reach the encoder daemon.

    Carries ``temporarily_disabled = True`` (plus ``reason``) when the daemon
    is *deliberately* suspended (admin pause or memory-pressure auto-suspend),
    versus simply unreachable.
    """

    def __init__(self, message: str, *, temporarily_disabled: bool = False,
                 reason: Optional[str] = None):
        super().__init__(message)
        self.temporarily_disabled = temporarily_disabled
        self.reason = reason


@dataclass(slots=True)
class SentenceEmbedding:
    """One exported sentence-level embedding row.

    ``embedding`` is a 1024-element ``list[float]`` (L2-normalized,
    Qwen3-Embedding-8B). The remaining fields locate the sentence and its
    parent video. Returned by :meth:`Embeddings.sentences` when
    ``as_objects=True``; otherwise rows come back as plain dicts.
    """

    transcript_speaker_id: int
    sentence_id: int
    video_id: str
    channel_id: Optional[str]
    channel_name: Optional[str]
    upload_date: Optional[str]
    ideas_label: Optional[str]
    country_code: Optional[str]
    platform: Optional[str]
    embedding: list[float]


_ENCODE_PATH = "/api/encode-query"


class Embeddings:
    """Raw embedding export + text encoding (``client.embeddings``).

    Bound to a parent :class:`~youpol.YouPol`. Bulk-export methods mirror the
    four corpus levels:

    - :meth:`sentences`        — transcript sentences (main target)
    - :meth:`speaker_segments` — speaker turns
    - :meth:`full_transcripts` — one vector per video
    - :meth:`comments`         — comment sentences

    plus :meth:`encode` to embed arbitrary text in the same Qwen3 space.
    """

    def __init__(self, session, base_url: str):
        # `session` is the YouPol _Session (requests.Session + bearer token).
        self._session = session
        self._base_url = base_url.rstrip("/")

    # ── RPC plumbing ─────────────────────────────────────────────────────
    def _post_rpc(self, rpc: str, body: dict) -> list[dict]:
        url = f"{self._base_url}/rpc/{rpc}"
        resp = self._session._session.post(url, json=body, timeout=120)
        if resp.status_code == 403 or resp.status_code == 401:
            raise EmbeddingAccessDenied(
                "Raw embedding export requires a researcher or writer token "
                f"(server returned HTTP {resp.status_code})."
            )
        if resp.status_code >= 400:
            try:
                err = resp.json()
                msg, code = err.get("message", resp.text), err.get("code", "")
            except Exception:
                msg, code = resp.text, ""
            if code == "42501":  # permission denied for function
                raise EmbeddingAccessDenied(
                    "Permission denied: raw embedding export is restricted to "
                    "researcher / writer tiers."
                )
            raise RuntimeError(f"RPC {rpc} failed: HTTP {resp.status_code} {code} {msg[:300]}")
        return resp.json()

    @staticmethod
    def _model_filters(
        pol_detect_label: Optional[str],
        pol_detect_prob_min: Optional[float],
        model_filter: Optional[ModelFilter],
    ) -> Optional[dict]:
        """Fold the pol_detect convenience args into a ModelFilter payload."""
        mf = model_filter or ModelFilter()
        if pol_detect_label:
            mf.label("pol_detect", pol_detect_label)
        if pol_detect_prob_min is not None:
            mf.prob_range("pol_detect", min=pol_detect_prob_min)
        return mf.build()

    # ── Bulk export: sentences (main) ────────────────────────────────────
    def sentences(
        self,
        *,
        ideas: Optional[list[str]] = None,
        country: Optional[str] = None,
        platform: str = "youtube",
        pol_detect_label: Optional[str] = None,
        pol_detect_prob_min: Optional[float] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        channel: Optional[str] = None,
        suppressed_filter: Optional[str] = None,
        model_filter: Optional[ModelFilter] = None,
        page_size: int = 2000,
        max_rows: Optional[int] = None,
        as_objects: bool = False,
        progress: bool = False,
    ) -> list:
        """Export sentence-level embeddings, keyset-paginated.

        Streams every matching row from ``get_sentence_embeddings_v2`` by
        advancing on the ``(transcript_speaker_id, sentence_id)`` primary key
        — so a full-corpus pull is linear in the number of rows.

        Args:
            ideas/country/platform/channel/year_from/year_to/suppressed_filter:
                video-level filters (same semantics as ``client.search``).
            pol_detect_label: keep only sentences with this pol_detect label
                (e.g. ``"political_yes"``).
            pol_detect_prob_min: minimum pol_detect probability.
            model_filter: a :class:`~youpol.ModelFilter` for arbitrary
                classifier cross-filters (merged with the pol_detect args).
            page_size: rows per RPC call (server caps at 5000).
            max_rows: stop after this many rows (``None`` = all).
            as_objects: return :class:`SentenceEmbedding` instances instead of
                dicts.
            progress: print a one-line running count to stderr.

        Returns:
            ``list[dict]`` (or ``list[SentenceEmbedding]``). Each row:
            ``transcript_speaker_id, sentence_id, video_id, channel_id,
            channel_name, upload_date, ideas_label, country_code, platform,
            embedding (list[float])``.
        """
        mf = self._model_filters(pol_detect_label, pol_detect_prob_min, model_filter)
        out: list[dict] = []
        after_tsid: Optional[int] = None
        after_sid: Optional[int] = None
        while True:
            body = {
                "p_ideas": ideas,
                "p_country": country,
                "p_platform": platform,
                "p_model_filters": mf,
                "p_year_from": year_from,
                "p_year_to": year_to,
                "p_channel": channel,
                "p_suppressed_filter": suppressed_filter,
                "p_after_tsid": after_tsid,
                "p_after_sid": after_sid,
                "p_page_size": page_size,
            }
            page = self._post_rpc("get_sentence_embeddings_v2", body)
            if not page:
                break
            out.extend(page)
            if progress:
                import sys
                print(f"\r  embeddings.sentences: {len(out):,} rows", end="", file=sys.stderr, flush=True)
            last = page[-1]
            after_tsid, after_sid = last["transcript_speaker_id"], last["sentence_id"]
            if max_rows is not None and len(out) >= max_rows:
                out = out[:max_rows]
                break
            if len(page) < page_size:
                break
        if progress:
            import sys
            print("", file=sys.stderr)
        if as_objects:
            return [SentenceEmbedding(**{k: r.get(k) for k in SentenceEmbedding.__dataclass_fields__}) for r in out]
        return out

    # ── Bulk export: speaker segments ────────────────────────────────────
    def speaker_segments(
        self, *, ideas=None, country=None, platform="youtube",
        year_from=None, year_to=None, channel=None, suppressed_filter=None,
        page_size=2000, max_rows=None, progress=False,
    ) -> list[dict]:
        """Export speaker-segment embeddings (one vector per speaker turn)."""
        out, after_id = [], None
        while True:
            body = {
                "p_ideas": ideas, "p_country": country, "p_platform": platform,
                "p_year_from": year_from, "p_year_to": year_to, "p_channel": channel,
                "p_suppressed_filter": suppressed_filter,
                "p_after_id": after_id, "p_page_size": page_size,
            }
            page = self._post_rpc("get_speaker_embeddings_v2", body)
            if not page:
                break
            out.extend(page)
            if progress:
                import sys
                print(f"\r  embeddings.speaker_segments: {len(out):,} rows", end="", file=sys.stderr, flush=True)
            after_id = page[-1]["transcript_speaker_id"]
            if max_rows is not None and len(out) >= max_rows:
                return out[:max_rows]
            if len(page) < page_size:
                break
        return out

    # ── Bulk export: full transcripts ────────────────────────────────────
    def full_transcripts(
        self, *, ideas=None, country=None, platform="youtube",
        year_from=None, year_to=None, channel=None, suppressed_filter=None,
        page_size=2000, max_rows=None, progress=False,
    ) -> list[dict]:
        """Export one mean-pooled embedding per video transcript."""
        out, after_vid = [], None
        while True:
            body = {
                "p_ideas": ideas, "p_country": country, "p_platform": platform,
                "p_year_from": year_from, "p_year_to": year_to, "p_channel": channel,
                "p_suppressed_filter": suppressed_filter,
                "p_after_video_id": after_vid, "p_page_size": page_size,
            }
            page = self._post_rpc("get_full_transcript_embeddings_v2", body)
            if not page:
                break
            out.extend(page)
            if progress:
                import sys
                print(f"\r  embeddings.full_transcripts: {len(out):,} rows", end="", file=sys.stderr, flush=True)
            after_vid = page[-1]["video_id"]
            if max_rows is not None and len(out) >= max_rows:
                return out[:max_rows]
            if len(page) < page_size:
                break
        return out

    # ── Bulk export: comment sentences ───────────────────────────────────
    def comments(
        self, *, ideas=None, country=None, platform="youtube",
        year_from=None, year_to=None, min_likes=0,
        page_size=2000, max_rows=None, progress=False,
    ) -> list[dict]:
        """Export comment-sentence embeddings (lowest-priority backfill tier)."""
        out, after_cid, after_sid = [], None, None
        while True:
            body = {
                "p_ideas": ideas, "p_country": country, "p_platform": platform,
                "p_year_from": year_from, "p_year_to": year_to, "p_min_likes": min_likes,
                "p_after_cid": after_cid, "p_after_sid": after_sid, "p_page_size": page_size,
            }
            page = self._post_rpc("get_comment_embeddings_v2", body)
            if not page:
                break
            out.extend(page)
            if progress:
                import sys
                print(f"\r  embeddings.comments: {len(out):,} rows", end="", file=sys.stderr, flush=True)
            after_cid, after_sid = page[-1]["comment_id"], page[-1]["sentence_id"]
            if max_rows is not None and len(out) >= max_rows:
                return out[:max_rows]
            if len(page) < page_size:
                break
        return out

    # ── Text encoding (same Qwen3 space) ─────────────────────────────────
    def encode(
        self,
        texts,
        *,
        is_query: bool = False,
        instruction: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """Encode text into the corpus's 1024-dim Qwen3 space.

        Pass a single ``str`` to get one ``list[float]`` back, or a list of
        strings (≤ 256) to get a ``list[list[float]]``. ``is_query=False``
        (the default here) embeds the text as a *passage* — the right mode for
        building a prototype from seed sentences so it is comparable to the
        exported corpus vectors. Set ``is_query=True`` to use Qwen3's query
        prompt; pass ``instruction=`` for instruction-aware encoding.

        Raises :class:`EmbeddingsUnavailable` if the encoder daemon is down or
        temporarily suspended (``.temporarily_disabled`` distinguishes the two).
        """
        single = isinstance(texts, str)
        payload: dict[str, Any] = {
            "texts": [texts] if single else list(texts),
            "is_query": is_query,
        }
        if instruction:
            payload["instruction"] = instruction
        url = f"{self._base_url}{_ENCODE_PATH}"
        resp = self._session._session.post(url, json=payload, timeout=timeout)
        if resp.status_code == 503:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            raise EmbeddingsUnavailable(
                body.get("message") or body.get("detail") or "encoder daemon unavailable",
                temporarily_disabled=(body.get("status") == "temporarily_disabled"),
                reason=body.get("detail") or body.get("message"),
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"/api/encode-query failed: HTTP {resp.status_code} {resp.text[:200]}")
        data = resp.json()
        vectors = data.get("vectors")
        if vectors is None and "vector" in data:
            vectors = [data["vector"]]
        return vectors[0] if single else vectors
