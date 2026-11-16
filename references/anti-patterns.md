# Anti-patterns

Nine ways these systems fail. Each one looks fine from the outside for about a week.

## 1. Mixing the three layers

**Symptom:** the discipline file is 6,000 characters, half of it project notes.
**Why it fails:** the host has an injection cap. Over the cap it injects nothing, so
all your rules disappear at once — not the least important ones, all of them.
**Fix:** identity stays short, discipline holds cross-project rules only, everything
specific goes to a note with a pointer left behind.

## 2. Empty files to look complete

**Symptom:** the structure is perfect and every note is a template heading.
**Why it fails:** an empty vault costs context on every read and returns nothing.
Worse, it makes the system look finished, so nobody fills it.
**Fix:** three real notes beat thirty placeholders. Create notes when a fact exists,
not when a folder exists.

## 3. Index drift

**Symptom:** notes exist that no index line points to.
**Why it fails:** retrieval goes through the index. An unindexed note is invisible,
so the agent re-derives a fact that was already written down — the exact waste the
system was built to prevent.
**Fix:** adding a note and adding its index line are one action, not two.

## 4. Dangling pointers

**Symptom:** the discipline file says "see `preferences/deploy-rules.md`" and that
file was renamed three weeks ago.
**Why it fails:** a pointer that does not resolve teaches the agent that the
discipline file is unreliable. After two of those, it stops following the rules that
do resolve.
**Fix:** `link_check.py` after every rename. Treat a dangling link as a failing test.

## 5. Budget creep

**Symptom:** 3,950 of 4,000 characters, and everyone keeps adding "just one line".
**Why it fails:** the failure is binary and silent. Below the cap everything works;
above it nothing does. There is no warning from the host.
**Fix:** `budget_check.py` in CI. Keep 15% headroom so the next rule does not break it.

## 6. Counting recall rows as proof

**Symptom:** "it returned 3 memories, so memory works."
**Why it fails:** lower the threshold and garbage returns 3 memories too. Row count
measures the threshold, not the relevance.
**Fix:** measure the score of a **negative control** — a query that should return
nothing. If it returns something, the threshold is too loose regardless of what the
real queries did.

## 7. Re-using the negative control

**Symptom:** the same "this should not be found" string in every verification report.
**Why it fails:** once written into a report, the string becomes a stored memory. The
next test finds it, and the test that was supposed to prove precision now produces a
false positive — permanently.
**Fix:** one use per control string. Rotate them, and keep them out of the vault.

## 8. Claiming automatic recall

**Symptom:** the README says "your agent will remember automatically".
**Why it fails:** on hosts without lifecycle hooks, nothing is automatic. Users
discover this in day two and stop trusting every other claim in the project.
**Fix:** state the actual mode. "Manual with explicit triggers" is a weaker promise
and a much better product.

## 9. Secrets in the discipline file

**Symptom:** an API key pasted into `MEMORY.md` because "it is only local".
**Why it fails:** the discipline file is injected into every session, sent to the
model provider, and often committed to a repo.
**Fix:** no secrets in any layer. Reference an environment variable name only.
