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

# AGENT_EMAIL never needs to be a registered platform member — GET
# /delegation/my-role resolves any unregistered email to role=null, limit=0
# (least-privileged) automatically, confirmed live. APPROVER_EMAIL must be a
# real, higher-ranked member (org_admin) so it can approve from the dashboard
# and can never approve its own request.
AGENT_EMAIL = os.environ.get("AGENT_EMAIL", "agent-operator@example.com")
APPROVER_EMAIL = os.environ.get("APPROVER_EMAIL", "approver@example.com")
AGENT_ID = "promotionguard-agent"

VERDICTS = ("allowed", "blocked", "held", "approved", "executed")

# Violation 2's hold: no ArmorIQ policy mechanism can distinguish
# promote_model(stage="production") from stage="staging" (verified live, see
# done.md) — the agent's own code creates a real delegation request via the
# SDK's trust primitives when it detects stage=="production", and polls for
# the higher-ranked approver's decision.
DELEGATION_POLL_INTERVAL_SECONDS = 3.0
DELEGATION_TIMEOUT_SECONDS = 600

# MCP servers, run over HTTP so the ArmorIQ proxy can reach them (Phase 1 Gate 1).
MCP_HOST = "127.0.0.1"
DATASET_MCP_PORT = 8001
JOBS_MCP_PORT = 8002
REGISTRY_MCP_PORT = 8003
DATASET_MCP_URL = f"http://{MCP_HOST}:{DATASET_MCP_PORT}/mcp"
JOBS_MCP_URL = f"http://{MCP_HOST}:{JOBS_MCP_PORT}/mcp"
REGISTRY_MCP_URL = f"http://{MCP_HOST}:{REGISTRY_MCP_PORT}/mcp"

# OpenRouter — LLM tool-calling loop (Phase 3). Model id picked live at first
# run since the free-tier roster shifts; override here once locked in.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "")
