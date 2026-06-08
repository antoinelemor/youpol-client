"""
youpol.export
=============

Corpus-scale bulk export for ANALYSIS, backed by dedicated keyset-paginated
server RPCs (``get_political_sentences``, ``get_comment_politicization``).

These replace the slow per-video access patterns: instead of one request per
video for sentence themes, and two ``count`` requests per video for comment
politicization, the join + classifier reconstruction + aggregation run inside
Postgres and stream back in pages — a full-corpus pull is linear in the number
of rows (sentences) or videos, not in round trips.

    client.export.political_sentences(ideas=["Far_right"], country="FR",
                                      year_from=2016, year_to=2024)
    client.export.comment_politicization(ideas=["Far_right"], country="FR",
                                         year_from=2016, year_to=2024)

Both require a researcher- or writer-tier token (same governance as the raw
embedding export).
"""
from __future__ import annotations

import sys
from typing import Optional


class ExportAccessDenied(RuntimeError):
    """Raised when the token lacks the researcher/writer tier for export RPCs."""


class Export:
    """Keyset-paginated bulk-export endpoint (analysis-ready corpus pulls)."""

    def __init__(self, session, base_url: str):
        self._session = session
        self._base_url = base_url.rstrip("/")

    # ── RPC plumbing ─────────────────────────────────────────────────────────
    def _post_rpc(self, rpc: str, body: dict) -> list[dict]:
        url = f"{self._base_url}/rpc/{rpc}"
        resp = self._session._session.post(url, json=body, timeout=180)
        if resp.status_code in (401, 403):
            raise ExportAccessDenied(
                "Corpus export requires a researcher or writer token "
                f"(server returned HTTP {resp.status_code})."
            )
        if resp.status_code >= 400:
            try:
                err = resp.json()
                msg, code = err.get("message", resp.text), err.get("code", "")
            except Exception:
                msg, code = resp.text, ""
            if code == "42501":
                raise ExportAccessDenied(
                    "Permission denied: corpus export is restricted to "
                    "researcher / writer tiers."
                )
            raise RuntimeError(f"RPC {rpc} failed: HTTP {resp.status_code} {code} {msg[:300]}")
        return resp.json()

    # ── Political sentences + per-theme P(yes) ────────────────────────────────
    def political_sentences(
        self,
        *,
        ideas: Optional[list[str]] = None,
        country: Optional[str] = None,
        platform: str = "youtube",
        pol_label: Optional[str] = "political_yes",
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        channel: Optional[str] = None,
        suppressed_filter: Optional[str] = None,
        page_size: int = 2000,
        max_rows: Optional[int] = None,
        progress: bool = False,
    ) -> list[dict]:
        """Export political transcript sentences with per-theme P(yes).

        Streams ``get_political_sentences`` by advancing on the
        ``(transcript_speaker_id, sentence_id)`` primary key.

        Each row is a dict::

            transcript_speaker_id, sentence_id, video_id, channel_id,
            channel_name, upload_date, ideas_label, country_code, platform,
            pol_detect_label, themes  # {theme_key: P(yes) float}

        ``themes`` is a dict mapping each active SIED theme storage key
        (e.g. ``"theme_equality"``) to the reconstructed P(theme = yes).
        """
        out: list[dict] = []
        after_tsid: Optional[int] = None
        after_sid: Optional[int] = None
        while True:
            body = {
                "p_ideas": ideas,
                "p_country": country,
                "p_platform": platform,
                "p_pol_label": pol_label,
                "p_year_from": year_from,
                "p_year_to": year_to,
                "p_channel": channel,
                "p_suppressed_filter": suppressed_filter,
                "p_after_tsid": after_tsid,
                "p_after_sid": after_sid,
                "p_page_size": page_size,
            }
            page = self._post_rpc("get_political_sentences", body)
            if not page:
                break
            out.extend(page)
            if progress:
                print(f"\r  export.political_sentences: {len(out):,} rows",
                      end="", file=sys.stderr, flush=True)
            last = page[-1]
            after_tsid, after_sid = last["transcript_speaker_id"], last["sentence_id"]
            if max_rows is not None and len(out) >= max_rows:
                out = out[:max_rows]
                break
            if len(page) < page_size:
                break
        if progress:
            print("", file=sys.stderr)
        return out

    # ── Comment politicization aggregated per video ───────────────────────────
    def comment_politicization(
        self,
        *,
        ideas: Optional[list[str]] = None,
        country: Optional[str] = None,
        platform: str = "youtube",
        pol_label: str = "political_yes",
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        suppressed_filter: Optional[str] = None,
        page_size: int = 5000,
        max_rows: Optional[int] = None,
        progress: bool = False,
    ) -> list[dict]:
        """Per-video comment-politicization counts, aggregated server-side.

        Streams ``get_comment_politicization`` by advancing on ``video_id``.
        Each row is a dict ``{video_id, n_sentences, n_political}`` where
        ``n_sentences`` is the number of comment sentences for the video and
        ``n_political`` the number classified ``pol_label``.
        """
        out: list[dict] = []
        after_video: Optional[str] = None
        while True:
            body = {
                "p_ideas": ideas,
                "p_country": country,
                "p_platform": platform,
                "p_pol_label": pol_label,
                "p_year_from": year_from,
                "p_year_to": year_to,
                "p_suppressed_filter": suppressed_filter,
                "p_after_video": after_video,
                "p_page_size": page_size,
            }
            page = self._post_rpc("get_comment_politicization", body)
            if not page:
                break
            out.extend(page)
            if progress:
                print(f"\r  export.comment_politicization: {len(out):,} videos",
                      end="", file=sys.stderr, flush=True)
            after_video = page[-1]["video_id"]
            if max_rows is not None and len(out) >= max_rows:
                out = out[:max_rows]
                break
            if len(page) < page_size:
                break
        if progress:
            print("", file=sys.stderr)
        return out
