"""
Data models for the YouPol database.

Each model corresponds to a table or view in the YT.POL_processed PostgreSQL
database, exposed via the PostgREST API at https://data.you-pol.com/.

All views are unified across YouTube and TikTok data. Use the ``platform``
field to distinguish between platforms (``"youtube"`` or ``"tiktok"``).
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import date


# ---------------------------------------------------------------------------
# videos (unified view: videos_with_update)
# ---------------------------------------------------------------------------

@dataclass
class Video:
    """A video in the YouPol corpus (YouTube or TikTok).

    View: ``videos_with_update`` (~23,500 rows)

    This is the central table. Comments, transcripts, and speaker segments
    all reference a video via ``video_id``.

    Attributes:
        video_id: Platform video ID (primary key).
        channel_name: Display name of the channel.
        video_title: Title of the video.
        video_views: Total view count at time of collection.
        subscribers: Channel subscriber/follower count at time of collection.
        video_likes: Like count at time of collection.
        video_comments_count: Comment count at time of collection.
        link: Full URL to the video.
        tags: List of tags/hashtags assigned to the video.
        duration: Video duration in seconds.
        channel_id: Platform channel ID.
        description: Video description text.
        upload_date: Date the video was uploaded.
        suppressed: Whether the video has been suppressed/removed.
        suppressed_at: Timestamp when the video was flagged as suppressed.
        suppression_reason: Reason for suppression (deleted, deactivated,
            terminated, members_only, unavailable).
        original_channel: Original channel name if the video was re-uploaded.
        ideas: Annotated political orientation. Values: ``"Far_right"``,
            ``"Left"``, ``"Masc"`` (Manosphere), ``"Comp"`` (Conspiracy).
        gender: Gender of the main speaker. Values: ``"H"`` (male),
            ``"F"`` (female), ``"Mixte"`` (mixed/multiple speakers).
        playlist: Whether the video belongs to a playlist.
        country: Country of the channel. Values: ``"FR"`` (France),
            ``"QC"`` (Quebec/Canada).
        age_restricted: Whether the video is age-restricted.
        trashed_at: Timestamp when the video was trashed by admin (YouTube only).
        trash_reason: Reason for trashing (YouTube only).
        created_at: Timestamp when the video was added to the database.
        updated_at: Timestamp of last update.
        last_update: Timestamp of the last metadata scan.
        status: Content status. Values: ``"active"``, ``"suppressed"``,
            ``"trashed"``.
        platform: Source platform. Values: ``"youtube"``, ``"tiktok"``.
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
    suppressed_at: Optional[str] = None
    suppression_reason: Optional[str] = None
    original_channel: Optional[str] = None
    ideas: Optional[str] = None
    gender: Optional[str] = None
    playlist: Optional[str] = None
    country: Optional[str] = None
    age_restricted: Optional[bool] = None
    trashed_at: Optional[str] = None
    trash_reason: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_update: Optional[str] = None
    status: Optional[str] = None
    platform: Optional[str] = None


# ---------------------------------------------------------------------------
# comments (unified view: comments_with_status)
# ---------------------------------------------------------------------------

