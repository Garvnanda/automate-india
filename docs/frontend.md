# PromotionGuard — Frontend Spec

Everything needed to rebuild `panel/index.html` exactly as it stands. Design language, element
inventory, every piece of logic, and the backend contract it depends on.

**One file, no build step, no framework, no dependencies.** The entire frontend is a single
`panel/index.html` — inline `<style>`, inline `<script>`, one IIFE. The only external request is a
Google Fonts stylesheet. This is deliberate: a judge clones the repo and runs one command.

---

## 1. What it is

A skeuomorphic **instrument console** — brushed metal, recessed modules, a dual-trace oscilloscope,
needle gauges, brass toggle switches, annunciator lamps and a key dial. It is the demo surface for
the whole project: you flip a switch, pick a scenario, and watch a real agent run against a real
database through the real ArmorIQ proxy.

### Two rules the design must not break

1. **Nothing on the panel is fake.** Every trace pulse is a real line `agent.main` printed, every
   gauge reading is live SQLite, every lamp reflects a real verdict. There is no scripted
   choreography, no demo timeline, no placeholder data. If a thing cannot be shown honestly it is
   not shown.
2. **No prose on the panel.** All explanation lives in hover-only floating cards. The instrument
   itself stays clean — labels are terse mono uppercase, and anything longer than a label is a
   tooltip.

Two consequences that look like bugs but are correct:

- **Only one scope lane ever animates.** Unguarded and guarded share one SQLite database, so they
  genuinely cannot run at the same time. The idle lane dims and holds its last real result.
- **The key dial is an indicator, not a button.** Approval only ever happens on ArmorIQ's own
  dashboard, by a human with a higher-ranked role. The panel watches; it never approves.

---

## 2. Backend contract

The frontend is a pure consumer of three endpoints served by `panel/server.py` (stdlib
`http.server`, no framework).

### `GET /api/state`

```json
{
  "val_rows": 100,
  "promotions": [{"model_hash": "cand-v7-8f3a2b", "stage": "staging", "promoted_at": "..."}],
  "infra": {"state": "ready", "message": "tunneled and registered with ArmorIQ", "owned": true}
}
```

`infra.state` ∈ `off` | `starting` | `ready` | `error`.

### `POST /api/reset`

Reseeds the database. Returns `{"seeded": 200, ...same shape as /api/state}`.

### `GET /api/run?mode=<guarded|unguarded>&violation=<0|1|2>`

Server-Sent Events. The server reseeds, spawns `python -u -m agent.main --<mode>
[--force-violation N]`, and streams the subprocess's stdout **one line per `data:` frame**. Frame
kinds, in the order the frontend must test for them:

| Frame | Meaning |
|---|---|
| JSON with `verdict` | one tool call — the primary event |
| JSON with `__final_state__` | authoritative end-of-run DB state + `exit_code` |
| `__END__` | stream over, close the EventSource |
| `run_id=...` | run started (ignored) |
| `BLOCKED: ...` | the agent aborted on a block |
| `NOT APPROVED: ...` | hold timed out or was rejected |
| `ERROR: ...` | session not ready, surfaced verbatim |
| `done — N tool calls, ...` | clean finish |
| `agent final message: ...` | the LLM's closing text |

### The verdict line — the load-bearing schema

Fixed in `agent/logging.py`. **Do not change without updating the panel.**

```json
{"ts": "...", "mode": "guarded", "step": 4, "action": "promote_model",
 "mcp": "registry-mcp", "params": {"stage": "production"},
 "verdict": "held", "reason": "..."}
```

`verdict` ∈ `allowed` | `blocked` | `held` | `approved` | `executed`.

> **Critical, non-obvious:** the agent emits **no `allowed` and no "starting" event**. A step is
> only logged once it already has an outcome. Every progress affordance in the UI is therefore
> *inferred*, never received. See §6.4.

---

## 3. Design language

### Palette (CSS custom properties on `:root`)

