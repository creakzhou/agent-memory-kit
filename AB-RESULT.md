| Question | With context file | With `-nc` |
|---|---|---|
| The memory rules file has a hard character budget. What does the host do when that budget is exceeded? | correct — "When the memory rules file exceeds its 3600-character budget, the host injects nothing at all — it does not truncate." | not answered — "not available" |
| Where do decisions with their reasons get written, and may an old decision be rewritten? | correct — "Decisions with their reasons go in `04-decisions` (append-only, never rewrite history), and an old decision may not be rewritten — contradictions are…" | not answered — "Not available." |
| How many notes should be read before concluding the index is wrong? | correct — "Read at most three notes; if three are not enough, the index is wrong and should be fixed rather than reading more." | not answered — "Not available." |
| Which prefix holds finished or dead work? | correct — "The `10-archive` prefix holds finished or dead work — items are moved there rather than deleted, and their index lines are kept so old decisions stay…" | not answered — "The prefix that holds finished or dead work is "ex-", as in "ex-" meaning former or no longer active." |
| A note seems to need two titles. What do you do? | correct — "Split it into two notes, one topic each, and add an index line for each." | not answered — "If a note seems to need two titles, use a compound title (e.g., "Main Title: Subtitle") or choose the most descriptive one and mention the alternative…" |
| What storage does this memory system use? | correct — "The memory system uses plain markdown files organized in numbered folders within a vault directory (`/private/tmp/abvault/vault`) — no database, embed…" | not answered — "not available" |

`6/6` vs `0/6` correct · 3 run(s) per cell · engine `custom` · model `deepseek-v4-flash`
