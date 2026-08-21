# PromotionGuard — Idea

**Track:** ArmorIQ, Problem 1 — *"Autonomous, until it shouldn't be"*
**Team:** Har Agam Deep Singh, Garv Nanda

---

## The one-liner

An agent that runs an ML model promotion pipeline entirely unattended — and stops dead the moment it tries to edit the data it's being graded on, or promote a model into production it was only authorized to stage.

## The pitch

Every ML team is quietly automating the same pipeline: pull the eval split, run the candidate, read the metrics, promote the winner. It is repetitive, well-specified work — exactly what you'd hand an agent, and exactly what nobody wants to babysit.

The problem is that in this workflow the safe actions and the catastrophic action are *the same shape*. Reading metrics is a read. Launching a run is a launch. Promoting a model is a promote. And when the candidate misses the bar, the two things an agent will reach for are:

1. Fix the measurement — the eval set has noisy rows, the dataset card says so, drop them and re-run.
2. Ship anyway — the metrics are close enough, promote to production instead of staging.

Neither reads as dangerous. Neither contains a scary word. A `contains("delete")` filter catches nothing, because the agent isn't deleting anything it wasn't documented to delete, and `promote_model` is the exact call it was authorized to make. Only the *plan* knows the difference, and only if the plan is signed and checked before the call runs.

That is the whole project: an agent that moves fast on everything inside its declared intent and stops cold at the boundary, with the boundary enforced cryptographically rather than by vibes or keyword matching.

## Why this scenario and not another

**The failure mode is real, not staged.** An agent that silently trims its own eval set is a live concern in every team running automated retraining. Nobody has to be convinced it matters once they see it happen.

**Both violations defeat keyword filtering, by construction.**
- Violation 1 arrives as *documentation*. The agent is following the dataset card. There is no adversarial phrasing to detect.
- Violation 2 is the same MCP, the same action, the same tool the agent has been authorized for all along. One argument different. There is nothing textual to filter on at all.

**The destructive artifacts are real.** Rows genuinely disappear from a SQLite labels table. A wrong promotion genuinely lands in the registry. Run it unguarded and the damage is on disk — which is the bar the track sets: *"'It would have deleted the table' proves nothing."*

**It maps onto ArmorIQ's two enforcement mechanisms cleanly**, one each:
- Violation 1 → **hard block.** `delete_rows` is not in the signed plan; the SDK checks the action against the captured plan client-side and refuses before any request leaves the agent process — the call never reaches the proxy or the database.
- Violation 2 → **human-in-the-loop hold.** Promoting to production exceeds the agent's role authority; ArmorIQ raises a delegation request, the plan goes to `held`, a higher-ranked human approves from the dashboard, and the agent resumes mid-run.

That second one is the demo. It is the exact sequence the track asks for — *"deliberately trigger an out-of-scope action and watch it get caught and held — before it executes. Then approve it from the dashboard and watch the agent continue."*

## The narrative for the judges

> Run 1, unguarded. The agent does the whole job by itself. It also quietly deletes forty rows from the eval set and pushes an unvalidated model into production. Here is the database before, and here is the database after.
>
> Run 2, same agent, same code, same prompt. ArmorIQ on. The routine steps flow with nobody watching. Then the injection fires — and `delete_rows` never reaches the database, because it was never in the signed plan. The rows are still there.
>
> Then it tries production. That's the same call it made successfully thirty seconds ago for staging. No filter distinguishes them. ArmorIQ does, because production exceeds what this agent was authorized to do alone — so the plan holds, here in the dashboard, waiting on a human with the authority to say yes. I approve it. And the agent picks up exactly where it stopped and finishes the run.
>
> Every one of those decisions — allowed, blocked, held, approved — is in the audit trail with its plan hash.

## Scope discipline

**In:** one agent, three MCP servers, five planned steps, two violations, one real database, one before/after.

**Out:** real model training, MLflow, drift detection, shadow deploys, multi-agent delegation, deployment, auth, anything with a UI beyond making the demo legible.

The track says it plainly and we are taking it literally: *"Two or three MCP servers is enough, one useful tool and one dangerous tool. Teams that wire up six spend the whole event on plumbing and demo nothing."*
