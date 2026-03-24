"""
YouPol client — Quick start examples.

Replace YOUR_TOKEN with your JWT token.
"""

from youpol import YouPol

TOKEN = "YOUR_TOKEN"
client = YouPol(token=TOKEN)

# ── 1. Browse videos ─────────────────────────────────────────────────────

# Get the 10 most viewed French videos
videos = client.videos.list(
    country="FR",
    order="video_views.desc",
    limit=10,
)
for v in videos:
    print(f"[{v.video_id}] {v.video_title} — {v.video_views:,} views")

# Search videos by title (case-insensitive)
results = client.videos.list(video_title="ilike.*macron*", limit=5)

# Get a specific video
video = client.videos.get(video_id=videos[0].video_id)
print(f"\nVideo: {video.video_title}")
print(f"  Channel: {video.channel_name}")
print(f"  Duration: {video.duration}s")
print(f"  Uploaded: {video.upload_date}")

# ── 2. Comments ──────────────────────────────────────────────────────────

# Get top comments for a video
comments = client.comments.list(
    video_id=videos[0].video_id,
    order="like_count.desc",
    limit=10,
)
print(f"\nTop comments on '{videos[0].video_title}':")
for c in comments:
    print(f"  [{c.like_count} likes] {c.author}: {c.text[:80]}...")

# ── 3. Transcripts ───────────────────────────────────────────────────────

# Get full transcript
transcript = client.transcripts.get(video_id=videos[0].video_id)
if transcript.cleaned_transcript:
    print(f"\nTranscript preview: {transcript.cleaned_transcript[:200]}...")

# ── 4. Speaker segments ─────────────────────────────────────────────────

# Get speaker-diarized segments
segments = client.speaker_segments.list(
    video_id=videos[0].video_id,
    order="segment_order.asc",
    limit=20,
)
for s in segments:
    print(f"  [{s.speaker}] {s.speaker_transcript[:80]}...")

# Only political segments
political = client.speaker_segments.list(
    video_id=videos[0].video_id,
    pol_detect_label="political_yes",
    pol_detect_probability="gte.0.9",
    order="segment_order.asc",
)
print(f"\nPolitical segments (high confidence): {len(political)}")

# ── 5. NER-processed data ───────────────────────────────────────────────

# Get processed comments with named entities
processed = client.processed_comments.list(
    video_id=videos[0].video_id,
    limit=100,
)
for p in processed:
    entities = p.ner_entities or {}
    persons = entities.get("PER", [])
    if persons:
        print(f"  Persons mentioned: {persons} in: {p.text[:60]}...")

# ── 6. Filtering examples ───────────────────────────────────────────────

# Videos with > 100k views from Quebec
popular_qc = client.videos.list(
    country="QC",
    video_views="gte.100000",
    order="video_views.desc",
    limit=10,
)

# Female-led channels
female = client.videos.list(gender="F", limit=10)

# Videos from multiple countries
multi = client.videos.list(country=["FR", "QC"], limit=10)

# Only select certain columns (faster)
ids_only = client.videos.list(
    select=["video_id", "video_title"],
    limit=10,
)
