"""
Discovering classifiers and using their annotations.

The YouPol corpus can host multiple classifiers at the same time — a new one
can be added via the admin panel without any client release. This example
shows how to:

  1. List every active classifier (single- and multi-label)
  2. Read its label vocabulary
  3. Build a dynamic SELECT that includes the model's output columns
  4. Filter on single-label predictions and probabilities
  5. Filter on multi-label: "has label X", score-threshold per label
"""

from youpol import YouPol

TOKEN = "YOUR_TOKEN_HERE"
client = YouPol(token=TOKEN)


# ---------------------------------------------------------------------------
# 1. Discover active classifiers
# ---------------------------------------------------------------------------
print("Active classifiers in the corpus:")
for m in client.models.list():
    print(f"  - {m.display_name} ({m.model_key})")
    print(f"      storage_key:   {m.storage_key}")
    print(f"      task_type:     {m.task_type}")
    print(f"      labels:        {m.label_list()}")
    print(f"      api_tables:    {m.api_tables}")
    print(f"      column_names:  {m.column_names}")
    if m.is_multi_label:
        print(f"      threshold:     {m.multi_label_threshold}")


# ---------------------------------------------------------------------------
# 2. Single-label: fetch rows with a specific label + high confidence
# ---------------------------------------------------------------------------
pol = client.models.get(model_key="pol_detect")

political = client.processed_speaker_segments.list(**{
    f"{pol.storage_key}_label": pol.positive_label,         # e.g. "political_yes"
    f"{pol.storage_key}_probability": "gte.0.9",
    "limit": 20,
    "order": f"{pol.storage_key}_probability.desc",
})
print(f"\nTop 20 highly-political sentences ({pol.positive_label}):")
for r in political:
    print(f"  [{r.pol_detect_probability:.3f}] {(r.speaker_transcript or '')[:100]}")


# ---------------------------------------------------------------------------
# 3. Multi-label: "has at least one of these labels" via JSONB 'contains'
# ---------------------------------------------------------------------------
# Assuming an active multi-label classifier with storage_key "topics_ml"
topics = next((m for m in client.models.list() if m.storage_key == "topics_ml"), None)

if topics and topics.is_multi_label:
    # PostgREST 'cs' (contains) on the JSONB 'active' array:
    sports_rows = client.processed_comments.list(**{
        f"{topics.storage_key}_scores->active": 'cs.["sports"]',
        "limit": 10,
    })
    print(f"\nRows where 'sports' is in the active labels (threshold={topics.multi_label_threshold}):")
    for r in sports_rows:
        scores = r.extras.get(f"{topics.storage_key}_scores", {})
        active = scores.get("active") if isinstance(scores, dict) else None
        print(f"  {active} — {(r.text or '')[:80]}")

    # ------------------------------------------------------------------
    # 4. Multi-label: score threshold on a specific label
    # ------------------------------------------------------------------
    # PostgREST JSON-arrow path: col->key->>subkey returns text — cast in
    # a filter by using a numeric-op:
    politics_heavy = client.processed_comments.list(**{
        f"{topics.storage_key}_scores->scores->>politics": "gte.0.6",
        "limit": 10,
    })
    print(f"\nRows with politics score ≥ 0.6:")
    for r in politics_heavy:
        scores = r.extras.get(f"{topics.storage_key}_scores", {})
        if isinstance(scores, dict):
            print(f"  politics={scores.get('scores', {}).get('politics')} — "
                  f"{(r.text or '')[:80]}")


# ---------------------------------------------------------------------------
# 5. Any unknown columns are accessible via `.extras` on every row
# ---------------------------------------------------------------------------
# When a new classifier is deployed to the DB, its columns are immediately
# readable from the client even before the dataclass declares them:
rows = client.processed_speaker_segments.list(limit=1)
if rows and getattr(rows[0], "extras", None):
    print("\nDynamic columns detected on this row:")
    for k, v in rows[0].extras.items():
        print(f"  {k} = {v!r}")