@dataclass
class Comment:
    """A comment on a video in the corpus (YouTube or TikTok).

    View: ``comments_with_status`` (~7.5M rows)

    Each comment is linked to a video via ``video_id``.

    Attributes:
        comment_id: Auto-incremented internal ID (primary key).
        id: Platform's native comment ID string.
        parent: Parent comment ID if this is a reply, else None.
        video_id: Video ID this comment belongs to.
        channel_name: Channel name of the video (denormalized).
        video_title: Title of the video (denormalized).
        video_views: View count of the video (denormalized).
        subscribers: Subscriber count of the channel (denormalized).
        video_likes: Like count of the video (denormalized).
        link: URL to the video (denormalized).
        text: The comment text content.
        like_count: Number of likes on this comment.
        author_id: User ID of the commenter.
        author: Display name of the commenter.
        author_thumbnail: URL to the commenter's profile picture.
        author_is_uploader: True if the commenter is the video uploader.
        author_is_verified: True if the commenter has a verified badge.
        author_url: URL to the commenter's channel.
        is_favorited: True if the comment was favorited by the uploader.
        _time_text: Relative time text (e.g. "2 months ago").
        timestamp: Date the comment was posted.
        is_pinned: True if the comment is pinned.
        suppressed: Whether the comment has been deleted.
        suppressed_at: Timestamp when the comment was flagged as deleted.
        status: Content status. Values: ``"active"``, ``"suppressed"``.
        last_update: Timestamp of suppression detection.
        platform: Source platform. Values: ``"youtube"``, ``"tiktok"``.
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
    last_update: Optional[str] = None
    platform: Optional[str] = None


# ---------------------------------------------------------------------------
# video_transcripts (unified view)
# ---------------------------------------------------------------------------

@dataclass
class Transcript:
    """Full transcript of a video (YouTube or TikTok).

    View: ``video_transcripts`` (~21,000 rows)

    One row per video. Contains both the raw diarized transcript and a
    cleaned version.

    Attributes:
        video_id: Video ID (primary key).
        original_diarized_transcript: Raw transcript with speaker diarization
            markers (e.g. ``[SPEAKER_00]: ...``).
        cleaned_transcript: Cleaned version without diarization markers.
        transcribed_at: Timestamp when the video was transcribed.
        transcript_status: Status flag. Values:
            ``"ok"`` (normal transcript),
            ``"no_speech"`` (no detectable speech).
        transcript_status_at: Timestamp when the status was last set.
        status: Content status (derived from parent video). Values:
            ``"active"``, ``"suppressed"``.
        platform: Source platform. Values: ``"youtube"``, ``"tiktok"``.
    """

    video_id: Optional[str] = None
    original_diarized_transcript: Optional[str] = None
    cleaned_transcript: Optional[str] = None
    transcribed_at: Optional[str] = None
    transcript_status: Optional[str] = None
    transcript_status_at: Optional[str] = None
    status: Optional[str] = None
    platform: Optional[str] = None


# ---------------------------------------------------------------------------
# speakers_with_pol (unified view)
# ---------------------------------------------------------------------------

@dataclass
class SpeakerSegment:
    """A single speaker segment from a diarized transcript (YouTube or TikTok).

    View: ``speakers_with_pol`` (~612K rows)

    Each row is one contiguous segment spoken by a single speaker in a video.
    Segments are ordered by ``segment_order`` within each video. Includes
    political content detection and aggregated sentence-level statistics.

    Attributes:
        transcript_speaker_id: Auto-incremented internal ID (primary key).
        video_id: Video ID.
        speaker: Speaker label (e.g. ``"SPEAKER_00"``, ``"SPEAKER_01"``).
        segment_order: Position of this segment in the transcript (0-indexed).
        speaker_transcript: Text spoken in this segment.
        pol_detect_label: Political content classification. Values:
            ``"political_yes"``, ``"political_no"``.
        pol_detect_label_id: Numeric ID of the classification label.
        pol_detect_probability: Classifier confidence score (0-1).
        pol_detect_ci_lower: Lower bound of the 95% confidence interval.
        pol_detect_ci_upper: Upper bound of the 95% confidence interval.
        pol_detect_language: Language detected for classification.
        pol_detect_annotated: Whether this segment was manually annotated.
        sentences_total: Total number of sentences in this segment.
        sentences_political: Number of sentences classified as political.
        pct_political: Percentage of political sentences (0-100).
        avg_confidence: Average classifier confidence for political sentences.
        status: Content status (derived from parent video). Values:
            ``"active"``, ``"suppressed"``.
        platform: Source platform. Values: ``"youtube"``, ``"tiktok"``.
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
    sentences_total: Optional[int] = None
    sentences_political: Optional[int] = None
    pct_political: Optional[float] = None
    avg_confidence: Optional[float] = None
    status: Optional[str] = None
    platform: Optional[str] = None


