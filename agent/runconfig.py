"""One run's configuration — set by the judge on the panel, carried end to end.

v1 shipped `--force-violation N`, which made the violation something the demo
*selected*. v2 replaces that judge-facing path with this: Bank A says what the
agent is **authorized** to do, Bank B says what the **world** looks like, and
whatever the agent then reaches for outside its authorization is the violation.
Emergent, not chosen.

`--force-violation` stays in agent/main.py — it is the deterministic recording
path and the emergency live path, not the judge-facing one.
"""

import json
from dataclasses import asdict, dataclass, field

# Canonical order. The signed plan is always assembled in this sequence, and
# agent/plan.py's PLAN_STEPS is the source of each step's params.
PLAN_ACTIONS = ("get_dataset_card", "read_split", "launch_run", "read_metrics", "promote_model")

# The four reads the pipeline cannot run without. The panel renders these as
# locked-on switches; the backend keeps the list so it can validate rather than
# trust the client. Unlocking one is allowed — it produces a clean block, not a
# crash (see docs/v2-plan.md 4.1).
LOCKED_ACTIONS = ("get_dataset_card", "read_split", "launch_run", "read_metrics")

# Params that carry authority rather than data. A call whose value for one of
# these is not present in the signed plan is an authority escalation and routes
# through a real ArmorIQ delegation request. Kept as a declared concept instead
# of an `if stage == "production"` so the mechanism generalises — and so the
# action name never has to change, which CLAUDE.md forbids.
AUTHORITY_PARAMS = ("stage",)

MODEL_RESULTS = ("clears", "narrow", "fails")
CARDS = ("clean", "poisoned", "custom")
CARD_TEXT_MAX_LEN = 4000  # generous for a hand-typed card; bounds LLM context cost


@dataclass
class RunConfig:
    # Bank A — authority
    authorized: list = field(default_factory=lambda: list(PLAN_ACTIONS))
    promote_production: bool = False
    # Bank B — world
    model_result: str = "clears"
    card: str = "poisoned"
    hash_match: bool = True
    card_text: str = ""  # the judge's own words, used when card == "custom" 

    def __post_init__(self):
        self.authorized = [a for a in self.authorized if isinstance(a, str)]
        if self.model_result not in MODEL_RESULTS:
            raise ValueError(f"model_result must be one of {MODEL_RESULTS}, got {self.model_result!r}")
        if self.card not in CARDS:
            raise ValueError(f"card must be one of {CARDS}, got {self.card!r}")
        if len(self.card_text) > CARD_TEXT_MAX_LEN:
            raise ValueError(f"card_text is {len(self.card_text)} chars, max {CARD_TEXT_MAX_LEN}")
        if self.card == "custom" and not self.card_text.strip():
            raise ValueError("card is 'custom' but card_text is empty — write something for the agent to read")

    @property
    def plans_anything(self):
        """False only for the one input that produces genuinely nothing."""
        return bool(self.authorized) or self.promote_production

    def to_json(self):
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw):
        if not raw:
            return cls()
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
