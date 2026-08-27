<<<<<<< HEAD
# Smart Cart Recovery Agent

**Track:** AI Growth & Agentic Commerce — Razorpay AI Builder Internship 2026

An agentic system that watches abandoned e-commerce carts, decides **which ones are worth chasing first**, and **auto-writes a personalized recovery message** with a discount that scales to how likely (and how valuable) the recovery is — instead of blasting every abandoned cart with the same generic "10% off" email.

---

## What problem does this solve?

Online stores lose a large share of revenue to cart abandonment. Most recovery tools send the *same* templated email to *every* customer after a fixed delay. That wastes discount margin on customers who would have converted anyway, and under-incentivizes high-value carts that are actually at risk of being lost.

This agent instead:
1. **Scores** every abandoned cart on cart value, item count, customer loyalty, and how long it's been idle.
2. **Decides** a priority tier (`High` / `Medium` / `Low`) and a matching discount depth (15% / 10% / 5%).
3. **Generates** a personalized recovery message in the right tone of urgency for that tier.
4. Surfaces everything on a live dashboard so a growth/ops team can act on the highest-priority carts first.

This is the core loop of "agentic commerce": perceive (cart state) → decide (scoring engine) → act (generate + surface a recovery message) — without a human writing each message by hand.

---

## Tech stack

- **Backend:** Python 3, Flask
- **Database:** SQLite (zero-config, file-based — swappable for Postgres in production)
- **Frontend:** Server-rendered Jinja2 templates, hand-written CSS (no framework)
- **Decision engine:** Rule-based weighted scoring (see `score_recovery_priority` in `app.py`)
- **Message generation:** Rule-based NLG (see `generate_recovery_message` in `app.py`), structured so the same function signature can be swapped for a live LLM call (e.g. the Anthropic API) — see "Swapping in a real LLM" below.

---

## Project structure

```
smart-cart-recovery-agent/
├── app.py                  # Flask app: routes, scoring engine, message generator
├── requirements.txt
├── templates/
│   ├── base.html            # shared layout + design system
│   ├── dashboard.html       # main recovery queue view
│   └── add_cart.html        # form to log a new abandoned cart
└── cart_recovery.db         # created automatically on first run
```

---

## Running it locally

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000**.

On first load the dashboard will be empty — click **"Load sample data"** to seed 5 realistic abandoned carts, or use **"+ New Cart"** to add your own.

---

## How the scoring engine works

```
score =  min(cart_value / 500, 20)      # value signal, capped
       + items_count * 2                 # intent signal
       + 15 (if repeat customer)         # loyalty signal
       + min(idle_hours * 1.5, 15)       # urgency signal, capped

score >= 40  → High priority   → 15% discount
score >= 22  → Medium priority → 10% discount
else         → Low priority    → 5% discount
```

The caps on value and idle-time prevent one signal from dominating the score, so a very old, very cheap cart doesn't outrank a fresh, high-value one.

---

## Swapping in a real LLM

`generate_recovery_message()` is intentionally isolated from the rest of the pipeline. To connect it to a live model (e.g. Claude via the Anthropic API), replace the function body with an API call that receives the same inputs (`name`, `product`, `discount`, `priority`, `is_repeat`) and returns a string — no other code needs to change. This was kept rule-based for the demo so the project runs fully offline with no API key required.

---

## Build challenges & how they were solved

- **Avoiding a single flat discount for every cart:** an early version used one fixed discount. Replaced it with the weighted scoring engine above so discount depth reflects actual recovery value.
- **Keeping the demo runnable without external API keys:** message generation is rule-based rather than calling a live LLM, so the project works out of the box for anyone reviewing it, while staying structured to swap in a real model call later.
- **Idle-time calculation drift:** since `idle_hours` is computed live from `created_at`, priority scores update automatically as time passes, without needing a background job for the demo.

---

## Author

Rudra Soni
=======
# smart-cart-recovery-agent
>>>>>>> ec6b1d16f5d5f0f0a4b2000ce09e401dda0e7ff2
