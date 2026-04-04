"""
YouPol client — Pandas analysis examples.

Requires: pip install youpol[pandas]

Note: accessing comments, transcriptions, or export functions
requires an appropriate access tier (analyst_2 or researcher).
See the README for details.
"""

from youpol import YouPol
import youpol.pandas_ext  # activates .to_dataframe()

TOKEN = "YOUR_TOKEN"
client = YouPol(token=TOKEN)

# ── Load videos into a DataFrame ─────────────────────────────────────────

df = client.videos.to_dataframe(
    select=["video_id", "channel_name", "video_title", "video_views",
            "video_likes", "upload_date", "gender", "country", "duration"],
    country="FR",
    limit=500,
)

print(f"Loaded {len(df)} French videos")
print(df.describe())

# ── Basic analysis ───────────────────────────────────────────────────────

# Views by gender
print("\nMean views by speaker gender:")
print(df.groupby("gender")["video_views"].mean())

# Top channels by total views
print("\nTop 10 channels by total views:")
print(
    df.groupby("channel_name")["video_views"]
    .sum()
    .sort_values(ascending=False)
    .head(10)
)

# ── Comments DataFrame ───────────────────────────────────────────────────

video_id = df.iloc[0]["video_id"]
comments_df = client.comments.to_dataframe(
    video_id=video_id,
    select=["comment_id", "author", "text", "like_count", "timestamp"],
    order="like_count.desc",
    limit=200,
)

print(f"\nLoaded {len(comments_df)} comments for video {video_id}")
print(f"Mean likes per comment: {comments_df['like_count'].mean():.1f}")

# ── NER analysis ─────────────────────────────────────────────────────────

ner_df = client.processed_comments.to_dataframe(
    video_id=video_id,
    select=["comment_id", "sentence_id", "text", "ner_entities"],
    limit=500,
)

# Extract all mentioned persons
import json

all_persons = []
for _, row in ner_df.iterrows():
    entities = row["ner_entities"]
    if isinstance(entities, str):
        entities = json.loads(entities)
    if entities and entities.get("PER"):
        all_persons.extend(entities["PER"])

if all_persons:
    from collections import Counter
    print(f"\nMost mentioned persons in comments:")
    for person, count in Counter(all_persons).most_common(10):
        print(f"  {person}: {count}")