| Token | Value | Use |
|---|---|---|
| `--room` | `#0b0a09` | page background, the "dark room" the panel sits in |
| `--panel-lo` / `--panel` / `--panel-hi` | `#17130f` / `#221d18` / `#2e2820` | metal gradient stops |
| `--edge-hi` | `rgba(255,235,205,.09)` | top bevel highlight |
| `--ink` | `#ece3d4` | warm off-white text |
| `--dim` | `#7c7263` | secondary text |
| `--brass` | `#c9a227` | the wordmark, tooltip borders, active switch caps |
| `--amber` | `#f2a81d` | HOLD state |
| `--red` | `#e2412c` | BLOCK / danger / unguarded damage |
| `--green` | `#5ac476` | OK / guarded / enforced |
| `--trace-a` | `#f0703a` | unguarded lane (orange) |
| `--trace-b` | `#5ac476` | guarded lane (green) |

**Colour has fixed meaning.** Orange = unguarded lane, always. Green = guarded/success. Amber =
held/waiting. Red = blocked or destroyed. Brass = chrome/identity, never status.

### Type

- `--cond`: **Barlow Condensed** — the wordmark and all tooltip body text.
- `--mono`: **JetBrains Mono** — every label, readout, action name and log line.

Both from Google Fonts with local fallbacks (`'Arial Narrow', system-ui` / `ui-monospace, Menlo,
Consolas`). Labels are uppercase, 8–9.5px, letter-spacing `.11em`–`.18em`. Small and wide is the
whole instrument-label idiom — do not scale them up.

### Materials — how the metal is faked

Three techniques, reused everywhere:

**Brushed panel face** — a 1px repeating linear gradient at 93° over a 163° base gradient:

```css
background:
  repeating-linear-gradient(93deg, rgba(255,240,215,.016) 0 1px, transparent 1px 4px),
  linear-gradient(163deg, var(--panel-hi) 0%, var(--panel) 34%, var(--panel-lo) 100%);
```

**Recessed module** (every cell, lamp, plan step) — inset light on top, inset dark at the bottom,
plus a 1px outer highlight to lift it off the face:

```css
box-shadow: inset 0 1px 0 rgba(255,235,205,.055),
            inset 0 -2px 5px rgba(0,0,0,.6),
            0 1px 0 rgba(255,235,205,.035);
```

**Lit lamp** — an off-state radial gradient swapped for a hot one plus an outer glow. The colour is
injected per-lamp through a `--c` variable so one rule serves all lamps:

```css
.lamp.on i{
  background: radial-gradient(circle at 34% 30%, #fff3d2, var(--c) 58%,
              color-mix(in srgb, var(--c) 55%, #000) 100%);
  box-shadow: 0 0 14px 2px color-mix(in srgb, var(--c) 65%, transparent),
              inset 0 1px 2px rgba(255,255,255,.55);
}
```

Four `.screw` pseudo-elements sit at the panel corners, each rotated a different arbitrary angle
(52°, 24°, 71°, 0°) so they don't read as a repeated sprite.

### Motion

Everything honours `prefers-reduced-motion`. A global override collapses all transitions and
animations to `.01ms`, and the JS reads `matchMedia('(prefers-reduced-motion: reduce)')` into `RM`
to disable trace jitter and snap the gauge needles straight to target.

---

## 4. Layout

Single column, `.panel` at `min(1200px, 97vw)`, vertically centred, gap `clamp(9px,1.2vh,14px)`:

```
┌ .panel ────────────────────────────────────────────────────┐
│ .bezel      wordmark · session lamp · 3 annunciator lamps   │
├────────────────────────────────────────────────────────────┤
│ .scope      dual-trace canvas + glass overlay + lane tags   │
├────────────────────────────────────────────────────────────┤
│ .planbar    label │ 6 × .pstep  (5 plan steps + reserved)   │
├────────────────────────────────────────────────────────────┤
│ .bay        gaugeA (1fr) │ gaugeB (1fr) │ keycell (1.12fr)  │
├────────────────────────────────────────────────────────────┤
│ .console    scrolling raw verdict log                       │
├────────────────────────────────────────────────────────────┤
│ .controls   4 toggles │ reset + plate                       │
└────────────────────────────────────────────────────────────┘
                      .tip — fixed, follows cursor
```

Only responsive break: below 760px `.bay` becomes 2 columns and `.keycell` spans full width.

---

## 5. Element inventory

### 5.1 Bezel

- `.mark` — `PROMOTIONGUARD`, brass, `letter-spacing:.34em`, with a dual text-shadow (dark below,
  light above) to look engraved. `data-tip="mark"`.
