#!/usr/bin/env python3
"""One-shot LLM call: read a prompt on stdin, print the answer on stdout.

The adapter behind `ab_context.py --engine custom`. Deliberately:
  - no dependencies (urllib only), so it runs on a bare python3
  - credentials come from the environment, never from a file or a flag
  - temperature 0, so a rerun reproduces the same table
  - exits non-zero on empty content instead of printing nothing: a reasoning
    model that burns its budget on chain-of-thought must not be scored as a
    wrong answer, because that turns a broken engine into a fake gap

Env: LLM_BASE_URL (OpenAI-compatible, with or without /v1), LLM_API_KEY,
     LLM_MODEL, and optionally LLM_MAX_TOKENS, LLM_EXTRA_JSON, LLM_TIMEOUT.

    export LLM_BASE_URL=https://api.deepseek.com LLM_MODEL=deepseek-chat
    export LLM_API_KEY=...                       # your key, never committed
    python3 scripts/ab_context.py --engine custom \
        --cmd "python3 examples/llm-once.py" ...
"""
import json
import os
import sys
import urllib.error
import urllib.request

base = os.environ.get("LLM_BASE_URL", "").strip().rstrip("/")
key = os.environ.get("LLM_API_KEY", "").strip()
model = os.environ.get("LLM_MODEL", "").strip()
timeout = float(os.environ.get("LLM_TIMEOUT", "120"))

missing = [n for n, v in (("LLM_BASE_URL", base), ("LLM_API_KEY", key),
                          ("LLM_MODEL", model)) if not v]
if missing:
    sys.exit("llm-once: missing env " + ", ".join(missing))

prompt = sys.stdin.read()
if not prompt.strip():
    sys.exit("llm-once: empty prompt on stdin")

max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "4000"))
body = {
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0,
    "max_tokens": max_tokens,
    "stream": False,
}
# Vendor knobs, e.g. LLM_EXTRA_JSON='{"thinking":{"type":"disabled"}}' to stop a
# reasoning model from burning the token budget on chain-of-thought before it
# writes a single word. Malformed JSON is a hard error, never silently ignored.
extra = os.environ.get("LLM_EXTRA_JSON", "").strip()
if extra:
    try:
        body.update(json.loads(extra))
    except json.JSONDecodeError as exc:
        sys.exit(f"llm-once: LLM_EXTRA_JSON is not valid JSON: {exc}")
body = json.dumps(body).encode("utf-8")

req = urllib.request.Request(
    base + "/chat/completions",
    data=body,
    headers={"Content-Type": "application/json",
             "Authorization": "Bearer " + key},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
except urllib.error.HTTPError as exc:
    sys.exit(f"llm-once: HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}")
except Exception as exc:  # noqa: BLE001 - one-shot tool, report and die
    sys.exit(f"llm-once: {type(exc).__name__}: {exc}")

try:
    choice = payload["choices"][0]
    text = (choice["message"]["content"] or "").strip()
except (KeyError, IndexError, TypeError):
    sys.exit("llm-once: unexpected payload: " + json.dumps(payload)[:300])

# A reasoning model can spend every token on its chain of thought and return an
# empty string. Exiting 0 there would let the harness score "no content" as
# "answered wrong" — the exact false green ab_context.py exists to prevent.
if not text:
    usage = payload.get("usage", {})
    rt = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
    sys.exit(
        f"llm-once: empty content (finish_reason={choice.get('finish_reason')}, "
        f"reasoning_tokens={rt}, max_tokens={max_tokens}). Raise LLM_MAX_TOKENS."
    )
print(text)
