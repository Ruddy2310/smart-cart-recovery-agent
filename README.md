# Cart Recovery Agent

**AI Revenue Recovery Infrastructure** — an agent that scores abandoned carts, decides the right channel and offer, executes a bounded recovery workflow, and audits every decision it makes.

Built for the Razorpay AI Buildathon, Track 03 (AI Revenue Recovery) / Track 01 (AI Growth & Agentic Commerce).

---

## What it does

1. **Detects** abandoned carts (currently manual entry / seeded demo data; see *Production integration* below for how this becomes automatic).
2. **Scores** each cart on cart value, item count, repeat-customer status, and idle time to produce an intent tier (Low → Very High) and a recovery probability.
3. **Decides** the right channel (WhatsApp / Email / SMS) and discount depth per customer — not one flat offer for everyone.
4. **Explains** every recommendation in plain business language (`Why the agent chose this action`), not a black-box score.
5. **Executes**, within bounds: a hard cap of 3 contact attempts per cart, automatic escalation to a human agent for high-value carts that aren't converting, and a permanent opt-out/do-not-contact list that the agent will never violate.
6. **Logs** every action — sent message, suppression, escalation, opt-out, recovery — to an auditable AI Decision Log.
7. **Measures** its own impact: the `/simulation` page runs a batch of 50 synthetic carts through both a generic flat-outreach baseline and the agent's differentiated strategy, side by side, so the uplift is a measured number rather than a claim.

## Architecture

```
Flask (Python) app
 ├── app.py                  Scoring engine, decision engine, routes
 ├── templates/               Server-rendered UI (Jinja2)
 │    ├── base.html            Sidebar shell, topbar, toasts
 │    ├── dashboard.html        Overview + Recovery Queue + cart detail modal
 │    ├── decisions.html        AI Decision Log (audit trail)
 │    ├── analytics.html        Channel/offer/intent performance
 │    ├── campaigns.html        Recovery strategy configuration
 │    ├── customers.html        Aggregated customer view
 │    ├── simulation.html       Measured batch simulation (agent vs baseline)
 │    └── settings.html
 ├── api/index.py             Vercel serverless WSGI entrypoint
 └── vercel.json              Vercel Python runtime config
```

- **Database:** SQLite. Two tables — `carts` (state + contact attempts + opt-out flag) and `decisions` (append-only audit log: timestamp, customer, decision, reason, expected impact, outcome).
- **Deployment:** Vercel, via `@vercel/python`. Because Vercel's filesystem is read-only outside `/tmp`, the DB path switches to `/tmp` in that environment — meaning data in the hosted demo resets between deployments/cold starts. This is fine for a demo; see below for the production fix.

## Decision engine (how scoring actually works)

```
score = min(cart_value / 500, 20)       # value signal
      + items_count * 2                  # intent signal
      + (15 if repeat_customer else 0)    # loyalty signal
      + min(idle_hours * 1.5, 15)         # urgency signal

priority  = High (score ≥ 40) / Medium (≥ 22) / Low
discount  = 15% / 10% / 5%          respectively
channel   = WhatsApp / Email / SMS  respectively
probability = weighted function of score, repeat status, and idle time
```

This is intentionally a transparent, rule-based model rather than an opaque ML model — every number the agent shows can be traced back to a cause, which is what the "why the agent chose this action" panel is built to demonstrate.

## Compliance & stopping rules

- **Max 3 contact attempts** per cart. On the 3rd unsuccessful attempt, the agent stops and logs an "Escalated" decision instead of retrying indefinitely.
- **Automatic escalation** for high-priority carts still unconverted after 2 attempts, so a human takes over on high-stakes cases rather than the agent looping forever.
- **Do-not-contact / opt-out** is permanent and checked before every send — once set, no code path in the app will message that customer again.
- Every one of the above is logged to the Decision Log with an `outcome` (`Pending` / `Escalated` / `Suppressed` / `Recovered`), so the whole history is auditable.

## Production integration plan (not yet wired — by design, for a hackathon build)

This demo uses manually entered / seeded cart data so it can be judged without a live store. In production, the detection step would be:

1. **Checkout Drop-off Recovery** — subscribe to Razorpay Checkout's client-side events (`checkout.opened`, `checkout.failed`, no `payment.captured` within N minutes) via webhooks, and create a `carts` row automatically instead of the `/add` form.
2. **Payment degradation** — listen to Razorpay's `payment.failed` webhook to distinguish "abandoned before paying" from "tried to pay and failed" (a different, often higher-intent, recovery case), and adjust the recommended action accordingly (e.g., "retry payment" vs "reconsider purchase").
3. **Recovery execution** — replace the current rule-based message text with real WhatsApp Business API / email provider calls, gated behind the same `MAX_CONTACT_ATTEMPTS` and opt-out checks already implemented.
4. **Outcome feedback loop** — when Razorpay reports a `payment.captured` event for a previously-abandoned cart, mark it recovered automatically (today this is a manual "Mark recovered" button) and feed the actual conversion back into the scoring weights over time.

## Batch simulation methodology

`/simulation` generates 50 synthetic carts with randomized value, item count, repeat status, and idle time (seeded, so results are reproducible via `?seed=`). Each cart is run through two independent stochastic trials:

- **Baseline:** a fixed 19% recovery probability for every cart, representing a generic "same email to everyone" strategy with no segmentation.
- **Agent:** the per-cart probability computed by the scoring engine above.

Both scenarios draw from the same random cart batch, so the only variable is the strategy. This is clearly a simulation on synthetic data — not a claim about real production conversion — but it demonstrates *how* the strategy would be measured once real outcome data exists.

## Local development

```bash
pip install -r requirements.txt
python app.py
# visit http://localhost:5000, then /seed to load demo data
```

## Tech stack

Python, Flask, SQLite, vanilla HTML/CSS/JS (no frontend framework), deployed serverlessly on Vercel.

## Author

Rudra Soni
