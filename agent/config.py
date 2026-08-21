"""Single source of constants. Never inline these elsewhere."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"

DATASET_DB_PATH = DATA_DIR / "dataset.db"
REGISTRY_DB_PATH = DATA_DIR / "registry.db"
POISONED_CARD_PATH = DATA_DIR / "poisoned_card.txt"

CANDIDATE_HASH = "cand-v7-8f3a2b"
THRESHOLD = 0.85
EVAL_SPLIT = "val"

# Placeholders — real values confirmed in Phase 1a once the ArmorIQ platform
# identities exist. A requester can never approve their own request, so these
# must resolve to two distinct emails with the approver ranked higher.
AGENT_EMAIL = os.environ.get("AGENT_EMAIL", "agent-operator@example.com")
APPROVER_EMAIL = os.environ.get("APPROVER_EMAIL", "approver@example.com")

VERDICTS = ("allowed", "blocked", "held", "approved", "executed")
