"""
YouPol API client.

Wraps the PostgREST API at https://data.you-pol.com/ with a typed,
ergonomic Python interface. All endpoints serve unified views covering
both YouTube and TikTok data — use ``platform="youtube"`` or
``platform="tiktok"`` to filter by platform.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlencode

import requests

from youpol.models import (
    Video,
    Comment,
    Transcript,
    SpeakerSegment,
    ProcessedComment,
    ProcessedSpeakerSegment,
    MetadataSnapshot,
    ChannelSnapshot,
    SearchResult,
)

API_URL = "https://data.you-pol.com"


class APIError(Exception):
    """Raised when the API returns an error response."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        super().__init__(f"[{status_code}] {code}: {message}")


class _Session:
    """Thin wrapper around requests.Session with auth and pagination."""

    def __init__(self, token: str, base_url: str):
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"
        self._session.headers["Accept"] = "application/json"
        self._base_url = base_url.rstrip("/")

    def get(self, path: str, params: dict | None = None) -> list[dict]:
        """Single-page GET request."""
        url = f"{self._base_url}/{path}"
        resp = self._session.get(url, params=params)
        if resp.status_code >= 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            raise APIError(resp.status_code, body.get("code", ""), body.get("message", resp.text))
        return resp.json()

    def get_paginated(self, path: str, params: dict | None = None, limit: int | None = None) -> list[dict]:
        """Auto-paginated GET. Fetches all pages up to ``limit`` rows."""
        params = dict(params or {})
        collected = []
        offset = int(params.pop("offset", 0))
        page_size = min(1000, limit) if limit else 1000

        while True:
            page_params = {**params, "limit": page_size, "offset": offset}
            page = self.get(path, page_params)
            collected.extend(page)

            if limit and len(collected) >= limit:
                return collected[:limit]
            if len(page) < page_size:
                return collected

            offset += len(page)

    def head(self, path: str, params: dict | None = None) -> dict:
        """HEAD request — returns headers (useful for count)."""
        url = f"{self._base_url}/{path}"
        params = dict(params or {})
        resp = self._session.head(url, params=params, headers={
            **self._session.headers,
            "Prefer": "count=exact",
        })
        if resp.status_code >= 400:
            raise APIError(resp.status_code, "", resp.text)
        return dict(resp.headers)

    def rpc(self, func_name: str, params: dict) -> list[dict]:
        """Call a PostgREST RPC function via POST."""
        url = f"{self._base_url}/rpc/{func_name}"
        resp = self._session.post(url, json=params, headers={
            "Content-Type": "application/json",
        })
        if resp.status_code >= 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            raise APIError(resp.status_code, body.get("code", ""), body.get("message", resp.text))
        return resp.json()


def _parse_filters(filters: dict[str, Any]) -> dict[str, str]:
    """Convert keyword filters to PostgREST query parameters.

    Supports:
        - Simple equality: ``channel_name="Psyhodelik"`` -> ``channel_name=eq.Psyhodelik``
        - Operator prefix: ``video_views="gte.1000"`` -> ``video_views=gte.1000``
        - List (IN): ``country=["FR", "QC"]`` -> ``country=in.(FR,QC)``
        - None (IS NULL): ``description=None`` -> ``description=is.null``
    """
    OPERATORS = {"eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike", "is", "in", "cs", "cd", "not"}
    params = {}
    for key, value in filters.items():
        if value is None:
            params[key] = "is.null"
        elif isinstance(value, list):
            params[key] = f"in.({','.join(str(v) for v in value)})"
        elif isinstance(value, bool):
            params[key] = f"eq.{'true' if value else 'false'}"
        elif isinstance(value, str) and any(value.startswith(f"{op}.") for op in OPERATORS):
            params[key] = value
        else:
            params[key] = f"eq.{value}"
    return params


