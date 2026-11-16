# Hybrid retrieval beats pure embedding for a personal vault

Created: 2026-11-11
Status: decided
Links: [[wikilink-hygiene]] · [[vault-migration]]

## Context

Under 500 notes, is an embedding index worth the moving parts? Tested three
configurations against 30 real queries and 2 garbage queries.

## Body

| Config | Real recall@5 | Garbage hits | Setup cost |
|---|---|---|---|
| TF-IDF over char bigrams | 27/30 | 0 | none |
| Embedding, cosine 0.8 | 29/30 | 0 | index + API |
| Embedding, cosine 0.45 | 30/30 | **2/2** | index + API |

The 0.45 row is the one that matters. It scored perfectly on real queries and
also returned confident results for a string of random characters. Recall went up
and precision went to zero at the same time.

## Decision / conclusion

Use lexical retrieval as the default and keep embeddings for cross-language
queries only. Never tune the threshold on hit count — tune it on a negative
control that should return nothing.

## History

| Date | Change | Why |
|---|---|---|
| 2026-11-11 | created | threshold sweep finished |
| 2026-11-12 | added the garbage column | first write-up omitted it, which was the whole point |
