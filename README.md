# YouPol Python Client

Python client for the [YouPol](https://you-pol.com/) research database API.

The YouPol database contains YouTube and TikTok political content data collected for academic research. All endpoints serve **unified views** covering both platforms — use `platform="youtube"` or `platform="tiktok"` to filter.

## Database Overview

| Endpoint | View/Table | Rows | Description |
|----------|------------|------|-------------|
| `videos` | `videos_with_update` | ~23,500 | Video metadata with status, platform, last update |
| `comments` | `comments_with_status` | ~7.5M | Comments with suppression status |
| `transcripts` | `video_transcripts` | ~21,000 | Full video transcripts (raw diarized + cleaned) |
| `speaker_segments` | `speakers_with_pol` | ~612K | Speaker-diarized segments with political speech detection |
| `processed_comments` | `comments_processed` | ~9.8M | Sentence-level comments with NER |
| `processed_speaker_segments` | `transcription_speakers_processed` | ~5.4M | Sentence-level segments with NER + political classification |
| `metadata_history` | `video_metadata_history` | growing | Longitudinal video metadata snapshots |
| `channel_history` | `channel_metadata_history` | growing | Longitudinal channel snapshots |
| `analytics_by_month` | `analytics_by_month` | — | Monthly political speech aggregation |
| `analytics_by_channel` | `analytics_by_channel` | — | Per-channel political speech aggregation |
| `analytics_by_country` | `analytics_by_country` | — | Per-country political speech aggregation |
| `analytics_by_gender` | `analytics_by_gender` | — | Per-gender political speech aggregation |
| `models` | `active_models` | 1+ | Registry of every active classifier (single or multi-label) — discover columns, labels, deployment tables |

## Installation

```bash
pip install git+https://github.com/antoinelemor/youpol-client.git
```

With pandas support:

```bash
pip install "youpol[pandas] @ git+https://github.com/antoinelemor/youpol-client.git"
```

## Quick Start

```python
from youpol import YouPol

client = YouPol(token="your_jwt_token")

# Get the 10 most viewed French videos
videos = client.videos.list(country="FR", order="video_views.desc", limit=10)
for v in videos:
    print(f"{v.video_title} ({v.platform}) — {v.video_views:,} views — {v.status}")

# Get comments for a video
comments = client.comments.list(video_id=videos[0].video_id, limit=100)

# Get the transcript
transcript = client.transcripts.get(video_id=videos[0].video_id)
print(transcript.cleaned_transcript[:500])

# Search in comments — works in three modes:
#   - "fts"      (default) French full-text search, exact words
#   - "semantic" Qwen3 embedding similarity (1024-dim halfvec)
#   - "hybrid"   reciprocal rank fusion of FTS + semantic
hits = client.search.comments("immigration", mode="semantic", page_size=10)
for h in hits:
    print(f"  rank={h.rank:.3f}  {h['video_title']} :: {h['text'][:80]}")
```

## Authentication

You need a JWT token to access the API. Contact the project administrators to obtain one.

### Access Tiers

Tokens are issued with one of five access tiers, each controlling which data you can query and how much you can use the API:

| Tier | Label | Data Access | Search & Export |
|------|-------|-------------|-----------------|
| `metadata` | **Metadata** | Video & channel metadata only (title, views, dates, tags). No comments, transcriptions, or speaker data. | None |
| `analyst_1` | **Analyst Tier 1** | Metadata + structural comment/transcription data (counts, timestamps, languages) — **without** comment text, author identifiers, or transcript content. | None |
| `analyst_2` | **Analyst Tier 2** | Metadata + full transcription content (diarized transcripts, speaker segments, NER entities). Comments remain structural only (no text, no authors). | Transcription search & analysis only. No comment search, no bulk exports. |
| `researcher` | **Researcher** | Full read access to all tables, including comments with text and author data. | All search, analysis, and export functions. |
| `writer` | **Writer** | Full read + write access. Reserved for internal use. | All functions, no rate limits. |

### Rate Limits

All tiers except `writer` are subject to configurable rate limits, both **per day** (resets at midnight UTC) and **per lifetime** of the token:

| Limit | Description |
|-------|-------------|
| **Requests / day** | Total API calls allowed per day |
| **Requests total** | Lifetime cap on API calls |
| **Searches / day** | Full-text search & analysis queries per day |
| **Searches total** | Lifetime cap on search queries |
| **Transcriptions / day** | Requests to transcription/speaker endpoints per day |
| **Transcriptions total** | Lifetime cap on transcription data access |
| **Exports / day** | Bulk export function calls per day |
| **Exports total** | Lifetime cap on bulk exports |

When a limit is reached, the API returns an HTTP error with a clear English message explaining which limit was hit and whether it resets daily or requires an upgrade. Example:

```
Daily search limit reached (50/50). Resets at midnight UTC.
```

```
Lifetime request limit reached (5000/5000). Contact the administrator to upgrade your access.
```

Your specific limits depend on your token tier and may be customized by the administrator. Contact the project team to request an upgrade if needed.

### Tier-Specific Endpoint Access

Depending on your tier, some endpoints will return an error. Here is what each tier can access:

| Endpoint | `metadata` | `analyst_1` | `analyst_2` | `researcher` | `writer` |
|----------|-----------|------------|------------|-------------|---------|
| `videos` | Full | Full | Full | Full | Full |
| `metadata_history` | Full | Full | Full | Full | Full |
| `channel_history` | Full | Full | Full | Full | Full |
| `comments` | — | Structure only | Structure only | Full | Full |
| `transcripts` | — | Status only | Full | Full | Full |
| `speaker_segments` | — | Structure only | Full | Full | Full |
| `processed_comments` | — | Structure only | — | Full | Full |
| `processed_speaker_segments` | — | Structure only | Full | Full | Full |
| `search_transcripts()` | — | — | Yes | Yes | Yes |
| `search_speakers()` | — | — | Yes | Yes | Yes |
| `search_comments()` | — | — | — | Yes | Yes |
| `export_*()` | — | — | — | Yes | Yes |

**Structure only** means you receive metadata columns (IDs, counts, timestamps, languages) but not the actual text content or author identifiers. This is enforced at the database level via filtered views.

## API Reference

### Table Endpoints

```python
# Unified endpoints (YouTube + TikTok)
client.videos                       # videos with metadata, status, platform
client.comments                     # comments with suppression status
client.transcripts                  # full video transcripts
client.speaker_segments             # speaker-diarized segments with political detection
client.processed_comments           # sentence-level comments with NER
client.processed_speaker_segments   # sentence-level segments with NER + pol_detect
client.metadata_history             # longitudinal video metadata snapshots
client.channel_history              # longitudinal channel snapshots

# Analytics views
client.analytics_by_month           # monthly political speech stats
client.analytics_by_channel         # per-channel political speech stats
client.analytics_by_country         # per-country political speech stats
client.analytics_by_gender          # per-gender political speech stats
```

### Common Methods

Every table endpoint supports:

```python
# List rows with filters
rows = client.videos.list(
    select=["video_id", "video_title", "video_views", "platform"],
    order="video_views.desc",
    limit=10,
    country="FR",
    platform="youtube",
    status="active",
)

# Get a single row by primary key
video = client.videos.get(video_id="dQw4w9WgXcQ")

# Count matching rows
n = client.comments.count(video_id="dQw4w9WgXcQ")
```

### Search (FTS · Semantic · Hybrid)

`client.search` exposes four methods covering the four corpus levels.
Each accepts `mode="fts" | "semantic" | "hybrid"`:

| `mode`     | Backend                          | When to use                              |
|------------|----------------------------------|------------------------------------------|
| `fts`      | PostgreSQL full-text (default)   | Exact words / lemmas, fast               |
| `semantic` | Qwen3-Embedding-8B cosine        | Find meaning, paraphrases, related ideas |
| `hybrid`   | Reciprocal Rank Fusion of both   | Best of both — same words *and* meaning  |

```python
# 1) Video-level (one row per video, full-transcript embedding)
hits = client.search.full_transcripts(
    "désastre migratoire",
    mode="semantic",
    country="FR",
    page_size=10,
)

# 2) Speaker-segment level (per speaker turn inside a video)
hits = client.search.transcriptions(
    "politique étrangère",
    mode="hybrid",
    page_size=20,
)

# 3) Sentence level (finest granularity — main retrieval target)
hits = client.search.sentences(
    "réforme des retraites",
    mode="semantic",
    page_size=20,
)

# 4) Comments (raw, one row per comment)
hits = client.search.comments(
    "immigration",
    mode="semantic",
    min_likes=5,
    page_size=20,
)

for h in hits:
    print(f"rank={h.rank:.3f}  total={h.total_count}")
    print(h["headline"])  # <mark>-wrapped snippet (FTS / hybrid only)
```

Every result is a `SearchResult` carrying:
- `rank` — relevance score (cosine for semantic, ts_rank_cd for FTS,
  RRF combined score for hybrid)
- `total_count` — total matching rows (server-computed, capped at 2 000
  for performance)
- `extras` — all other columns the RPC returned. Access them by key
  (`h["video_id"]`, `h["headline"]`, `h["model_labels"]`…) or via
  `h.get("col", default)`.

#### Qwen3 instruction-aware retrieval

Pass an `instruction=` string to bias semantic retrieval toward a
specific intent (per Qwen3 docs: +1–5 % retrieval quality vs the
default query prompt):

```python
# Default semantic: finds passages on the topic, regardless of stance
hits_neutral = client.search.sentences("politique migratoire", mode="semantic")

# Bias toward defending stance
hits_defend = client.search.sentences(
    "politique migratoire",
    mode="semantic",
    instruction="Find passages defending open immigration and refugee rights",
)

# Bias toward criticism / counter-arguments
hits_counter = client.search.sentences(
    "politique migratoire",
    mode="semantic",
    instruction="Find counter-arguments to immigration restrictions",
)
```

#### Intersecting with classifier predictions

Pass a `ModelFilter` to combine a semantic query with any classifier's
predictions. Filters are evaluated **before** the embedding lookup, so
they cut the candidate set efficiently:

```python
from youpol import ModelFilter

flt = (ModelFilter()
       .label("pol_detect", "political_yes")
       .prob_range("pol_detect", min=0.8)
       .video_pct("pol_detect", min=30, scope="tsp"))

hits = client.search.sentences(
    "immigration",
    mode="hybrid",
    instruction="Find passages with strong rhetorical framing",
    model_filter=flt,
    page_size=20,
)
```

#### Graceful degradation

When `mode="semantic"` is requested but the encoder daemon is unreachable
(e.g. during a model swap), the call automatically falls back to
`mode="fts"` and you still get results. Set `fallback_fts=False` to
re-raise `SemanticUnavailable` instead.

Common keyword arguments on every search method:

| Argument             | Meaning                                                  |
|----------------------|----------------------------------------------------------|
| `mode`               | `"fts"` (default) `"semantic"` `"hybrid"`                |
| `instruction`        | Qwen3 instruction for semantic / hybrid                  |
| `ideas`              | Filter on `videos.ideas` (e.g. `["Far_right"]`)          |
| `country`            | Filter on `videos.country` (`"FR"`, `"QC"`, …)           |
| `year_from`/`year_to`| Inclusive upload-date bounds                             |
| `channel`            | Substring match on `channel_name`                        |
| `platform`           | `"youtube"` / `"tiktok"` / `None` (both)                 |
| `suppressed_filter`  | `None` (active) / `"only"` (deleted) / `"all"`           |
| `page_num`/`page_size` | 1-indexed pagination                                   |
| `model_filter`       | `ModelFilter` for classifier cross-filtering             |

### Filtering

| Syntax | Meaning | Example |
|--------|---------|---------|
| `column="value"` | Equals | `country="FR"` |
| `column="gt.N"` | Greater than | `video_views="gt.10000"` |
| `column="gte.N"` | Greater or equal | `video_views="gte.10000"` |
| `column="lt.N"` | Less than | `video_views="lt.1000"` |
| `column="lte.N"` | Less or equal | `video_views="lte.1000"` |
| `column="neq.value"` | Not equal | `country="neq.FR"` |
| `column="like.*pattern*"` | Pattern match (case-sensitive) | `video_title="like.*Macron*"` |
| `column="ilike.*pattern*"` | Pattern match (case-insensitive) | `video_title="ilike.*macron*"` |
| `column=["a", "b"]` | In list | `country=["FR", "QC"]` |
| `column=None` | Is NULL | `description=None` |
| `platform="youtube"` | Platform filter | Filter by YouTube only |
| `status="active"` | Status filter | Active content only |

### Sorting

```python
# Single column
client.videos.list(order="video_views.desc")

# Multiple columns
client.videos.list(order="country.asc,video_views.desc")
```

### Pagination

The client automatically paginates large result sets:

```python
# Fetches all matching rows (multiple requests if needed)
all_videos = client.videos.list(country="FR")

# Limit total results
first_500 = client.videos.list(country="FR", limit=500)
```

### Pandas Integration

```python
import youpol.pandas_ext  # activate .to_dataframe()

df = client.videos.to_dataframe(
    select=["video_id", "video_title", "video_views", "country", "platform", "status"],
    country="FR",
    order="video_views.desc",
    limit=1000,
)
```

## Discovering classifiers (`client.models`)

The YouPol corpus can host multiple classifiers at the same time — new ones are added via the admin panel without a client release. Use `client.models` to discover what is active and how its output is stored.

```python
for m in client.models.list():
    print(m.display_name, m.storage_key, m.task_type, m.api_tables)

pol = client.models.get(model_key="pol_detect")
print(pol.label_list())        # ['political_no', 'political_yes']
print(pol.column_names)        # ['pol_detect_label', 'pol_detect_label_id', ...]
print(pol.display_label('political_yes'))  # 'Political' (admin-configured)
```

### Column conventions

For every active model, the processed tables gain new columns whose names follow a fixed pattern based on the model's `storage_key`:

| `task_type` | Columns added per target table |
|---|---|
| `single_label_classification` | `{sk}_label` (TEXT) · `{sk}_label_id` (float) · `{sk}_probability` (float) · `{sk}_language` (TEXT) · `{sk}_annotated` (BOOLEAN) |
| `multi_label_classification` | `{sk}_scores` (JSONB) — single document holding `{scores: {label: prob}, active: [labels ≥ threshold], threshold, language, annotated}` |

Two models can share a `storage_key` on **disjoint** tables (e.g. one pol_detect on transcripts, another on comments) — both write to the same `pol_detect_*` columns on their own tables. The admin UI enforces this is non-overlapping.

### Filtering on a classifier's output

Any column added by a classifier is immediately queryable — no client update needed. Use `m.column_names` in `select=` and plain kwargs in filter positions:

```python
# Single-label: exact label + probability range
m = client.models.get(model_key="pol_detect")
rows = client.processed_speaker_segments.list(**{
    f"{m.storage_key}_label":       m.positive_label,   # eq.political_yes
    f"{m.storage_key}_probability": "gte.0.9",
    "limit": 20,
})

# Multi-label: at least one label active (JSONB contains)
m = client.models.get(model_key="topics_ml")
rows = client.processed_comments.list(**{
    f"{m.storage_key}_scores->active": 'cs.["sports"]',
    "limit": 50,
})

# Multi-label: score threshold on a specific label
rows = client.processed_comments.list(**{
    f"{m.storage_key}_scores->scores->>politics": "gte.0.6",
})
```

Dynamic columns from freshly-deployed classifiers that the client dataclass doesn't declare are automatically attached to each row under `.extras`:

```python
rows = client.processed_comments.list(limit=1)
print(rows[0].extras)
# {'hate_speech_label': 'benign', 'topics_scores': {...}, ...}
```

### Display labels

The admin can override how each raw label appears in API responses and on `data.you-pol.com`. The mapping ships on every model under `display_config.labels`:

```python
m = client.models.get(model_key="pol_detect")
m.display_label("political_yes")   # "Political"
m.display_label("political_no")    # "Non-political"

# Or inspect the raw mapping
print((m.display_config or {}).get("labels"))
# {"political_yes": "Political", "political_no": "Non-political"}
```

The internal label values used in DB columns and filter params stay unchanged — only presentation changes.


## Database Schema

### `videos_with_update` (VIEW — unified YouTube + TikTok)

| Column | Type | Description |
|--------|------|-------------|
| `video_id` | str (PK) | Platform video ID |
| `channel_name` | str | Channel display name |
| `video_title` | str | Video title |
| `video_views` | int | View count |
| `subscribers` | int | Channel subscriber/follower count |
| `video_likes` | int | Like count |
| `video_comments_count` | int | Comment count |
| `upload_date` | date | Upload date |
| `duration` | int | Duration in seconds |
| `ideas` | str | Political orientation: `Far_right`, `Left`, `Masc`, `Comp` |
| `gender` | str | Speaker gender: `"H"`, `"F"`, `"Mixte"` |
| `country` | str | Channel country: `"FR"` or `"QC"` |
| `suppressed` | bool | Video removed/private |
| `suppressed_at` | timestamp | When flagged as suppressed |
| `suppression_reason` | str | Why: `deleted`, `deactivated`, `terminated`, `members_only`, `unavailable` |
| `last_update` | timestamp | Last metadata scan |
| `status` | str | `active` / `suppressed` / `trashed` |
| `platform` | str | `youtube` or `tiktok` |
| `trashed_at` | timestamp | Admin trash timestamp (YouTube only) |

### `comments_with_status` (VIEW — unified YouTube + TikTok)

| Column | Type | Description |
|--------|------|-------------|
| `comment_id` | int (PK) | Internal ID |
| `id` | str | Platform comment ID |
| `video_id` | str (FK) | Video ID |
| `text` | str | Comment text |
| `like_count` | int | Likes on the comment |
| `author` | str | Commenter display name |
| `timestamp` | date | Date posted |
| `suppressed` | bool | Comment deleted |
| `suppressed_at` | timestamp | When flagged as deleted |
| `status` | str | `active` / `suppressed` |
| `platform` | str | `youtube` or `tiktok` |

### `video_transcripts` (VIEW — unified YouTube + TikTok)

| Column | Type | Description |
|--------|------|-------------|
| `video_id` | str (PK) | Video ID |
| `original_diarized_transcript` | str | Raw transcript with speaker markers |
| `cleaned_transcript` | str | Cleaned transcript |
| `transcribed_at` | timestamp | When transcribed |
| `transcript_status` | str | `ok` or `no_speech` |
| `status` | str | `active` / `suppressed` (from parent video) |
| `platform` | str | `youtube` or `tiktok` |

### `speakers_with_pol` (VIEW — unified YouTube + TikTok)

| Column | Type | Description |
|--------|------|-------------|
| `transcript_speaker_id` | int (PK) | Internal ID |
| `video_id` | str (FK) | Video ID |
| `speaker` | str | Speaker label (`"SPEAKER_00"`, ...) |
| `segment_order` | int | Position in transcript |
| `speaker_transcript` | str | Segment text |
| `pol_detect_label` | str | `"political_yes"` / `"political_no"` |
| `pol_detect_probability` | float | Classifier confidence (0-1) |
| `sentences_total` | int | Total sentences in segment |
| `sentences_political` | int | Political sentences in segment |
| `pct_political` | float | % political sentences |
| `avg_confidence` | float | Avg confidence for political sentences |
| `status` | str | `active` / `suppressed` (from parent video) |
| `platform` | str | `youtube` or `tiktok` |

### `comments_processed` (VIEW — unified YouTube + TikTok)

| Column | Type | Description |
|--------|------|-------------|
| `comment_id` | int (PK) | References original comment |
| `sentence_id` | int (PK) | Sentence index |
| `text` | str | Sentence text |
| `ner_entities` | dict | Named entities: `{"PER": [...], "LOC": [...], "ORG": [...]}` |

### `transcription_speakers_processed` (VIEW — unified YouTube + TikTok)

| Column | Type | Description |
|--------|------|-------------|
| `transcript_speaker_id` | int (PK) | References original segment |
| `sentence_id` | int (PK) | Sentence index |
| `speaker_transcript` | str | Sentence text |
| `ner_entities` | dict | Named entities: `{"PER": [...], "LOC": [...], "ORG": [...]}` |
| `pol_detect_label` | str | Political classification |
| `pol_detect_probability` | float | Confidence (0-1) |

### `video_metadata_history` (VIEW — unified YouTube + TikTok)

| Column | Type | Description |
|--------|------|-------------|
| `id` | int (PK) | Snapshot ID |
| `video_id` | str | Video ID |
| `video_views` | int | View count at scan time |
| `video_likes` | int | Like count at scan time |
| `video_comments_count` | int | Comment count at scan time |
| `subscribers` | int | Subscriber count at scan time |
| `video_title` | str | Title at scan time |
| `scanned_at` | timestamp | Scan timestamp |

### `channel_metadata_history` (VIEW — unified YouTube + TikTok)

| Column | Type | Description |
|--------|------|-------------|
| `id` | int (PK) | Snapshot ID |
| `channel_name` | str | Channel display name |
| `subscribers` | int | Subscriber count at scan time |
| `total_videos_yt` | int | Videos on platform at scan time |
| `total_videos_db` | int | Videos in database at scan time |
| `total_transcribed` | int | Transcribed videos at scan time |
| `total_comments_db` | int | Comments in database at scan time |
| `scanned_at` | timestamp | Scan timestamp |

### Analytics Views

Four pre-computed views for political speech analysis:

- `analytics_by_month` — columns: `month`, `total_sentences`, `political_sentences`, `pct_political`
- `analytics_by_channel` — columns: `channel_name`, `total_sentences`, `political_sentences`, `pct_political`
- `analytics_by_country` — columns: `country`, `total_sentences`, `political_sentences`, `pct_political`
- `analytics_by_gender` — columns: `gender`, `total_sentences`, `political_sentences`, `pct_political`

## Longitudinal Analysis

The database tracks metadata changes over time. Each metadata scan creates a snapshot in the history tables.

```python
# Video view count evolution
history = client.metadata_history.list(
    video_id="VIDEO_ID",
    order="scanned_at.asc",
)

# Channel subscriber growth
ch_history = client.channel_history.list(
    channel_name="ChannelName",
    order="scanned_at.asc",
)
```

## Examples

See the [`examples/`](examples/) directory:
- [`quickstart.py`](examples/quickstart.py) — Basic usage of all endpoints
- [`pandas_analysis.py`](examples/pandas_analysis.py) — Data analysis with pandas

## License

MIT