- `.sub` — `MODEL PG-1 · CSRG-IAP INTENT ENFORCEMENT`.
- `.sess` — the enforcement-session lamp + `SESSION READY` / `STARTING` / `OFF` / `FAILED`.
  `data-tip="sess"`.
- `.annun` — three `.lamp`s: `ARMED` (green, run in progress), `HOLD` (amber, blinking),
  `BLOCK` (red). Each carries its own `data-tip`.

### 5.2 Scope

A `<canvas>` filling a recessed well of `clamp(180px,30vh,270px)`, with:
- `.glass` — a non-interactive overlay: a 103° diagonal sheen plus a top-left radial reflection.
- `.lane-tag.a` / `.lane-tag.b` — `UNGUARDED` (top) and `GUARDED · ARMORIQ` (bottom). The inactive
  one gets `.idle` (opacity `.35`).
- `.ceil-tag` — `PLAN CEILING`, turns red when the ceiling is hit.

### 5.3 Plan strip — the concept made visible

`.planbar` = a fixed left `.planlabel` + `.psteps`, a **6-column grid**.

- Columns 1–5 are the five signed steps, built in JS from a `PLAN` array that mirrors
  `agent/plan.py`. Each is `<i>` (lamp) + `<span class="a">` (action name in mono).
- **Column 6 is permanently reserved** for `delete_rows` and rendered at `opacity:0`. It fades in
  rather than being inserted, so **the layout never shifts** when the violation fires. This is
  intentional — a reflow mid-demo is a tell.
- `.planlabel` flips with the mode:
  - unguarded → `DECLARED PLAN` / `NOT ENFORCED`, label red (`.planbar.open`)
  - guarded → `SIGNED PLAN` / `ENFORCED BY ARMORIQ`, label green (`.planbar.enforced`)

Step state classes and their lamp colours (`--c`):

| Class | Colour | Meaning |
|---|---|---|
| *(none)* | dark | not reached |
| `.run` | `#e8c463` blinking | in flight (inferred) |
| `.done` | green | executed |
| `.held` | amber | held, or approved-and-executed under enforcement |
| `.bad` | red | blocked, or executed-unauthorized with enforcement off |

`.held` and `.bad` also get a 1px inset ring in their own colour.

### 5.4 Bay

- **`.cellA`** — orange needle gauge, big `VAL ROWS` readout, `PROD PROMOTIONS` sub-readout. The
  unguarded world state.
- **`.cellB`** — identical in green. The guarded world state. Side by side, these two are the entire
  before/after.
- The inactive cell gets `.idle` (opacity `.55`).
- **`.keycell`** — a `.keyhole` disc containing a `.key` (head/bar/bit built from three spans), a
  `.keytimer`, `.keylabel`, `.keysub`. States:
  - idle: dull, `NO PENDING APPROVAL`
  - `.armed`: amber outer glow, key turns brass, timer fades in and counts
  - `.turned`: key rotates 92° over `.55s cubic-bezier(.34,1.4,.4,1)` — the approval beat

### 5.5 Console

Raw verdict log, mono 9.5px, `max-height:68px`, auto-scrolled, capped at 40 lines
(oldest removed). Classes `.ok` / `.warn` / `.err`. This is deliberately the unglamorous raw
truth — it is what makes the pretty parts credible.

### 5.6 Controls

Four `.tog` brass toggles: `GUARDED` (green when on), then `HAPPY` / `VIOL-1` / `VIOL-2`
(brass when on). The lever is a rounded bar with a `::after` ball cap, rotated/translated on
`aria-pressed` with a springy `cubic-bezier(.3,1.5,.5,1)`.

`.reset` is a physical push-button: it translates 2px down and swaps to an inset shadow on
`:active`. `.plate` on the right shows the model hash and a live status line.

### 5.7 Tooltip layer

A single `.tip` div, `position:fixed`, brass-bordered, `pointer-events:none`, that follows the
cursor. Never more than one exists.

---

## 6. Logic

### 6.1 Scope simulation

Two lane objects, `A` (unguarded) and `B` (guarded), each:

```js
{ buf: Array(620).fill(0), base: 0, pulses: [], frozen: false, ceiling: 0, clipGlow: 0 }
```

Every animation frame, each lane pushes one new sample and shifts the buffer:

```js
let v = L.base;
if (!RM) v += (Math.random() - .5) * 1.6;          // idle jitter
for (const p of L.pulses){
  if (!(L.frozen && p.hold && p.age >= p.peak)) p.age += 1;   // a held pulse stops aging
  const s = p.mag * Math.exp(-p.age / p.decay) * Math.sin(p.age * p.freq);
  if (s > 0) v += s;                                // positive half only
}
L.pulses = L.pulses.filter(p => p.age < p.decay * 4.2 || (p.hold && L.frozen));
if (L.ceiling && v > L.ceiling){ v = L.ceiling; L.clipGlow = 1; }
```

A **decaying sine** is what makes a pulse read as a seismograph event rather than a spike.

`fire(L, mag, opts)` pushes a pulse; defaults `decay:15, freq:.19, peak:8`. Magnitudes in use:
normal call `24`, blocked `44` then a second `60` with `decay:26`, held `30` with `hold:true,
decay:900`.

**Freezing** is the trick that makes a hold legible: when `frozen` is set, a `hold` pulse stops
aging once it reaches its peak, so the trace visibly *stops mid-swing* and stays there until the
verdict resolves.

`ceiling` clamps the guarded lane after a block and lights the `PLAN CEILING` tag red;
`clipGlow` decays at `*= .94` per frame to fade the flash.

`markers` are labelled vertical rules that scroll left with the trace (`m.idx--` each frame,
dropped past `-70`).

Drawing: grid (10 × 8), midline, then each lane at `cy = H*.27` / `H*.74`. The active lane draws at
full alpha with `shadowBlur`; the idle one at `.32` with no glow. A dot marks the newest sample at
the right edge.

### 6.2 Gauges

Canvas, 380×220, arc from `A0 = π*1.06` to `A1 = π*1.94`, redline over the first 30% of the sweep,
11 ticks (every 5th major), `0` and `100` numerals.

The needle is a **critically-ish damped spring**, not a transition — that overshoot-and-settle is
what sells it as a physical meter:

```js
const f = (st.target - st.v) * .1;
st.vel = (st.vel + f) * .84;     // .84 = damping
st.v  += st.vel;
```

Each gauge returns its `st` object; the app only ever writes `st.target`. Under reduced motion,
`v` snaps to `target`.

### 6.3 Application state

```js
let guardedMode = false;   // which lane/mode is live
let running     = false;   // a run is in flight → controls disabled
let infraReady  = false;   // guarded is unlocked
let infraMsg    = '';      // last message from the bring-up
let activeLaneKey = null;  // 'A' | 'B' | null — which lane draws bright
```

### 6.4 Plan strip state machine

Because there is no "starting" event (§2), progress is inferred:

```js
function advanceP(i){                       // called after a step completes
  const nx = stepEls[i + 1];
  if (nx && nx.className === 'pstep') setPStep(i + 1, 'run');
}
```

`runScenario` sets step 0 to `run` at launch; every `executed` verdict lights its own step and
advances the next. **Never invent log events to make the UI prettier** — adapt the UI to the real
stream.

Verdict → strip mapping:

| Verdict | Action in plan? | Result |
|---|---|---|
| `executed` | yes, `stage` ≠ production | `.done`, advance next |
| `executed` | yes, `stage` = production | guarded → `.held`, unguarded → `.bad` |
| `held` / `approved` | yes | `.held` |
| `blocked` | yes | `.bad` |
| *any* | **no** (`delete_rows`) | reserved slot → `.on .bad`, `dataset.state = verdict` |

That last row is the whole point: membership of the signed plan, not the name of the call, is what
decides.

### 6.5 Hold timer

`startHoldTimer()` on `held`, `stopHoldTimer()` on `approved`, on `NOT APPROVED:`, on reset and at
the start of every run. Ticks every 500ms, renders `M:SS`. Visibility is pure CSS — the timer is
`opacity:0` until `.keycell.armed`.

### 6.6 Enforcement-session gating

`applyInfra(infra)` runs on every `/api/state` response:

- writes `.sess` class + label
- sets `infraReady`
- if not ready and the user is somehow in guarded mode, forces back to unguarded
- **while `starting`, schedules `refreshState()` again in 2s** — that self-poll is the only polling
  in the app

The `GUARDED` switch refuses to arm when `!infraReady` and writes the reason to the status plate.