# ---------------------------------------------------------------------------
# NER entities
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


# ---------------------------------------------------------------------------
# comments_processed
# ---------------------------------------------------------------------------

@dataclass
class ProcessedComment:
    """A sentence-level processed version of a comment with NER annotations.

    Table: ``comments_processed`` (YouTube + TikTok, ~9.8M rows)

    Each original comment is split into individual sentences. Each sentence
    gets its own row with NER (Named Entity Recognition) results.
    The composite primary key is ``(comment_id, sentence_id)``.

    Attributes:
        comment_id: References the original comment (part of composite PK).
        sentence_id: Sentence index within the comment (part of composite PK, 0-indexed).
        id: Platform's native comment ID string.
        parent: Parent comment ID if this is a reply.
        video_id: Video ID.
        channel_name: Channel name (denormalized).
        video_title: Video title (denormalized).
        video_views: View count (denormalized).
        subscribers: Subscriber count (denormalized).
        video_likes: Like count (denormalized).
        link: Video URL (denormalized).
        text: The individual sentence text.
        like_count: Like count on the original comment.
        author_id: User ID of the commenter.
        author: Display name of the commenter.
        author_thumbnail: Commenter profile picture URL.
        author_is_uploader: True if commenter is the video uploader.
        author_is_verified: True if commenter has a verified badge.
        author_url: Commenter's channel URL.
        is_favorited: True if favorited by the uploader.
        _time_text: Relative time text.
        timestamp: Date the comment was posted.
        is_pinned: True if the comment is pinned.
        ner_entities: Named entities found in this sentence.
            A dict with keys ``"PER"`` (persons), ``"LOC"`` (locations),
            ``"ORG"`` (organizations), each mapping to a list of strings.
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

    Table: ``transcription_speakers_processed`` (YouTube + TikTok, ~5.4M rows)

    Each speaker segment is split into individual sentences. Each sentence
    gets its own row with NER results and political speech classification.
    The composite primary key is ``(transcript_speaker_id, sentence_id)``.

    Attributes:
        transcript_speaker_id: References the original speaker segment
            (part of composite PK).
        sentence_id: Sentence index within the segment (part of composite PK, 0-indexed).
        video_id: Video ID.
        speaker: Speaker label (e.g. ``"SPEAKER_00"``).
        segment_order: Position of the parent segment in the transcript.
        speaker_transcript: The individual sentence text.
        ner_entities: Named entities found in this sentence.
            A dict with keys ``"PER"``, ``"LOC"``, ``"ORG"``.
        pol_detect_label: Political speech classification for this sentence.
            Values: ``"political_yes"``, ``"political_no"``.
        pol_detect_probability: Classifier confidence (0-1).
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


# ---------------------------------------------------------------------------
# video_metadata_history (unified view)
# ---------------------------------------------------------------------------

@dataclass
class MetadataSnapshot:
    """A point-in-time snapshot of video metadata.

    View: ``video_metadata_history`` (YouTube + TikTok)

    One row per video per metadata scan. Use for longitudinal analysis
    of view counts, likes, subscriber growth, and title changes over time.

    Attributes:
        id: Auto-incremented snapshot ID.
        video_id: Video ID.
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
# channel_metadata_history (unified view)
# ---------------------------------------------------------------------------

@dataclass
class ChannelSnapshot:
    """A point-in-time snapshot of channel metadata.

    View: ``channel_metadata_history`` (YouTube + TikTok)

    One row per channel per scan. Use for longitudinal analysis
    of channel growth (subscribers, video counts, etc.).

    Attributes:
        id: Auto-incremented snapshot ID.
        channel_name: Channel display name.
        channel_id: Platform channel ID.
        subscribers: Subscriber count at scan time.
        total_videos_yt: Number of videos on the platform at scan time.
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


# ---------------------------------------------------------------------------
# Search result models (returned by RPC search functions)
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """Base class for search results with ranking and highlighting."""
    headline: Optional[str] = None
    rank: Optional[float] = None
    total_count: Optional[int] = None
