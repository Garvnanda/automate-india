"""Ask the agent — free-text Q&A grounded in one real run's actual transcript.

Not a new agent, not a tool-calling loop: one plain chat completion, given the
real logged events for a run_id and nothing else. If the model answers outside
what the transcript shows, that's a prompt-following failure to note, not
something this module tries to prevent — it only supplies the grounding.
"""

import json
import re
import urllib.error
import urllib.request

from agent.config import LOGS_DIR, OPENROUTER_API_KEY, OPENROUTER_MODEL

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# uuid.uuid4().hex[:12] — exactly 12 lowercase hex chars, always. Validated
# before touching the filesystem so a crafted run_id can't walk outside
# LOGS_DIR (the same discipline as every other user-facing input this
# session — see RunConfig's validation, the CSRF gate, the origin-side MCP
# auth).
RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")
QUESTION_MAX_LEN = 500

SYSTEM_PROMPT = (
    "You are the ML pipeline agent, explaining a run you already completed to "
    "the person watching. Answer only from the transcript below — never invent "
    "a tool call, a number, or an outcome that isn't in it. If the question "
    "asks about something outside the transcript (a hypothetical, a different "
    "run), say so plainly instead of guessing. Speak in first person ('I read "
    "the dataset card...'). Be concise: 2-4 sentences unless the question "
    "genuinely needs more."
)


def transcript_for(run_id):
    """The real event log for one run, as plain lines an LLM can read."""
    if not RUN_ID_RE.match(run_id or ""):
        raise ValueError(f"not a real run id: {run_id!r}")
    path = LOGS_DIR / f"{run_id}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"no log for run {run_id}")

    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        e = json.loads(raw)
        reason = f" ({e['reason']})" if e.get("reason") else ""
        lines.append(f"step {e['step']}: {e['action']} on {e['mcp']} "
                     f"with {e['params']} -> {e['verdict']}{reason}")
    if not lines:
        raise FileNotFoundError(f"log for run {run_id} is empty")
    return "\n".join(lines)


def ask(run_id, question):
    """Returns the agent's answer as plain text. Raises ValueError (bad input),
    FileNotFoundError (unknown run), or RuntimeError (OpenRouter/config failure)
    — callers map these to HTTP status, same pattern as RunConfig validation."""
    question = (question or "").strip()
    if not question:
        raise ValueError("empty question")
    if len(question) > QUESTION_MAX_LEN:
        raise ValueError(f"question is {len(question)} chars, max {QUESTION_MAX_LEN}")
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    transcript = transcript_for(run_id)
    body = json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"TRANSCRIPT:\n{transcript}\n\nQUESTION: {question}"},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL, data=body,
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenRouter {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"OpenRouter unreachable: {e.reason}")

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"OpenRouter response missing an answer: {data}")
