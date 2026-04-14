"""
YouPol — Python client for the YouPol research database API.

All data endpoints serve unified views covering both YouTube and TikTok.
Use ``platform="youtube"`` or ``platform="tiktok"`` to filter by platform.

Usage::

    from youpol import YouPol

    client = YouPol(token="your_jwt_token")
    videos = client.videos.list(country="FR", order="video_views.desc", limit=10)
    for v in videos:
        print(f"{v.video_title} ({v.platform}) — {v.video_views:,} views")
"""

from youpol.client import YouPol
from youpol.models import (
    Video, Comment, Transcript, SpeakerSegment,
    ProcessedComment, ProcessedSpeakerSegment,
    MetadataSnapshot, ChannelSnapshot,
    NEREntities,
    ActiveModel,
)

__version__ = "1.1.0"
__all__ = [
    "YouPol",
    "Video", "Comment", "Transcript", "SpeakerSegment",
    "ProcessedComment", "ProcessedSpeakerSegment",
    "MetadataSnapshot", "ChannelSnapshot",
    "NEREntities",
    "ActiveModel",
]