class _TableEndpoint:
    """Base class for table-specific endpoints."""

    _table: str
    _model: type

    def __init__(self, session: _Session):
        self._session = session

    def list(
        self,
        *,
        select: str | list[str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        **filters: Any,
    ) -> list:
        """Query rows from this table.

        Args:
            select: Columns to return. Pass a comma-separated string or a list.
                Defaults to all columns.
            order: Sort order. Examples: ``"video_views.desc"``,
                ``"upload_date.asc"``, ``"video_views.desc,upload_date.asc"``.
            limit: Maximum number of rows to return. The client automatically
                paginates if needed. Pass ``None`` to fetch all matching rows.
            offset: Number of rows to skip.
            **filters: Column filters. See examples below.

        Returns:
            List of model instances.

        Filter syntax:
            Simple equality::

                client.videos.list(country="FR")

            Comparison operators (prefix with operator and dot)::

                client.videos.list(video_views="gte.10000")

            Pattern matching::

                client.videos.list(channel_name="ilike.*politique*")

            Multiple values (IN)::

                client.videos.list(country=["FR", "QC"])

            NULL check::

                client.videos.list(description=None)

            Platform filter::

                client.videos.list(platform="youtube")
                client.videos.list(platform="tiktok")

            Status filter::

                client.videos.list(status="active")
                client.videos.list(status="suppressed")
        """
        params = _parse_filters(filters)
        if select:
            params["select"] = ",".join(select) if isinstance(select, list) else select
        if order:
            params["order"] = order
        if offset:
            params["offset"] = offset

        rows = self._session.get_paginated(self._table, params, limit=limit)
        return [self._model(**row) for row in rows]

    def get(self, **key_filters: Any):
        """Fetch a single row by primary key.

        Args:
            **key_filters: Primary key column(s) and value(s).

        Returns:
            A single model instance.

        Raises:
            APIError: If the row is not found.

        Example::

            video = client.videos.get(video_id="dQw4w9WgXcQ")
        """
        params = {k: f"eq.{v}" for k, v in key_filters.items()}
        params["limit"] = 1
        rows = self._session.get(self._table, params)
        if not rows:
            raise APIError(404, "NOT_FOUND", f"No row found with {key_filters}")
        return self._model(**rows[0])

    def count(self, **filters: Any) -> int:
        """Count rows matching the given filters.

        Returns:
            Integer count of matching rows.

        Example::

            n = client.comments.count(video_id="dQw4w9WgXcQ")
        """
        params = _parse_filters(filters)
        headers = self._session.head(self._table, params)
        content_range = headers.get("Content-Range", headers.get("content-range", ""))
        # Format: "0-N/total" or "*/total"
        if "/" in content_range:
            total = content_range.split("/")[-1]
            if total != "*":
                return int(total)
        # Fallback: fetch with count
        params["limit"] = 0
        params["select"] = list(params.get("select", "").split(","))[:1] or ["*"]
        return 0


# ---------------------------------------------------------------------------
# Unified endpoints (YouTube + TikTok via PostgREST views)
# ---------------------------------------------------------------------------

class Videos(_TableEndpoint):
    """Endpoint for the ``videos_with_update`` view (~23,500 rows).

    Unified view of YouTube and TikTok videos with metadata, research
    annotations, and content status tracking.

    Key columns:
        - ``video_id`` (str, PK): Platform video ID
        - ``channel_name``, ``video_title`` (str): Video metadata
        - ``video_views``, ``video_likes``, ``video_comments_count`` (int): Engagement
        - ``ideas`` (str): Political orientation — "Far_right", "Left", "Masc", "Comp"
        - ``country`` (str): "FR" or "QC"
        - ``gender`` (str): "H", "F", or "Mixte"
        - ``status`` (str): "active", "suppressed", or "trashed"
        - ``platform`` (str): "youtube" or "tiktok"
        - ``suppressed_at`` (timestamp): When flagged as suppressed
        - ``suppression_reason`` (str): Why suppressed
        - ``last_update`` (timestamp): Last metadata scan

    Examples::

        # YouTube only, most viewed
        videos = client.videos.list(platform="youtube", order="video_views.desc", limit=10)

        # All active Far Right videos
        videos = client.videos.list(ideas="Far_right", status="active")

        # Suppressed content
        deleted = client.videos.list(status="suppressed", limit=100)
    """

    _table = "videos_with_update"
    _model = Video


class Comments(_TableEndpoint):
    """Endpoint for the ``comments_with_status`` view (~7.5M rows).

    Unified view of YouTube and TikTok comments with suppression status.

    Key columns:
        - ``comment_id`` (int, PK), ``text`` (str): Comment content
        - ``like_count`` (int): Likes on the comment
        - ``video_id`` (str, FK): Parent video
        - ``author`` (str): Commenter display name
        - ``status`` (str): "active" or "suppressed"
        - ``platform`` (str): "youtube" or "tiktok"

    Examples::

        # YouTube comments for a video
        comments = client.comments.list(video_id="abc123", platform="youtube", limit=100)

        # Top comments by likes
        comments = client.comments.list(order="like_count.desc", limit=10)
    """

    _table = "comments_with_status"
    _model = Comment


class Transcripts(_TableEndpoint):
    """Endpoint for the ``video_transcripts`` view (~21,000 rows).

    Unified view of YouTube and TikTok video transcripts with content status
    derived from the parent video.

    Key columns:
        - ``video_id`` (str, PK): Video ID
        - ``cleaned_transcript`` (str): Cleaned transcript text
        - ``original_diarized_transcript`` (str): Raw transcript with speaker markers
        - ``transcript_status`` (str): "ok" or "no_speech"
        - ``status`` (str): "active" or "suppressed" (from parent video)
        - ``platform`` (str): "youtube" or "tiktok"

    Examples::

        # Get transcript for a video
        transcript = client.transcripts.get(video_id="abc123")

        # Only active transcripts
        transcripts = client.transcripts.list(status="active", transcript_status="eq.ok")
    """

    _table = "video_transcripts"
    _model = Transcript


class SpeakerSegments(_TableEndpoint):
    """Endpoint for the ``speakers_with_pol`` view (~612K rows).

    Unified view of YouTube and TikTok speaker-diarized transcript segments
    with political content detection and aggregated statistics.

    Key columns:
        - ``transcript_speaker_id`` (int, PK): Internal ID
        - ``video_id`` (str, FK): Video ID
        - ``speaker`` (str): Speaker label (e.g. "SPEAKER_00")
        - ``speaker_transcript`` (str): Segment text
        - ``pol_detect_label`` (str): "political_yes" or "political_no"
        - ``pol_detect_probability`` (float): Classifier confidence (0-1)
        - ``pct_political`` (float): % political sentences in segment
        - ``avg_confidence`` (float): Average confidence for political sentences
        - ``status`` (str): "active" or "suppressed"
        - ``platform`` (str): "youtube" or "tiktok"

    Examples::

        # All segments for a video, in order
        segments = client.speaker_segments.list(video_id="abc123", order="segment_order.asc")

        # High-confidence political segments
        political = client.speaker_segments.list(
            pol_detect_label="political_yes",
            pol_detect_probability="gte.0.9",
            limit=100,
        )
    """

    _table = "speakers_with_pol"
    _model = SpeakerSegment


class ProcessedComments(_TableEndpoint):
    """Endpoint for the ``comments_processed`` view (~9.8M rows).

    Sentence-level processed comments with NER annotations.
    Unified YouTube + TikTok.

    Key columns:
        - ``comment_id`` (int, PK), ``sentence_id`` (int, PK): Composite key
        - ``text`` (str): Sentence text
        - ``ner_entities`` (dict): NER results (PER, LOC, ORG lists)

    Examples::

        # Get NER-annotated sentences for a video's comments
        processed = client.processed_comments.list(video_id="abc123", limit=100)
        for p in processed:
            if p.ner_entities and p.ner_entities.get("PER"):
                print(f"{p.text} -> persons: {p.ner_entities['PER']}")
    """

    _table = "comments_processed"
    _model = ProcessedComment


class ProcessedSpeakerSegments(_TableEndpoint):
    """Endpoint for the ``transcription_speakers_processed`` view (~5.4M rows).

    Sentence-level processed speaker segments with NER and political classification.
    Unified YouTube + TikTok.

    Key columns:
        - ``transcript_speaker_id`` (int, PK), ``sentence_id`` (int, PK): Composite key
        - ``speaker_transcript`` (str): Sentence text
        - ``ner_entities`` (dict): NER results (PER, LOC, ORG lists)
        - ``pol_detect_label`` (str): "political_yes" or "political_no"
        - ``pol_detect_probability`` (float): Confidence (0-1)

    Examples::

        sentences = client.processed_speaker_segments.list(
            video_id="abc123",
            order="segment_order.asc,sentence_id.asc",
            limit=200,
        )
    """

    _table = "transcription_speakers_processed"
    _model = ProcessedSpeakerSegment


class VideoMetadataHistory(_TableEndpoint):
    """Endpoint for the ``video_metadata_history`` view.

    Longitudinal metadata snapshots — one row per video per metadata scan.
    Unified YouTube + TikTok.

    Key columns:
        - ``id`` (int, PK): Snapshot ID
        - ``video_id`` (str): Video ID
        - ``video_views``, ``video_likes``, ``video_comments_count`` (int)
        - ``subscribers`` (int): Channel subscriber count at scan time
        - ``video_title`` (str): Title at scan time (tracks changes)
        - ``scanned_at`` (timestamp): Scan timestamp

    Examples::

        history = client.metadata_history.list(video_id="abc123", order="scanned_at.asc")
    """

    _table = "video_metadata_history"
    _model = MetadataSnapshot


class ChannelMetadataHistory(_TableEndpoint):
    """Endpoint for the ``channel_metadata_history`` view.

    Longitudinal channel snapshots. Unified YouTube + TikTok.

    Key columns:
        - ``id`` (int, PK): Snapshot ID
        - ``channel_name`` (str), ``channel_id`` (str)
        - ``subscribers`` (int): Subscriber count at scan time
        - ``total_videos_yt``, ``total_videos_db``, ``total_transcribed`` (int)
        - ``scanned_at`` (timestamp): Scan timestamp

    Examples::

        history = client.channel_history.list(channel_name="MyChannel", order="scanned_at.asc")
    """

    _table = "channel_metadata_history"
    _model = ChannelSnapshot


# ---------------------------------------------------------------------------
# Analytics views
# ---------------------------------------------------------------------------

class AnalyticsByMonth(_TableEndpoint):
    """Endpoint for the ``analytics_by_month`` view.

    Monthly aggregation of political speech detection across the corpus.

    Columns: ``month``, ``total_sentences``, ``political_sentences``, ``pct_political``
    """
    _table = "analytics_by_month"
    _model = dict

class AnalyticsByChannel(_TableEndpoint):
    """Endpoint for the ``analytics_by_channel`` view.

    Per-channel aggregation of political speech detection.

    Columns: ``channel_name``, ``total_sentences``, ``political_sentences``, ``pct_political``
    """
    _table = "analytics_by_channel"
    _model = dict

class AnalyticsByCountry(_TableEndpoint):
    """Endpoint for the ``analytics_by_country`` view.

    Per-country aggregation of political speech detection.

    Columns: ``country``, ``total_sentences``, ``political_sentences``, ``pct_political``
    """
    _table = "analytics_by_country"
    _model = dict

class AnalyticsByGender(_TableEndpoint):
    """Endpoint for the ``analytics_by_gender`` view.

    Per-gender aggregation of political speech detection.

    Columns: ``gender``, ``total_sentences``, ``political_sentences``, ``pct_political``
    """
    _table = "analytics_by_gender"
    _model = dict


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------

class YouPol:
    """Client for the YouPol research database API.

    The YouPol database contains political content data from YouTube and TikTok
    collected for academic research. It includes ~23,500 videos, ~7.5M comments,
    ~21,000 transcripts, ~612K speaker segments, and NLP-processed versions
    with NER annotations and political speech classification.

    All data endpoints serve unified views covering both YouTube and TikTok.
    Use ``platform="youtube"`` or ``platform="tiktok"`` to filter by platform.

    Args:
        token: JWT authentication token. Obtain one from the project
            administrators.
        base_url: API base URL. Defaults to ``https://data.you-pol.com``.

    Attributes:
        videos: Videos with metadata and status (~23,500 rows).
        comments: Comments with suppression status (~7.5M rows).
        transcripts: Full video transcripts (~21,000 rows).
        speaker_segments: Speaker-diarized segments with political detection (~612K rows).
        processed_comments: Sentence-level comments with NER (~9.8M rows).
        processed_speaker_segments: Sentence-level segments with NER (~5.4M rows).
        metadata_history: Longitudinal video metadata snapshots.
        channel_history: Longitudinal channel metadata snapshots.
        analytics_by_month: Monthly political speech aggregation.
        analytics_by_channel: Per-channel political speech aggregation.
        analytics_by_country: Per-country political speech aggregation.
        analytics_by_gender: Per-gender political speech aggregation.

    Example::

        from youpol import YouPol

        client = YouPol(token="your_jwt_token")

        # Browse videos
        videos = client.videos.list(country="FR", order="video_views.desc", limit=10)
        for v in videos:
            print(f"{v.video_title} ({v.platform}) — {v.video_views:,} views")

        # Full-text search
        results = client.search_comments("immigration", page_size=10)

        # Export to pandas DataFrame
        df = client.videos.to_dataframe(country="FR", limit=100)
    """

    def __init__(self, token: str, base_url: str = API_URL):
        self._session = _Session(token, base_url)

        # Unified endpoints (YouTube + TikTok)
        self.videos = Videos(self._session)
        self.comments = Comments(self._session)
        self.transcripts = Transcripts(self._session)
        self.speaker_segments = SpeakerSegments(self._session)
        self.processed_comments = ProcessedComments(self._session)
        self.processed_speaker_segments = ProcessedSpeakerSegments(self._session)
        self.metadata_history = VideoMetadataHistory(self._session)
        self.channel_history = ChannelMetadataHistory(self._session)

        # Analytics views
        self.analytics_by_month = AnalyticsByMonth(self._session)
        self.analytics_by_channel = AnalyticsByChannel(self._session)
        self.analytics_by_country = AnalyticsByCountry(self._session)
        self.analytics_by_gender = AnalyticsByGender(self._session)

    # ------------------------------------------------------------------
    # Full-text search methods (via PostgREST RPC functions)
    # ------------------------------------------------------------------

    def search_videos(
        self,
        query: str,
        *,
        suppressed_filter: str | None = None,
        platform_filter: str | None = None,
        page_num: int = 1,
        page_size: int = 50,
    ) -> list[dict]:
        """Search videos by title, channel name, or description.

        Uses trigram similarity matching for fuzzy search with relevance ranking.

        Args:
            query: Search query string.
            suppressed_filter: ``None`` (active only), ``"only"`` (deleted only),
                ``"all"`` (include deleted).
            platform_filter: ``None`` (all), ``"youtube"``, or ``"tiktok"``.
            page_num: Page number (1-indexed).
            page_size: Results per page.

        Returns:
            List of dicts with video columns plus ``headline``, ``rank``,
            and ``total_count``.
        """
        return self._session.rpc("search_videos_table", {
            "query": query,
            "suppressed_filter": suppressed_filter,
            "platform_filter": platform_filter,
            "page_num": page_num,
            "page_size": page_size,
        })

    def search_comments(
        self,
        query: str,
        *,
        suppressed_filter: str | None = None,
        platform_filter: str | None = None,
        min_likes: int = 0,
        page_num: int = 1,
        page_size: int = 50,
    ) -> list[dict]:
        """Full-text search in comments using French-language stemming.

        Uses PostgreSQL tsvector full-text search with GIN indexes for fast
        ranked results. Returns highlighted text excerpts.

        Args:
            query: Search query (supports French stemming).
            suppressed_filter: ``None`` (active only), ``"only"``, ``"all"``.
            platform_filter: ``None`` (all), ``"youtube"``, or ``"tiktok"``.
            min_likes: Minimum like count filter.
            page_num: Page number (1-indexed).
            page_size: Results per page.

        Returns:
            List of dicts with comment columns plus ``headline`` (HTML with
            ``<mark>`` tags), ``rank``, and ``total_count``.
        """
        return self._session.rpc("search_comments_table", {
            "query": query,
            "suppressed_filter": suppressed_filter,
            "platform_filter": platform_filter,
            "min_likes": min_likes,
            "page_num": page_num,
            "page_size": page_size,
        })

    def search_transcripts(
        self,
        query: str,
        *,
        suppressed_filter: str | None = None,
        platform_filter: str | None = None,
        page_num: int = 1,
        page_size: int = 50,
    ) -> list[dict]:
        """Full-text search in video transcripts using French-language stemming.

        Args:
            query: Search query (supports French stemming).
            suppressed_filter: ``None`` (active only), ``"only"``, ``"all"``.
            platform_filter: ``None`` (all), ``"youtube"``, or ``"tiktok"``.
            page_num: Page number (1-indexed).
            page_size: Results per page.

        Returns:
            List of dicts with transcript columns plus ``headline``, ``rank``,
            and ``total_count``.
        """
        return self._session.rpc("search_transcripts_table", {
            "query": query,
            "suppressed_filter": suppressed_filter,
            "platform_filter": platform_filter,
            "page_num": page_num,
            "page_size": page_size,
        })

    def search_speakers(
        self,
        query: str,
        *,
        suppressed_filter: str | None = None,
        platform_filter: str | None = None,
        page_num: int = 1,
        page_size: int = 50,
    ) -> list[dict]:
        """Full-text search in speaker segments using French-language stemming.

        Args:
            query: Search query (supports French stemming).
            suppressed_filter: ``None`` (active only), ``"only"``, ``"all"``.
            platform_filter: ``None`` (all), ``"youtube"``, or ``"tiktok"``.
            page_num: Page number (1-indexed).
            page_size: Results per page.

        Returns:
            List of dicts with speaker segment columns plus ``headline``,
            ``rank``, and ``total_count``.
        """
        return self._session.rpc("search_speakers_table", {
            "query": query,
            "suppressed_filter": suppressed_filter,
            "platform_filter": platform_filter,
            "page_num": page_num,
            "page_size": page_size,
        })
