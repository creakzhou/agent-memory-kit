# Vault migration: flat folder to numbered prefixes

Created: 2026-11-10
Status: active
Links: [[legacy-flat-notes]] · [[wikilink-hygiene]]

## Context

The old vault was 40 loose notes in one folder. Finding anything required
remembering a filename. Migration took one evening.

## Body

| Before | After | Notes |
|---|---|---|
| `notes/` (40 files) | `01-projects`, `03-preferences`, `04-decisions`, `05-reviews`, `10-archive`, `20-notes` | sorted by hand, 8 files went to archive |
| no index | `00-index.md` | one line per note, written last |
| 3 duplicate "meeting notes" | merged into project notes | lost nothing of value |

Order of work mattered: build folders, move files, **then** write the index. Doing
the index first meant rewriting it after every move.

## Decision / conclusion

Numbered prefixes beat tags because a tag can be forgotten and a number cannot.
The number also fixes sort order in every editor without configuration.

## History

| Date | Change | Why |
|---|---|---|
| 2026-11-10 | created | migration finished |
| 2026-11-12 | added the ordering lesson | second migration attempt went wrong the same way |
