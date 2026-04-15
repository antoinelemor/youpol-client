"""
Data models for the YouPol database.

Each model corresponds to a table in the YT.POL_processed PostgreSQL database,
exposed via the PostgREST API at https://data.you-pol.com/.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import date


# ---------------------------------------------------------------------------
# videos
# ---------------------------------------------------------------------------

@dataclass
class Video:
    """A YouTube video in the YouPol corpus.

    Table: ``videos`` (~22,800 rows)

    This is the central table. Comments, transcripts, and speaker segments
    all reference a video via ``video_id``.

    Attributes:
        video_id: YouTube video ID (primary key, e.g. ``"dQw4w9WgXcQ"``).
        channel_name: Display name of the YouTube channel.
        video_title: Title of the video.
        video_views: Total view count at time of collection.
        subscribers: Channel subscriber count at time of collection.
        video_likes: Like count at time of collection.
        video_comments_count: Comment count at time of collection.
        link: Full YouTube URL.
        tags: List of tags assigned to the video.
        duration: Video duration in seconds.
        channel_id: YouTube channel ID.
        description: Video description text.
        upload_date: Date the video was uploaded.
        suppressed: Whether the video has been suppressed/removed (default False).
        original_channel: Original channel name if the video was re-uploaded.
        ideas: Free-text annotation of main ideas/topics.
        gender: Gender of the main speaker. Values: ``"H"`` (male),
            ``"F"`` (female), ``"Mixte"`` (mixed/multiple speakers).
        playlist: Whether the video belongs to a playlist. Values:
            ``"0"`` (no) or ``"1"`` (yes).
        country: Country of the channel. Values: ``"FR"`` (France),
            ``"QC"`` (Quebec/Canada).
    """

    video_id: Optional[str] = None
    channel_name: Optional[str] = None
    video_title: Optional[str] = None
    video_views: Optional[int] = None
    subscribers: Optional[int] = None
    video_likes: Optional[int] = None
    video_comments_count: Optional[int] = None
    link: Optional[str] = None
    tags: Optional[list[str]] = None
    duration: Optional[int] = None
    channel_id: Optional[str] = None
    description: Optional[str] = None
    upload_date: Optional[str] = None
    suppressed: Optional[bool] = None
    original_channel: Optional[str] = None
    ideas: Optional[str] = None
    gender: Optional[str] = None
    playlist: Optional[str] = None
    country: Optional[str] = None
    age_restricted: Optional[bool] = None
    trashed_at: Optional[str] = None
    trash_reason: Optional[str] = None
    last_update: Optional[str] = None
    status: Optional[str] = None


# ---------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------

@dataclass
class Comment:
    """A YouTube comment on a video in the corpus.

    Table: ``comments`` (~7.3M rows)

    Each comment is linked to a video via ``video_id``.

    Attributes:
        comment_id: Auto-incremented internal ID (primary key).
        id: YouTube's native comment ID string (unique).
        parent: Parent comment ID if this is a reply, else None.
        video_id: YouTube video ID this comment belongs to (foreign key -> videos).
        channel_name: Channel name of the video (denormalized).
        video_title: Title of the video (denormalized).
        video_views: View count of the video (denormalized).
        subscribers: Subscriber count of the channel (denormalized).
        video_likes: Like count of the video (denormalized).
        link: URL to the video (denormalized).
        text: The comment text content.
        like_count: Number of likes on this comment.
        author_id: YouTube user ID of the commenter.
        author: Display name of the commenter.
        author_thumbnail: URL to the commenter's profile picture.
        author_is_uploader: True if the commenter is the video uploader.
        author_is_verified: True if the commenter has a verified badge.
        author_url: URL to the commenter's YouTube channel.
        is_favorited: True if the comment was favorited by the uploader.
        _time_text: Relative time text (e.g. "2 months ago").
        timestamp: Date the comment was posted.
        is_pinned: True if the comment is pinned.
    """

    comment_id: Optional[int] = None
    id: Optional[str] = None
    parent: Optional[str] = None
    video_id: Optional[str] = None
    channel_name: Optional[str] = None
    video_title: Optional[str] = None
    video_views: Optional[int] = None
    subscribers: Optional[int] = None
    video_likes: Optional[int] = None
    link: Optional[str] = None
    text: Optional[str] = None
    like_count: Optional[int] = None
    author_id: Optional[str] = None
    author: Optional[str] = None
    author_thumbnail: Optional[str] = None
    author_is_uploader: Optional[bool] = None
    author_is_verified: Optional[bool] = None
    author_url: Optional[str] = None
    is_favorited: Optional[bool] = None
    _time_text: Optional[str] = None
    timestamp: Optional[str] = None
    is_pinned: Optional[bool] = None
    suppressed: Optional[bool] = None
    suppressed_at: Optional[str] = None
    status: Optional[str] = None


# ---------------------------------------------------------------------------
# video_transcripts
# ---------------------------------------------------------------------------

@dataclass
class Transcript:
    """Full transcript of a video.

    Table: ``video_transcripts`` (~21,000 rows)

    One row per video. Contains both the raw diarized transcript and a
    cleaned version.

    Attributes:
        video_id: YouTube video ID (primary key, foreign key -> videos).
        original_diarized_transcript: Raw transcript with speaker diarization
            markers (e.g. ``[SPEAKER_00]: ...``).
        cleaned_transcript: Cleaned version of the transcript with
            diarization markers removed.
        transcript_status: Status flag for the transcript. Values:
            ``"ok"`` (default, normal transcript),
            ``"no_speech"`` (video has no detectable speech — music,
            text-only, or silent video).
        transcript_status_at: Timestamp when the status was last set.
        transcribed_at: Timestamp when the video was transcribed.
    """

    video_id: Optional[str] = None
    original_diarized_transcript: Optional[str] = None
    cleaned_transcript: Optional[str] = None
    transcript_status: Optional[str] = None
    transcript_status_at: Optional[str] = None
    transcribed_at: Optional[str] = None


# ---------------------------------------------------------------------------
# transcription_speakers
# ---------------------------------------------------------------------------

@dataclass
class SpeakerSegment:
    """A single speaker segment from a diarized transcript.

    Table: ``transcription_speakers`` (~559K rows)

    Each row is one contiguous segment spoken by a single speaker in a video.
    Segments are ordered by ``segment_order`` within each video.

    Attributes:
        transcript_speaker_id: Auto-incremented internal ID (primary key).
        video_id: YouTube video ID (foreign key -> videos).
        speaker: Speaker label (e.g. ``"SPEAKER_00"``, ``"SPEAKER_01"``).
        segment_order: Position of this segment in the transcript (0-indexed).
        speaker_transcript: Text spoken in this segment.
        pol_detect_label: Political content classification. Indicates whether
            the segment is political speech (policy discussion,
            institutional references, electoral content, etc.) as opposed to
            general commentary. Values: ``"political_yes"``, ``"political_no"``.
        pol_detect_label_id: Numeric ID of the classification label.
        pol_detect_probability: Classifier confidence score (0-1).
        pol_detect_ci_lower: Lower bound of the 95% confidence interval.
        pol_detect_ci_upper: Upper bound of the 95% confidence interval.
        pol_detect_language: Language detected for classification.
            Values: ``"EN"``, ``"FR"``, etc.
        pol_detect_annotated: Whether this segment was manually annotated
            (used as training data for the classifier).
    """

    transcript_speaker_id: Optional[int] = None
    video_id: Optional[str] = None
    speaker: Optional[str] = None
    segment_order: Optional[int] = None
    speaker_transcript: Optional[str] = None
    pol_detect_label: Optional[str] = None
    pol_detect_label_id: Optional[float] = None
    pol_detect_probability: Optional[float] = None
    pol_detect_ci_lower: Optional[float] = None
    pol_detect_ci_upper: Optional[float] = None
    pol_detect_language: Optional[str] = None
    pol_detect_annotated: Optional[bool] = None


# ---------------------------------------------------------------------------
# comments_processed
# ---------------------------------------------------------------------------

@dataclass
class NEREntities:
    """Named entities extracted from a text segment.

    Attributes:
        PER: List of person names found.
        LOC: List of location names found.
        ORG: List of organization names found.
    """

    PER: list[str] = field(default_factory=list)
    LOC: list[str] = field(default_factory=list)
    ORG: list[str] = field(default_factory=list)


@dataclass
class ProcessedComment:
    """A sentence-level processed version of a comment with NER annotations.

    Table: ``comments_processed`` (~9.8M rows)

    Each original comment is split into individual sentences. Each sentence
    gets its own row with NER (Named Entity Recognition) results.
    The composite primary key is ``(comment_id, sentence_id)``.

    Attributes:
        comment_id: References the original comment (part of composite PK).
        sentence_id: Sentence index within the comment (part of composite PK, 0-indexed).
        id: YouTube's native comment ID string.
        parent: Parent comment ID if this is a reply.
        video_id: YouTube video ID.
        channel_name: Channel name (denormalized).
        video_title: Video title (denormalized).
        video_views: View count (denormalized).
        subscribers: Subscriber count (denormalized).
        video_likes: Like count (denormalized).
        link: Video URL (denormalized).
        text: The individual sentence text.
        like_count: Like count on the original comment.
        author_id: YouTube user ID of the commenter.
        author: Display name of the commenter.
        author_thumbnail: Commenter profile picture URL.
        author_is_uploader: True if commenter is the video uploader.
        author_is_verified: True if commenter has a verified badge.
        author_url: Commenter's YouTube channel URL.
        is_favorited: True if favorited by the uploader.
        _time_text: Relative time text.
        timestamp: Date the comment was posted.
        is_pinned: True if the comment is pinned.
        ner_entities: Named entities found in this sentence.
            A dict with keys ``"PER"`` (persons), ``"LOC"`` (locations),
            ``"ORG"`` (organizations), each mapping to a list of strings.
            Example: ``{"PER": ["Macron"], "LOC": ["Paris"], "ORG": ["LFI"]}``
    """

    comment_id: Optional[int] = None
    sentence_id: Optional[int] = None
    id: Optional[str] = None
    parent: Optional[str] = None
    video_id: Optional[str] = None
    channel_name: Optional[str] = None
    video_title: Optional[str] = None
    video_views: Optional[int] = None
    subscribers: Optional[int] = None
    video_likes: Optional[int] = None
    link: Optional[str] = None
    text: Optional[str] = None
    like_count: Optional[int] = None
    author_id: Optional[str] = None
    author: Optional[str] = None
    author_thumbnail: Optional[str] = None
    author_is_uploader: Optional[bool] = None
    author_is_verified: Optional[bool] = None
    author_url: Optional[str] = None
    is_favorited: Optional[bool] = None
    _time_text: Optional[str] = None
    timestamp: Optional[str] = None
    is_pinned: Optional[bool] = None
    ner_entities: Optional[dict] = None


# ---------------------------------------------------------------------------
# transcription_speakers_processed
# ---------------------------------------------------------------------------

@dataclass
class ProcessedSpeakerSegment:
    """A sentence-level processed version of a speaker segment with NER.

    Table: ``transcription_speakers_processed`` (~5.4M rows)

    Each speaker segment is split into individual sentences. Each sentence
    gets its own row with NER results.
    The composite primary key is ``(transcript_speaker_id, sentence_id)``.

    Attributes:
        transcript_speaker_id: References the original speaker segment
            (part of composite PK).
        sentence_id: Sentence index within the segment (part of composite PK, 0-indexed).
        video_id: YouTube video ID.
        speaker: Speaker label (e.g. ``"SPEAKER_00"``).
        segment_order: Position of the parent segment in the transcript.
        speaker_transcript: The individual sentence text.
        ner_entities: Named entities found in this sentence.
            A dict with keys ``"PER"``, ``"LOC"``, ``"ORG"``,
            each mapping to a list of strings.
    """

    transcript_speaker_id: Optional[int] = None
    sentence_id: Optional[int] = None
    video_id: Optional[str] = None
    speaker: Optional[str] = None
    segment_order: Optional[int] = None
    speaker_transcript: Optional[str] = None
    ner_entities: Optional[dict] = None
    pol_detect_label: Optional[str] = None
    pol_detect_probability: Optional[float] = None
    # Extra model columns are attached dynamically — see ClassifierResult.
    extras: dict = field(default_factory=dict)


@dataclass
class ActiveModel:
    """A classifier currently active in the YouPol registry.

    Use ``client.models.list()`` to fetch this metadata. It tells you which
    tables carry this model's output columns (for SELECT/WHERE construction),
    its label vocabulary, and whether it is single- or multi-label.

    Attributes:
        model_id:               Registry primary key.
        model_key:              Stable unique identifier.
        storage_key:            Column prefix. Column names follow the
                                convention in ``column_names``.
        display_name:           Human-readable name.
        description:            Free-form description set by the admin.
        task_type:              ``"single_label_classification"`` — five scalar
                                columns: ``{sk}_label``, ``{sk}_label_id``,
                                ``{sk}_probability``, ``{sk}_language``,
                                ``{sk}_annotated``.
                                OR ``"multi_label_classification"`` — one
                                JSONB column ``{sk}_scores`` holding
                                ``{scores: {label: prob}, active: [labels
                                above threshold], threshold, language,
                                annotated}``.
        num_labels:             Number of label classes.
        label_map:              ``{"0": "label_a", "1": "label_b", ...}``.
        positive_label:         For single-label binary: which label counts
                                as positive. None for multi-class or
                                multi-label.
        multi_label_threshold:  Threshold used to materialize the ``active``
                                array in the JSONB (None for single-label).
        languages:              List of languages the model was trained on
                                (ISO-2 codes).
        primary_language:       Main training language.
        base_model:             HuggingFace base model id.
        target_text_type:       ``"transcripts"`` | ``"comments"`` | ``"both"``.
        api_tables:             Tables where this model's columns are exposed
                                via the API. Use to decide which processed
                                endpoints to query.
        worker_tables:          Tables where this model annotates incoming
                                data in real time.
        column_names:           The exact column names on each table,
                                ready to use in ``select=`` lists.
    """

    model_id: Optional[int] = None
    model_key: Optional[str] = None
    storage_key: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    task_type: Optional[str] = None
    num_labels: Optional[int] = None
    label_map: Optional[dict] = None
    positive_label: Optional[str] = None
    multi_label_threshold: Optional[float] = None
    languages: Optional[list] = None
    primary_language: Optional[str] = None
    base_model: Optional[str] = None
    target_text_type: Optional[str] = None
    api_tables: list = field(default_factory=list)
    worker_tables: list = field(default_factory=list)
    column_names: list = field(default_factory=list)
    activated_at: Optional[str] = None
    # Admin-configured display config. Shape:
    #   {"labels": {"political_yes": "Political", "political_no": "Non-political"}}
    # Used by the explorer UI + external consumers that want pretty label names.
    display_config: Optional[dict] = None
    # UI metadata (registry v4) — used by data.you-pol.com explorer to render
    # consistent filter widgets / badges per model. Featured + high-priority
    # models appear first in filter panels (the political slider stays at top).
    priority: int = 0
    featured: bool = False
    ui_color: Optional[str] = None        # hex color used for badges/sliders
    ui_short_name: Optional[str] = None   # compact label (≤ ~16 chars)
    ui_positive_label_display: Optional[str] = None  # pretty name for positive_label

    # Convenience helpers (not persisted; computed from fields)
    @property
    def is_multi_label(self) -> bool:
        """True if this is a multi-label classifier (output is JSONB)."""
        return self.task_type == "multi_label_classification"

    def label_list(self) -> list:
        """Return labels ordered by label_id (``["a", "b", "c"]``)."""
        lm = self.label_map or {}
        return [lm[k] for k in sorted(lm.keys(), key=lambda x: int(x))]

    def display_label(self, raw_label: str) -> str:
        """Return the admin-configured pretty name for a raw label, falling
        back to the raw value if no override was set.

        Example::

            m = client.models.get(model_key="pol_detect")
            pretty = m.display_label("political_yes")  # "Political"
        """
        if not raw_label:
            return raw_label
        labels = (self.display_config or {}).get("labels") or {}
        return labels.get(raw_label, raw_label)

    def scores_path(self, label: str) -> str:
        """Return the PostgREST JSON-path fragment to filter on a specific
        label's score for multi-label models.

        Example (threshold on sports score):

            client.processed_comments.list(**{
                f"{m.storage_key}_scores->scores->>{label}": "gte.0.3"
            })
        """
        return f"{self.storage_key}_scores->scores->>{label}"


# ---------------------------------------------------------------------------
# video_metadata_history
# ---------------------------------------------------------------------------

@dataclass
class MetadataSnapshot:
    """A point-in-time snapshot of video metadata.

    Table: ``video_metadata_history``

    One row per video per metadata scan. Use for longitudinal analysis
    of view counts, likes, subscriber growth, and title changes over time.

    Attributes:
        id: Auto-incremented snapshot ID.
        video_id: YouTube video ID.
        video_views: View count at scan time.
        video_likes: Like count at scan time.
        video_comments_count: Comment count at scan time.
        subscribers: Channel subscriber count at scan time.
        video_title: Video title at scan time (tracks title changes).
        scanned_at: Timestamp of this metadata scan.
    """

    id: Optional[int] = None
    video_id: Optional[str] = None
    video_views: Optional[int] = None
    video_likes: Optional[int] = None
    video_comments_count: Optional[int] = None
    subscribers: Optional[int] = None
    video_title: Optional[str] = None
    scanned_at: Optional[str] = None


# ---------------------------------------------------------------------------
# channel_metadata_history
# ---------------------------------------------------------------------------

@dataclass
class ChannelSnapshot:
    """A point-in-time snapshot of channel metadata.

    Table: ``channel_metadata_history``

    One row per channel per scan. Use for longitudinal analysis
    of channel growth (subscribers, video counts, etc.).

    Attributes:
        id: Auto-incremented snapshot ID.
        channel_name: Channel display name.
        channel_id: YouTube channel ID.
        subscribers: Subscriber count at scan time.
        total_videos_yt: Number of videos on YouTube at scan time.
        total_videos_db: Number of videos in database at scan time.
        total_transcribed: Number of transcribed videos at scan time.
        total_comments_db: Number of comments in database at scan time.
        scanned_at: Timestamp of this scan.
    """

    id: Optional[int] = None
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None
    subscribers: Optional[int] = None
    total_videos_yt: Optional[int] = None
    total_videos_db: Optional[int] = None
    total_transcribed: Optional[int] = None
    total_comments_db: Optional[int] = None
    scanned_at: Optional[str] = None
