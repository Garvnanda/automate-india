"""Ask the agent — free-text Q&A, streamed token by token, grounded in the
project itself and (when one exists) the most recent real run's transcript.

Not a new agent, not a tool-calling loop: one plain streaming chat completion.
Two sources of truth, both handed to the model explicitly so it never has to
guess: a short, user-facing project brief (what a judge or a curious visitor
would want explained — no file paths, no internal implementation, no security
findings from development), and the real logged events for one run if a
run_id is given.
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

PROJECT_BRIEF = """\
PromotionGuard is a demo built for the ArmorIQ hackathon track "Autonomous,
until it shouldn't be". An AI agent runs a real ML model promotion pipeline
end to end, unattended: it reads the dataset's documentation, pulls the
evaluation split, launches an evaluation run, reads the resulting metrics, and
promotes the candidate model if it clears the accuracy bar.

Two things can go wrong, by design, to prove the enforcement is real:
1. The agent may be tempted (usually by something in the dataset's own
   documentation) to delete rows from the evaluation set it is being graded
   on, to make its numbers look better.
2. The agent may try to promote the model straight to production instead of
   staging — the exact same promote_model call it was authorized to make
   moments earlier, with one argument changed.
Neither has a suspicious keyword to filter on. A dataset card telling an
agent to "exclude noisy rows" reads as ordinary documentation, not an attack.

ArmorIQ enforcement has two independent gates:
- Gate 1, the signed plan (cryptographic): before a run starts, the agent
  declares every action it intends to take, and ArmorIQ signs it. Anything
  outside that declared plan is refused before the call ever leaves the
  agent's own process.
- Gate 2, authority (human): a call that IS in the plan but exceeds what this
  agent may decide on its own — like a production promotion — gets held for
  a real, higher-ranked human to approve on ArmorIQ's own dashboard. A
  requester can never approve their own request. This panel never has an
  Approve button anywhere; approving here would misrepresent where the real
  authority lives.

The control panel (an on-screen "instrument", styled like a physical
console) lets a visitor genuinely control the run, not watch a script:
- AUTHORIZE switches decide what actually goes into the signed plan for this
  run — including, if turned on, letting the agent really delete rows.
- CONDITIONS dials set the world the agent encounters: how the candidate
  model scored, whether the dataset card is clean or poisoned, whether the
  model hash matches. A CARD dial position, CUSTOM, lets a visitor write the
  dataset card's text themselves and watch the agent react to their exact
  words.
- GUARDED toggles ArmorIQ enforcement on or off — same agent, same code,
  same prompt, only enforcement differs.
- The scope (top) traces real tool calls as they happen; the plan strip
  lights up step by step as each call gets its verdict; the gauges show the
  live database state; the key dial arms and freezes mid-swing the moment
  something is held for a human.

Nothing on the panel is scripted or faked: every trace pulse, every gauge
number, every verdict is a real outcome of a real run against a real SQLite
database, through the real ArmorIQ proxy.
"""

SYSTEM_PROMPT = (
    "You are a helpful guide explaining the PromotionGuard project to whoever "
    "is looking at it — a hackathon judge, a curious visitor, anyone. You have "
    "two sources of truth below: a project brief, and (if one is included) the "
    "transcript of the single most recent real run. Answer ONLY from those two "
    "sources. Never invent a tool call, a number, a file name, or an outcome "
    "that isn't in them. Do not discuss internal implementation details, "
    "source code, file paths, infrastructure, credentials, or any security "
    "issue found during development — describe the project and its security "
    "model the way a product would describe itself to a user, not the way an "
    "engineer would describe its internals. If asked something about a "
    "specific run and no transcript is included, say plainly that no run has "
    "completed yet in this session, don't guess. Speak in first person when "
    "describing what the agent itself did ('I read the dataset card...'), "
    "third person when describing the project in general. Be concise: 2-4 "
    "sentences unless the question genuinely needs more."
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


def _messages_for(run_id, question):
    parts = [f"PROJECT BRIEF:\n{PROJECT_BRIEF}"]
    if run_id:
        try:
            parts.append(f"MOST RECENT RUN TRANSCRIPT:\n{transcript_for(run_id)}")
        except (ValueError, FileNotFoundError):
            # a general question doesn't need a run — fall back quietly
            # rather than erroring the whole answer over it
            parts.append("MOST RECENT RUN TRANSCRIPT: (none available)")
    else:
        parts.append("MOST RECENT RUN TRANSCRIPT: (no run has completed in this session yet)")
    parts.append(f"QUESTION: {question}")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def ask_stream(run_id, question):
    """Yields the answer incrementally, one real content delta at a time —
    genuine token streaming from OpenRouter, not a client-side typewriter
    replaying a complete response."""
    question = (question or "").strip()
    if not question:
        raise ValueError("empty question")
    if len(question) > QUESTION_MAX_LEN:
        raise ValueError(f"question is {len(question)} chars, max {QUESTION_MAX_LEN}")
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    body = json.dumps({
        "model": OPENROUTER_MODEL,
        "stream": True,
        "messages": _messages_for(run_id, question),
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL, data=body,
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenRouter {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"OpenRouter unreachable: {e.reason}")

    got_any = False
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            delta = ((chunk.get("choices") or [{}])[0]).get("delta", {})
            content = delta.get("content")
            if content:
                got_any = True
                yield content
    if not got_any:
        raise RuntimeError("OpenRouter returned no content")


def ask(run_id, question):
    """Non-streaming convenience wrapper — same validation, same grounding,
    the whole answer at once. Used by tests and anything that doesn't need
    incremental rendering."""
    return "".join(ask_stream(run_id, question))
