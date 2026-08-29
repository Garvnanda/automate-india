"""Record one unguarded run as a replayable trace — the ghost layer's input.

The ghost is the only thing on the panel that is not live, so two rules govern
this file (docs/v3.md §5.4):

  1. It is a recording of a *real* run. This script runs `agent.main` for real,
     against the real databases, and writes down what actually came back. It
     never synthesises a frame.
  2. Every frame carries `step_index`. Garv syncs the ghost on step index and
     never on wall clock, because the guarded run pauses at a hold for however
     long a human takes — a clock-aligned ghost runs away and the screen turns
     to noise. A trace without step indices is useless to him.

Usage:
    python -m scripts.record_unguarded                 # violation 1, the default
    python -m scripts.record_unguarded --violation 2
    python -m scripts.record_unguarded --out evidence/other_trace.jsonl
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "evidence" / "unguarded_trace.jsonl"


def record(violation=1, out=DEFAULT_OUT, config=None):
    cmd = [sys.executable, "-u", "-m", "agent.main", "--unguarded",
           "--force-violation", str(violation)]
    if config:
        cmd += ["--config", config]

    # reset first: a trace of a run that started from an already-damaged database
    # would show the wrong numbers, and the whole point of the ghost is the
    # numbers diverging from the guarded lane's.
    subprocess.run([sys.executable, "-m", "data.reset"], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)

    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise SystemExit(f"the recorded run failed (exit {proc.returncode}):\n{proc.stderr}")

    run_id, frames, step_index = None, [], None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("run_id="):
            run_id = line.split()[0].partition("=")[2]
            continue
        if not line.startswith("{"):
            continue
        try:
            frame = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = frame.get("type") or next(iter(frame), "")
        if kind not in ("__plan__", "__step__", "__state__", "__verdict__",
                        "__hold__", "__resume__", "__END__") and "__plan__" not in frame:
            # agent.main also prints its JSONL audit line to stdout. That is the
            # log, not a frame; the panel never renders it and the ghost has no
            # use for it. Recording it would just make the trace look padded.
            continue
        if kind == "__plan__" or "__plan__" in frame:
            step_index = None
        elif "step_index" in frame and frame["step_index"] is not None:
            step_index = frame["step_index"]

        # a __state__ frame belongs to the step that just wrote — that is what
        # lets the ghost's gauge drain on the same beat the live lane resolves
        if "step_index" not in frame:
            # -1, not null: the world before the first step ran. The ghost needs
            # a real starting value to drain *from*, and "unknown" is not one.
            frame["step_index"] = step_index if step_index is not None else -1
        frames.append(frame)

    if not frames:
        raise SystemExit("the run produced no frames — nothing to record")

    header = {
        "type": "__trace__",
        "run_id": run_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "mode": "unguarded",
        "violation": violation,
        "command": " ".join(cmd[2:]),
        "frames": len(frames),
        "note": "RECORDED. A real unguarded run, replayed. Sync on step_index, never on wall clock.",
    }

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for frame in frames:
            f.write(json.dumps(frame) + "\n")

    # leave the databases clean: the next thing anyone runs should not inherit
    # this run's damage
    subprocess.run([sys.executable, "-m", "data.reset"], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)
    return header, frames


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--violation", type=int, choices=[1, 2], default=1)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    header, frames = record(args.violation, args.out, args.config)
    kinds = {}
    for f in frames:
        kinds[f.get("type") or next(iter(f), "?")] = kinds.get(f.get("type") or next(iter(f), "?"), 0) + 1
    print(f"recorded {header['frames']} frames from run {header['run_id']} -> {args.out}")
    for kind, n in sorted(kinds.items()):
        print(f"  {n:>3}  {kind}")

    missing = [f for f in frames if f.get("step_index") is None
               and (f.get("type") or next(iter(f), "")) not in ("__plan__", "__END__")]
    if missing:
        raise SystemExit(f"{len(missing)} frames have no step_index — the ghost cannot sync on this")
    print("every replayable frame carries step_index")


if __name__ == "__main__":
    main()
