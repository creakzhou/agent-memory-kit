# Wikilink hygiene

Created: 2026-11-09
Status: active
Links: [[about-me]] · [[working-agreements]]

## Context

A vault with 1,100 links is useful. A vault with 1,100 links of which 200 point
at renamed files is worse than no links, because it teaches the agent to ignore
broken pointers — including the ones that matter.

## Body

Rules that kept the graph usable:

1. One concept, one note name. If two notes need the same title, one of them is
   actually two concepts.
2. Rename with a link check, not by hand. Run the checker after every rename.
3. A link that cannot resolve is deleted on sight. A placeholder `[[todo]]` left
   for a week becomes permanent.
4. Index lines are the only place a summary lives. Do not copy summaries into
   project notes.

## Decision / conclusion

Treat a dangling link as a failing test, not a cosmetic issue. It is the cheapest
signal available that the memory system has started lying.

## History

| Date | Change | Why |
|---|---|---|
| 2026-11-09 | created | 38 dangling links found after a folder rename |
