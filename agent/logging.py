"""Fixed log line contract — do not change without updating the panel.

{ts, mode, step, action, mcp, params, verdict, reason}
verdict in allowed | blocked | held | approved | executed
"""

import json
from datetime import datetime, timezone

from agent.config import LOGS_DIR, VERDICTS


def log_event(run_id, mode, step, action, mcp, params, verdict, reason=""):
    if verdict not in VERDICTS:
        raise ValueError(f"bad verdict {verdict!r}, must be one of {VERDICTS}")

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "step": step,
        "action": action,
        "mcp": mcp,
        "params": params,
        "verdict": verdict,
        "reason": reason,
    }
    line = json.dumps(event)
    print(line)

    LOGS_DIR.mkdir(exist_ok=True)
    with open(LOGS_DIR / f"{run_id}.jsonl", "a", encoding="utf-8") as f:
        f.write(line + "\n")

    return event