### 6.7 Tooltip engine

One delegated `mousemove` listener on `document`:

```js
const t = e.target.closest('[data-tip]');
if (t !== tipFor){                       // entered a new target
  tipFor = t;
  const v = t && TIPS[t.dataset.tip];
  if (v){ tipEl.innerHTML = typeof v === 'function' ? v() : v; tipEl.classList.add('on'); ... }
  else tipEl.classList.remove('on');
} else if (t) moveTip(e.clientX, e.clientY);   // same target → just follow
```

Positioning offsets +18px from the cursor and **flips to the opposite side** when it would overflow
the viewport, clamped to ≥8px.

`TIPS` values are **either strings or functions**. Functions are re-evaluated on every hover, which
is how the copy reacts to live state:

- `intruder` — "the call never left the agent" (blocked) vs "forty rows are gone" (executed) vs the
  neutral pre-run text
- `guard` — on / off / **locked, with the live bring-up message**
- `planbar` — signed-and-enforced vs declared-and-unchecked
- `sess` — embeds `infraMsg`

There are 20 entries: `mark`, `sess`, `scope`, `planbar`, `step0`–`step4`, `intruder`, `cellA`,
`cellB`, `key`, `armed`, `hold`, `block`, `guard`, `run0`–`run2`, `reset`, `console`.

Each tooltip opens with a `<b>` line used as a small brass mono heading, then Barlow body text.

### 6.8 Run lifecycle

```
click scenario
  → disable all controls, pick lane by guardedMode, clear lane + plan strip
  → step 0 = run, ARMED lamp on, stop/zero hold timer
  → EventSource('/api/run?mode=…&violation=…')
      each frame → handleEvent: fire pulse, drop marker, log line,
                                updatePlan, lamps, key dial, gauges
  → '__END__' → close, re-enable controls, ARMED off
  onerror → close, re-enable, 'CONNECTION LOST'
```

`__final_state__` is applied verbatim as the authoritative end state — the frontend never computes
row counts itself.

---

## 7. Rebuild checklist

1. HTML skeleton + `:root` tokens + Google Fonts link.
2. `.panel` shell: brushed gradient, bevel shadows, four rotated screws.
3. Bezel: wordmark, sub, session lamp, three annunciators (one `.lamp` rule, per-lamp `--c`).
4. Scope well + `.glass` + lane tags; canvas sized by `ResizeObserver` with DPR capped at 2.
5. Scope engine: lane objects, `push`, `fire`, `drawLane`, `frame` on `requestAnimationFrame`.
6. Gauges: arc, ticks, redline, spring needle; return the `st` object.
7. Bay cells and the key dial (keyhole, key spans, timer, labels).
8. Console logger with the 40-line cap.
9. Controls: toggles, reset, plate.
10. Plan strip: `PLAN` array → 5 steps + reserved intruder, `setPStep` / `resetPSteps` /
    `advanceP` / `updatePlan` / `syncPlanbar`.
11. `TIPS` map + the delegated tooltip engine.
12. Backend wiring: `refreshState`, `applyState`, `applyInfra`, `runScenario`, `handleEvent`,
    reset handler.
13. Reduced-motion override last.

---

## 8. Gotchas

- **Python buffers stdout when it isn't a TTY.** Without `python -u` on the subprocess (and
  `sys.stdout.reconfigure(line_buffering=True)` in `agent/main.py`) the SSE stream delivers nothing
  until the run ends and the panel looks hung. This bit once already.
- **`color-mix()` is required** for the lamp glows. Any browser without it loses the glow only —
  the lamps still change colour.
- **The 6th grid column must exist from first paint.** Creating it on demand causes a reflow at the
  exact moment the demo needs to be steady.
- **Canvas needs DPR scaling** (`Math.min(devicePixelRatio, 2)`) or the trace is soft on retina.
- **Guarded runs need `.session.json`.** The panel starts the tunnel itself and reports progress
  through `infra`; a stale session file is detected by probing the tunnel — a dead cloudflared quick
  tunnel still resolves and returns **HTTP 530** from Cloudflare's edge, so "any response = alive"
  is not a valid liveness check. Treat `>= 500` as dead.
- **Never let the panel offer an Approve button.** It would be a lie about where authority lives,
  and it is the one thing in this project that would actually mislead a judge.
