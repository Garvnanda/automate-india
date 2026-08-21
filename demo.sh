#!/usr/bin/env bash
# The full demo sequence, in the order technical.md §9 lays out:
#   1. unguarded — the damage is real
#   2. reset
#   3. guarded happy path — flows freely
#   4. guarded violation 1 — blocked, rows survive
#   5. guarded violation 2 — held, approve it live, agent resumes
#
# Guarded steps need `python -m agent.infra` running in another terminal
# first (tunnels + registration) — this script checks for that and tells
# you plainly if it's missing rather than failing halfway through.

set -e
cd "$(dirname "$0")"

pause() { read -r -p "  [press enter to continue] " _ || true; }
banner() { echo; echo "════════════════════════════════════════════════"; echo "  $1"; echo "════════════════════════════════════════════════"; }

banner "1/6 — UNGUARDED. Same agent, no enforcement. Watch it break something."
python data/reset.py
pause
python -m agent.main --unguarded --force-violation 1
echo
python -m agent.main --unguarded --force-violation 2

banner "2/6 — RESET. Rows and registry back to a clean baseline."
python data/reset.py

if [ ! -f .session.json ]; then
  echo
  echo "No .session.json — guarded steps need the MCP servers tunneled and"
  echo "registered first. In another terminal, run:"
  echo
  echo "    python -m agent.infra"
  echo
  echo "then re-run this script."
  exit 1
fi

banner "3/6 — GUARDED, happy path. Same agent, same prompt, everything through ArmorIQ."
pause
python -m agent.main --guarded

banner "4/6 — GUARDED, violation 1. delete_rows was never in the signed plan."
python data/reset.py
pause
python -m agent.main --guarded --force-violation 1 || true
echo "rows survived — verify with: python tests/test_mcp_servers.py"

banner "5/6 — GUARDED, violation 2. Production exceeds staging-only authority."
python data/reset.py
pause
echo "This will HOLD. Approve it now at platform.armoriq.ai -> Intent -> Held Actions."
python -m agent.main --guarded --force-violation 2

banner "6/6 — Done. Open the ArmorIQ dashboard's Plan Detail Proof/Audit tabs for the trail."
