"""
YouPol API client.

Wraps the PostgREST API at https://data.you-pol.com/ with a typed,
ergonomic Python interface.

Access is governed by five token tiers (metadata, analyst_1, analyst_2,
researcher, writer) with configurable rate limits. See the README for
details on what each tier can access.
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
)

API_URL = "https://data.you-pol.com"
MAX_PAGE_SIZE = 200  # Server-enforced maximum


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
        page_size = min(MAX_PAGE_SIZE, limit) if limit else MAX_PAGE_SIZE

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
                paginates if this exceeds the server page size (200).
                Pass ``None`` to fetch all matching rows.
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

            Negation::

                client.videos.list(suppressed="eq.false")
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


class Videos(_TableEndpoint):
    """Endpoint for the ``videos`` table (~22,800 rows).

    The central table of the YouPol corpus. Each row is a YouTube video
    with metadata (title, views, likes, etc.) and research annotations
    (gender, country, ideas).

    Columns:
        - ``video_id`` (str, PK): YouTube video ID
        - ``channel_name`` (str): Channel display name
        - ``video_title`` (str): Video title
        - ``video_views`` (int): View count
        - ``subscribers`` (int): Channel subscriber count
        - ``video_likes`` (int): Like count
        - ``video_comments_count`` (int): Comment count
        - ``link`` (str): Full YouTube URL
        - ``tags`` (list[str]): Video tags
        - ``duration`` (int): Duration in seconds
        - ``channel_id`` (str): YouTube channel ID
        - ``description`` (str): Video description
        - ``upload_date`` (date): Upload date
        - ``suppressed`` (bool): Whether video was removed
        - ``original_channel`` (str): Original channel if re-uploaded
        - ``ideas`` (str): Annotated main ideas/topics
        - ``gender`` (str): Speaker gender — "H", "F", or "Mixte"
        - ``playlist`` (str): In playlist — "0" or "1"
        - ``country`` (str): Channel country — "FR" or "QC"

    Examples::

        # Get 10 most viewed French videos
        videos = client.videos.list(
            country="FR",
            order="video_views.desc",
            limit=10,
        )

        # Get a specific video
        video = client.videos.get(video_id="dQw4w9WgXcQ")

        # Search by title
        videos = client.videos.list(video_title="ilike.*macron*")

        # Only select certain columns
        videos = client.videos.list(
            select=["video_id", "video_title", "video_views"],
            limit=5,
        )
    """

    _table = "videos_with_update"
    _model = Video


class Comments(_TableEndpoint):
    """Endpoint for the ``comments`` table (~7.3M rows).

    YouTube comments collected from videos in the corpus.

    Columns:
        - ``comment_id`` (int, PK): Internal auto-incremented ID
        - ``id`` (str, unique): YouTube comment ID
        - ``parent`` (str): Parent comment ID (for replies)
        - ``video_id`` (str, FK -> videos): Video this comment belongs to
        - ``channel_name`` (str): Channel name (denormalized)
        - ``video_title`` (str): Video title (denormalized)
        - ``video_views`` (int): View count (denormalized)
        - ``subscribers`` (int): Subscriber count (denormalized)
        - ``video_likes`` (int): Like count (denormalized)
        - ``link`` (str): Video URL (denormalized)
        - ``text`` (str): Comment text
        - ``like_count`` (int): Likes on the comment
        - ``author_id`` (str): Commenter's YouTube user ID
        - ``author`` (str): Commenter's display name
        - ``author_thumbnail`` (str): Commenter's profile picture URL
        - ``author_is_uploader`` (bool): True if commenter = video uploader
        - ``author_is_verified`` (bool): True if commenter is verified
        - ``author_url`` (str): Commenter's channel URL
        - ``is_favorited`` (bool): Favorited by uploader
        - ``_time_text`` (str): Relative time text
        - ``timestamp`` (date): Date posted
        - ``is_pinned`` (bool): Pinned comment

    Examples::

        # Get comments for a video
        comments = client.comments.list(video_id="dQw4w9WgXcQ", limit=100)

        # Top comments by likes
        comments = client.comments.list(
            video_id="dQw4w9WgXcQ",
            order="like_count.desc",
            limit=10,
        )

        # Search comment text
        comments = client.comments.list(text="ilike.*immigration*", limit=50)
    """

    _table = "comments_with_status"
    _model = Comment


class Transcripts(_TableEndpoint):
    """Endpoint for the ``video_transcripts`` table (~21,000 rows).

    Full video transcripts — one row per video. Contains both the raw
    diarized transcript and a cleaned version.

    Columns:
        - ``video_id`` (str, PK, FK -> videos): YouTube video ID
        - ``original_diarized_transcript`` (str): Raw transcript with
          speaker markers (e.g. ``[SPEAKER_00]: ...``)
        - ``cleaned_transcript`` (str): Cleaned transcript without markers
        - ``transcript_status`` (str): ``"ok"`` (normal) or ``"no_speech"``
          (video has no detectable speech — music, text-only, etc.)
        - ``transcript_status_at`` (timestamp): When the status was set
        - ``transcribed_at`` (timestamp): When the video was transcribed

    Examples::

        # Get transcript for a video
        transcript = client.transcripts.get(video_id="dQw4w9WgXcQ")
        print(transcript.cleaned_transcript)

        # List all video IDs that have transcripts
        transcripts = client.transcripts.list(select="video_id")

        # Filter out no-speech videos
        transcripts = client.transcripts.list(transcript_status="eq.ok")
    """

    _table = "video_transcripts"
    _model = Transcript


class SpeakerSegments(_TableEndpoint):
    """Endpoint for the ``transcription_speakers`` table (~559K rows).

    Speaker-diarized transcript segments. Each row is one contiguous
    segment spoken by a single speaker, ordered by ``segment_order``.

    Includes political content detection annotations (``pol_detect_*``
    columns) from a classifier that identifies segments containing
    political speech (policy discussion, institutional
    references, electoral content, etc.) versus general commentary.

    Columns:
        - ``transcript_speaker_id`` (int, PK): Internal ID
        - ``video_id`` (str, FK -> videos): YouTube video ID
        - ``speaker`` (str): Speaker label (e.g. "SPEAKER_00")
        - ``segment_order`` (int): Position in transcript (0-indexed)
        - ``speaker_transcript`` (str): Text of this segment
        - ``pol_detect_label`` (str): Classifies whether the segment is political speech (policy, institutions, elections, etc.) — "political_yes" or "political_no"
        - ``pol_detect_label_id`` (float): Numeric label ID
        - ``pol_detect_probability`` (float): Classifier confidence (0-1)
        - ``pol_detect_ci_lower`` (float): 95% CI lower bound
        - ``pol_detect_ci_upper`` (float): 95% CI upper bound
        - ``pol_detect_language`` (str): Detected language ("EN", "FR", ...)
        - ``pol_detect_annotated`` (bool): Manually annotated (training data for the classifier)

    Examples::

        # Get all segments for a video, in order
        segments = client.speaker_segments.list(
            video_id="dQw4w9WgXcQ",
            order="segment_order.asc",
        )

        # Only political segments with high confidence
        political = client.speaker_segments.list(
            video_id="dQw4w9WgXcQ",
            pol_detect_label="political_yes",
            pol_detect_probability="gte.0.9",
            order="segment_order.asc",
        )
    """

    _table = "transcription_speakers"
    _model = SpeakerSegment


class ProcessedComments(_TableEndpoint):
    """Endpoint for the ``comments_processed`` table (~9.8M rows).

    Sentence-level processed comments with NER (Named Entity Recognition).
    Each original comment is split into sentences; each sentence gets NER
    annotations identifying persons, locations, and organizations.

    Composite primary key: ``(comment_id, sentence_id)``.

    Columns:
        - ``comment_id`` (int, PK): References original comment
        - ``sentence_id`` (int, PK): Sentence index (0-indexed)
        - All columns from ``comments`` (denormalized)
        - ``ner_entities`` (dict): NER results with keys:
            - ``"PER"``: list of person names
            - ``"LOC"``: list of location names
            - ``"ORG"``: list of organization names

    Examples::

        # Get processed sentences for a video's comments
        processed = client.processed_comments.list(
            video_id="dQw4w9WgXcQ",
            limit=100,
        )

        # Check NER entities
        for p in processed:
            if p.ner_entities and p.ner_entities.get("PER"):
                print(f"{p.text} -> persons: {p.ner_entities['PER']}")
    """

    _table = "comments_processed"
    _model = ProcessedComment


class ProcessedSpeakerSegments(_TableEndpoint):
    """Endpoint for the ``transcription_speakers_processed`` table (~5.4M rows).

    Sentence-level processed speaker segments with NER. Each speaker segment
    is split into sentences with NER annotations.

    Composite primary key: ``(transcript_speaker_id, sentence_id)``.

    Columns:
        - ``transcript_speaker_id`` (int, PK): References original segment
        - ``sentence_id`` (int, PK): Sentence index (0-indexed)
        - ``video_id`` (str): YouTube video ID
        - ``speaker`` (str): Speaker label
        - ``segment_order`` (int): Position in transcript
        - ``speaker_transcript`` (str): Sentence text
        - ``ner_entities`` (dict): NER results (PER, LOC, ORG lists)

    Examples::

        # Get NER-annotated transcript sentences
        sentences = client.processed_speaker_segments.list(
            video_id="dQw4w9WgXcQ",
            order="segment_order.asc,sentence_id.asc",
            limit=200,
        )
    """

    _table = "transcription_speakers_processed"
    _model = ProcessedSpeakerSegment


class VideoMetadataHistory(_TableEndpoint):
    """Endpoint for the ``video_metadata_history`` table.

    Longitudinal metadata snapshots — one row per video per metadata scan.
    Use for temporal analysis of view counts, likes, subscriber growth,
    and title changes over time.

    Columns:
        - ``id`` (int, PK): Auto-incremented snapshot ID
        - ``video_id`` (str): YouTube video ID
        - ``video_views`` (int): View count at scan time
        - ``video_likes`` (int): Like count at scan time
        - ``video_comments_count`` (int): Comment count at scan time
        - ``subscribers`` (int): Channel subscriber count at scan time
        - ``video_title`` (str): Title at scan time (tracks changes)
        - ``scanned_at`` (str): Timestamp of this scan

    Examples::

        # Get view count evolution for a video
        history = client.metadata_history.list(
            video_id="dQw4w9WgXcQ",
            order="scanned_at.asc",
        )
        for h in history:
            print(f"{h.scanned_at}: {h.video_views:,} views")

        # Export all metadata snapshots from last month
        history = client.metadata_history.list(
            scanned_at="gte.2026-02-19",
            order="scanned_at.desc",
        )
    """

    _table = "video_metadata_history"
    _model = MetadataSnapshot


class ChannelMetadataHistory(_TableEndpoint):
    """Endpoint for the ``channel_metadata_history`` table.

    Longitudinal channel snapshots — one row per channel per scan.
    Use for temporal analysis of channel subscriber growth, video
    counts, and corpus coverage over time.

    Columns:
        - ``id`` (int, PK): Auto-incremented snapshot ID
        - ``channel_name`` (str): Channel display name
        - ``channel_id`` (str): YouTube channel ID
        - ``subscribers`` (int): Subscriber count at scan time
        - ``total_videos_yt`` (int): Videos on YouTube at scan time
        - ``total_videos_db`` (int): Videos in database at scan time
        - ``total_transcribed`` (int): Transcribed videos at scan time
        - ``total_comments_db`` (int): Comments in database at scan time
        - ``scanned_at`` (str): Timestamp of this scan

    Examples::

        # Track subscriber growth for a channel
        history = client.channel_history.list(
            channel_name="Psyhodelik",
            order="scanned_at.asc",
        )
    """

    _table = "channel_metadata_history"
    _model = ChannelSnapshot


class YouPol:
    """Client for the YouPol research database API.

    The YouPol database contains YouTube and TikTok political content data
    collected for academic research. It includes ~23,500 videos, ~7.5M
    comments, ~21,000 transcripts, and NLP-processed versions with NER
    annotations.

    Access is controlled by five token tiers:

    - **metadata** — video/channel metadata only
    - **analyst_1** — metadata + structural comment/transcription data
      (no text content, no author identifiers)
    - **analyst_2** — metadata + full transcriptions + search functions,
      comments remain structural only
    - **researcher** — full read access to all data, search, and exports
    - **writer** — full read + write access (internal use)

    All tiers except writer are subject to configurable rate limits
    (per day and per lifetime). When a limit is reached the API returns
    a clear error message.

    Args:
        token: JWT authentication token. Obtain one from the project
            administrators.
        base_url: API base URL. Defaults to ``https://data.you-pol.com``.

    Attributes:
        videos: Access the ``videos`` table.
        comments: Access the ``comments`` table.
        transcripts: Access the ``video_transcripts`` table.
        speaker_segments: Access the ``transcription_speakers`` table.
        processed_comments: Access the ``comments_processed`` table.
        processed_speaker_segments: Access the ``transcription_speakers_processed`` table.

    Example::

        from youpol import YouPol

        client = YouPol(token="your_jwt_token")

        # Browse videos
        videos = client.videos.list(country="FR", order="video_views.desc", limit=10)
        for v in videos:
            print(f"{v.video_title} — {v.video_views:,} views")

        # Get comments
        comments = client.comments.list(video_id=videos[0].video_id, limit=50)

        # Get transcript
        transcript = client.transcripts.get(video_id=videos[0].video_id)

        # Export to pandas DataFrame
        df = client.videos.to_dataframe(country="FR", limit=100)
    """

    def __init__(self, token: str, base_url: str = API_URL):
        self._session = _Session(token, base_url)
        self.videos = Videos(self._session)
        self.comments = Comments(self._session)
        self.transcripts = Transcripts(self._session)
        self.speaker_segments = SpeakerSegments(self._session)
        self.processed_comments = ProcessedComments(self._session)
        self.processed_speaker_segments = ProcessedSpeakerSegments(self._session)
        self.metadata_history = VideoMetadataHistory(self._session)
        self.channel_history = ChannelMetadataHistory(self._session)
