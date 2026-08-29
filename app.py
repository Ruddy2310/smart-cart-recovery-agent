"""
Cart Recovery Agent
--------------------------
AI revenue recovery infrastructure for e-commerce: watches abandoned carts,
scores purchase intent, estimates recoverable revenue, and decides the best
channel + offer to win the order back -- then logs every decision it makes
so a revenue team can audit it.

Track: AI Growth & Agentic Commerce
Author: Rudra Soni
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from datetime import datetime, timedelta
import sqlite3
import os
import random
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-cart-recovery")

# Vercel's serverless filesystem is read-only except for /tmp.
# Locally this still writes next to app.py exactly like before.
if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/cart_recovery.db"
else:
    DB_PATH = os.path.join(BASE_DIR, "cart_recovery.db")


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS carts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_contact TEXT NOT NULL,
            product_name TEXT NOT NULL,
            cart_value REAL NOT NULL,
            items_count INTEGER NOT NULL,
            is_repeat_customer INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'abandoned',
            recovery_message TEXT,
            discount_offered INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cart_id INTEGER,
            customer_name TEXT NOT NULL,
            decision TEXT NOT NULL,
            reason TEXT NOT NULL,
            expected_impact REAL,
            outcome TEXT DEFAULT 'Pending',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


def log_decision(cart_id, customer_name, decision, reason, expected_impact, outcome="Pending", created_at=None):
    conn = get_db()
    conn.execute(
        """INSERT INTO decisions (cart_id, customer_name, decision, reason, expected_impact, outcome, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (cart_id, customer_name, decision, reason, expected_impact, outcome,
         created_at or datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Core "Agentic" logic
# ---------------------------------------------------------------------------
def calculate_idle_hours(created_at_str):
    created_at = datetime.fromisoformat(created_at_str)
    delta = datetime.now() - created_at
    return round(delta.total_seconds() / 3600, 2)


def format_idle(hours):
    total_minutes = round(hours * 60)
    if total_minutes < 60:
        return f"{max(total_minutes, 1)}m"
    h, m = divmod(total_minutes, 60)
    if h < 24:
        return f"{h}h {m}m" if m else f"{h}h"
    d, rh = divmod(h, 24)
    return f"{d}d {rh}h" if rh else f"{d}d"


def score_recovery_priority(cart_value, items_count, is_repeat, idle_hours):
    """
    Weighted scoring model -- the decision engine of the agent. Decides
    WHETHER and HOW MUCH discount to offer, instead of blindly offering
    the same discount to everyone.
    """
    score = 0
    score += min(cart_value / 500, 20)     # high value carts -> higher priority
    score += items_count * 2                # more items -> more intent
    score += 15 if is_repeat else 0         # loyal customers matter more
    score += min(idle_hours * 1.5, 15)      # older abandonment -> more urgency

    if score >= 40:
        priority, discount = "High", 15
    elif score >= 22:
        priority, discount = "Medium", 10
    else:
        priority, discount = "Low", 5

    return round(score, 1), priority, discount


def intent_label(score):
    """Finer-grained label shown in the UI (separate from the discount tier)."""
    if score >= 48:
        return "Very High"
    if score >= 33:
        return "High"
    if score >= 18:
        return "Medium"
    return "Low"


def recovery_probability(score, is_repeat, idle_hours):
    prob = min(94, max(6, score * 1.85))
    if is_repeat:
        prob += 6
    if idle_hours > 48:
        prob -= 12
    elif idle_hours < 2:
        prob += 4
    return int(round(max(4, min(96, prob))))


def recommended_channel(priority):
    return {"High": "WhatsApp", "Medium": "Email", "Low": "SMS"}[priority]


def recommended_action(priority, discount):
    channel = recommended_channel(priority)
    offer = f"{discount}% personalized offer" if discount else "no discount"
    return f"{channel} + {offer}"


def synthesize_signals(cart):
    """
    Deterministic 'customer signal' synthesis so a demo cart always shows
    the same device/location/session data on every page load, without
    needing extra DB columns for a hackathon-scale project.
    """
    seed_src = f"{cart['id']}-{cart['customer_name']}-{cart['created_at']}"
    seed = int(hashlib.md5(seed_src.encode()).hexdigest(), 16)
    rnd = random.Random(seed)

    devices = ["iPhone 15 Pro", "Samsung Galaxy S24", "MacBook Air M2",
               "OnePlus 12", "Windows Laptop", "iPad Air"]
    locations = ["Mumbai, MH", "Bengaluru, KA", "Ahmedabad, GJ", "Pune, MH",
                 "Delhi, NCR", "Hyderabad, TG", "Surat, GJ", "Jaipur, RJ"]
    stages = ["Viewed product", "Added to cart", "Started checkout",
              "Entered address", "Reached payment"]

    is_repeat = bool(cart["is_repeat_customer"])
    stage = rnd.choice(stages[2:]) if cart["cart_value"] > 3000 else rnd.choice(stages)

    return {
        "previous_purchases": rnd.randint(2, 11) if is_repeat else 0,
        "avg_order_value": round(rnd.uniform(1500, 6200), 0) if is_repeat else None,
        "last_purchase_days": rnd.randint(5, 140) if is_repeat else None,
        "device": rnd.choice(devices),
        "location": rnd.choice(locations),
        "session_minutes": round(rnd.uniform(1.5, 13.5), 1),
        "products_viewed": rnd.randint(2, 9),
        "checkout_stage": stage,
    }


def build_reasoning(cart, signals, priority, probability, idle_hours):
    parts = []
    parts.append(
        f"{cart['customer_name']} reached the \u201c{signals['checkout_stage'].lower()}\u201d stage "
        f"and spent {signals['session_minutes']} min viewing {signals['products_viewed']} products before leaving."
    )
    if cart["is_repeat_customer"]:
        parts.append(
            f"They've ordered {signals['previous_purchases']} times before at an average of "
            f"\u20b9{signals['avg_order_value']:.0f} per order, so this is a known, high-trust buyer."
        )
    if idle_hours > 24:
        parts.append(f"The cart has been idle for {format_idle(idle_hours)} \u2014 recovery odds drop the longer this sits.")
    else:
        parts.append(f"Idle for only {format_idle(idle_hours)}, still well inside the ideal recovery window.")
    parts.append(
        f"Similar {priority.lower()}-priority carts convert at roughly {probability}% when contacted "
        f"through the recommended channel within the next hour."
    )
    return " ".join(parts)


def enrich_cart(cart):
    idle_hours = calculate_idle_hours(cart["created_at"])
    score, priority, discount = score_recovery_priority(
        cart["cart_value"], cart["items_count"], cart["is_repeat_customer"], idle_hours
    )
    prob = recovery_probability(score, cart["is_repeat_customer"], idle_hours)
    signals = synthesize_signals(cart)
    reasoning = build_reasoning(cart, signals, priority, prob, idle_hours)
    return {
        **dict(cart),
        "idle_hours": idle_hours,
        "idle_label": format_idle(idle_hours),
        "score": score,
        "priority": priority,
        "intent": intent_label(score),
        "discount_calc": discount,
        "probability": prob,
        "estimated_recoverable": round(cart["cart_value"] * prob / 100, 0),
        "channel": recommended_channel(priority),
        "action_text": recommended_action(priority, discount),
        "signals": signals,
        "reasoning": reasoning,
    }


# ---------------------------------------------------------------------------
# Shared stats
# ---------------------------------------------------------------------------
def compute_stats(enriched):
    total_value = sum(c["cart_value"] for c in enriched)
    recovered_value = sum(c["cart_value"] for c in enriched if c["status"] == "recovered")
    abandoned = [c for c in enriched if c["status"] != "recovered"]
    recoverable_value = sum(c["estimated_recoverable"] for c in abandoned)
    recovered_count = len([c for c in enriched if c["status"] == "recovered"])
    high_intent = len([c for c in enriched if c["intent"] in ("High", "Very High")])
    recovery_rate = round((recovered_count / len(enriched)) * 100, 1) if enriched else 0.0
    avg_recovery_value = round(recovered_value / recovered_count, 0) if recovered_count else 0

    # Deterministic "vs last period" deltas for the demo -- derived from the
    # data itself so numbers stay internally consistent between reloads.
    seed = int(hashlib.md5(f"{len(enriched)}-{total_value}".encode()).hexdigest(), 16)
    rnd = random.Random(seed)

    return {
        "total_carts": len(enriched),
        "abandoned": len(abandoned),
        "recovered": recovered_count,
        "total_value": round(total_value, 2),
        "recovered_value": round(recovered_value, 2),
        "recoverable_value": round(recoverable_value, 2),
        "recovery_rate": recovery_rate,
        "recovery_rate_delta": round(rnd.uniform(2.0, 9.0), 1),
        "recoverable_delta": round(rnd.uniform(6.0, 22.0), 1),
        "high_intent": high_intent,
        "high_intent_delta": round(rnd.uniform(-4.0, 18.0), 1),
        "avg_recovery_value": avg_recovery_value,
        "avg_recovery_delta": round(rnd.uniform(-3.0, 11.0), 1),
    }


def format_inr(n):
    n = float(n)
    if n >= 100000:
        return f"\u20b9{n/100000:.2f}L"
    if n >= 1000:
        return f"\u20b9{n/1000:.1f}k"
    return f"\u20b9{n:.0f}"


app.jinja_env.filters["inr"] = format_inr


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    conn = get_db()
    carts = conn.execute("SELECT * FROM carts ORDER BY created_at DESC").fetchall()
    decisions = conn.execute(
        "SELECT * FROM decisions ORDER BY created_at DESC LIMIT 6"
    ).fetchall()
    conn.close()

    enriched = [enrich_cart(c) for c in carts]
    stats = compute_stats(enriched)

    queue = sorted(
        [c for c in enriched if c["status"] != "recovered"],
        key=lambda c: c["score"], reverse=True,
    )

    # 7-day at-risk vs recovered trend, bucketed from real idle-time data.
    buckets = [{"label": (datetime.now() - timedelta(days=d)).strftime("%a"),
                "at_risk": 0.0, "recovered": 0.0} for d in range(6, -1, -1)]
    for c in enriched:
        day_offset = min(6, int(c["idle_hours"] // 24))
        idx = 6 - day_offset
        if 0 <= idx < 7:
            if c["status"] == "recovered":
                buckets[idx]["recovered"] += c["cart_value"]
            else:
                buckets[idx]["at_risk"] += c["cart_value"]
    max_bucket = max([max(b["at_risk"], b["recovered"]) for b in buckets] + [1])

    return render_template(
        "dashboard.html", carts=enriched, queue=queue, stats=stats,
        decisions=decisions, buckets=buckets, max_bucket=max_bucket,
    )


@app.route("/add", methods=["GET", "POST"])
def add_cart():
    if request.method == "POST":
        conn = get_db()
        cur = conn.execute(
            """INSERT INTO carts
               (customer_name, customer_contact, product_name, cart_value,
                items_count, is_repeat_customer, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                request.form["customer_name"],
                request.form["customer_contact"],
                request.form["product_name"],
                float(request.form["cart_value"]),
                int(request.form["items_count"]),
                1 if request.form.get("is_repeat_customer") == "on" else 0,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        cart_id = cur.lastrowid
        conn.close()
        log_decision(cart_id, request.form["customer_name"], "Cart entered pipeline",
                     "New abandoned cart detected by the agent.",
                     float(request.form["cart_value"]), outcome="Pending")
        flash("Cart added to the recovery queue.", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_cart.html")


@app.route("/generate/<int:cart_id>", methods=["POST"])
def generate(cart_id):
    conn = get_db()
    cart = conn.execute("SELECT * FROM carts WHERE id = ?", (cart_id,)).fetchone()
    enriched = enrich_cart(cart)

    message = (
        f"Hi {cart['customer_name']}, we noticed you left {cart['product_name']} in your cart. "
        f"{'Your items are still saved, but stock is moving fast.' if enriched['priority']=='Medium' else 'Complete your purchase now before your discount expires.'} "
        f"Get {enriched['discount_calc']}% off with code SAVE{enriched['discount_calc']}."
    )

    conn.execute(
        "UPDATE carts SET recovery_message = ?, discount_offered = ? WHERE id = ?",
        (message, enriched["discount_calc"], cart_id),
    )
    conn.commit()
    conn.close()

    log_decision(cart_id, cart["customer_name"], f"Sent {enriched['action_text']}",
                 enriched["reasoning"], enriched["estimated_recoverable"], outcome="Pending")

    return jsonify({
        "message": message,
        "discount": enriched["discount_calc"],
        "priority": enriched["priority"],
        "score": enriched["score"],
        "probability": enriched["probability"],
    })


@app.route("/recover/<int:cart_id>", methods=["POST"])
def mark_recovered(cart_id):
    conn = get_db()
    cart = conn.execute("SELECT * FROM carts WHERE id = ?", (cart_id,)).fetchone()
    conn.execute("UPDATE carts SET status = 'recovered' WHERE id = ?", (cart_id,))
    conn.execute(
        "UPDATE decisions SET outcome = 'Recovered' WHERE cart_id = ? AND outcome = 'Pending'",
        (cart_id,),
    )
    conn.commit()
    conn.close()
    if cart:
        log_decision(cart_id, cart["customer_name"], "Cart recovered",
                     "Customer completed checkout after the recovery attempt.",
                     cart["cart_value"], outcome="Recovered")
    flash("Cart marked as recovered.", "success")
    return redirect(url_for("dashboard"))


@app.route("/delete/<int:cart_id>", methods=["POST"])
def delete_cart(cart_id):
    conn = get_db()
    conn.execute("DELETE FROM carts WHERE id = ?", (cart_id,))
    conn.execute("DELETE FROM decisions WHERE cart_id = ?", (cart_id,))
    conn.commit()
    conn.close()
    flash("Cart removed from the queue.", "info")
    return redirect(url_for("dashboard"))


@app.route("/decisions")
def decisions_log():
    conn = get_db()
    rows = conn.execute("SELECT * FROM decisions ORDER BY created_at DESC LIMIT 100").fetchall()
    conn.close()
    return render_template("decisions.html", decisions=rows)


@app.route("/customers")
def customers():
    conn = get_db()
    carts = conn.execute("SELECT * FROM carts ORDER BY created_at DESC").fetchall()
    conn.close()

    by_customer = {}
    for c in carts:
        key = (c["customer_name"], c["customer_contact"])
        entry = by_customer.setdefault(key, {
            "customer_name": c["customer_name"], "customer_contact": c["customer_contact"],
            "carts": 0, "total_value": 0.0, "recovered": 0, "is_repeat": bool(c["is_repeat_customer"]),
        })
        entry["carts"] += 1
        entry["total_value"] += c["cart_value"]
        if c["status"] == "recovered":
            entry["recovered"] += 1

    rows = sorted(by_customer.values(), key=lambda r: r["total_value"], reverse=True)
    return render_template("customers.html", customers=rows)


@app.route("/analytics")
def analytics():
    conn = get_db()
    carts = conn.execute("SELECT * FROM carts").fetchall()
    conn.close()
    enriched = [enrich_cart(c) for c in carts]
    stats = compute_stats(enriched)

    recovered = [c for c in enriched if c["status"] == "recovered"]
    channel_counts = {}
    offer_counts = {}
    intent_conversion = {"Very High": [0, 0], "High": [0, 0], "Medium": [0, 0], "Low": [0, 0]}
    for c in enriched:
        intent_conversion[c["intent"]][1] += 1
        if c["status"] == "recovered":
            intent_conversion[c["intent"]][0] += 1
    for c in recovered:
        channel_counts[c["channel"]] = channel_counts.get(c["channel"], 0) + 1
        key = f"{c['discount_offered']}%" if c["discount_offered"] else "No discount"
        offer_counts[key] = offer_counts.get(key, 0) + 1

    best_channel = max(channel_counts, key=channel_counts.get) if channel_counts else "\u2014"
    best_offer = max(offer_counts, key=offer_counts.get) if offer_counts else "\u2014"
    avg_idle_recovered = round(sum(c["idle_hours"] for c in recovered) / len(recovered), 1) if recovered else 0

    intent_rows = [
        {"label": k, "rate": round((v[0] / v[1]) * 100, 1) if v[1] else 0, "count": v[1]}
        for k, v in intent_conversion.items()
    ]

    return render_template(
        "analytics.html", stats=stats, best_channel=best_channel, best_offer=best_offer,
        avg_idle_recovered=avg_idle_recovered, intent_rows=intent_rows,
        channel_counts=channel_counts, offer_counts=offer_counts,
    )


@app.route("/campaigns")
def campaigns():
    return render_template("campaigns.html")


@app.route("/settings")
def settings():
    return render_template("settings.html")


@app.route("/seed")
def seed_demo_data():
    """Populates the DB with a realistic-looking abandoned-cart pipeline for demos."""
    conn = get_db()
    conn.execute("DELETE FROM carts")
    conn.execute("DELETE FROM decisions")

    demo = [
        ("Aarav Mehta", "+91 98200 11234", "Apple AirPods Pro 2", 24900, 1, 1, 42 / 60, "abandoned"),
        ("Diya Shah", "diya.shah@gmail.com", "Nike Air Max 90", 8290, 1, 0, 2, "abandoned"),
        ("Rohan Patel", "+91 90210 44567", "MacBook Sleeve + Stand", 12840, 2, 1, 18 / 60, "abandoned"),
        ("Ananya Desai", "ananya.desai@outlook.com", "Sony WH-1000XM5", 29990, 1, 0, 6, "abandoned"),
        ("Kabir Shah", "+91 99870 22341", "Samsung Galaxy Watch 6", 26999, 1, 1, 4, "abandoned"),
        ("Ishita Verma", "ishita.verma@gmail.com", "boAt Rockerz 550", 1799, 1, 0, 30, "abandoned"),
        ("Vivaan Joshi", "+91 91234 55667", "Fossil Gen 6 Smartwatch", 15990, 1, 1, 1.2, "recovered"),
        ("Meera Nair", "meera.nair@yahoo.com", "Levi's Denim Jacket", 3499, 1, 0, 50, "abandoned"),
        ("Aditya Rao", "+91 98765 11223", "JBL Flip 6 Speaker", 9499, 1, 0, 3.5, "abandoned"),
        ("Sanya Kapoor", "sanya.kapoor@gmail.com", "Titan Analog Watch", 4290, 1, 0, 14, "abandoned"),
        ("Arjun Malhotra", "+91 97865 33445", "Redmi Buds 5", 1299, 2, 1, 0.8, "recovered"),
        ("Riya Bhatt", "riya.bhatt@gmail.com", "Kindle Paperwhite", 13999, 1, 0, 20, "abandoned"),
        ("Karthik Iyer", "+91 90000 12121", "Puma Running Shoes", 4999, 1, 1, 7, "abandoned"),
        ("Neha Gupta", "neha.gupta@outlook.com", "Noise ColorFit Pro 4", 2299, 1, 0, 60, "abandoned"),
        ("Yash Trivedi", "+91 99887 65432", "Instant Pot Duo", 7490, 1, 0, 5, "abandoned"),
        ("Priyanka Reddy", "priyanka.reddy@gmail.com", "Philips Air Fryer", 6999, 1, 1, 2.5, "recovered"),
        ("Dev Patel", "+91 98111 22334", "Canon EOS R50 Camera Strap Kit", 3890, 1, 0, 9, "abandoned"),
        ("Simran Kaur", "simran.kaur@gmail.com", "Logitech MX Master 3S", 8999, 1, 1, 12, "abandoned"),
        ("Rahul Sharma", "+91 96540 87654", "Woodland Boots", 5490, 1, 0, 26, "abandoned"),
        ("Tanya Chawla", "tanya.chawla@yahoo.com", "Adidas Ultraboost", 11990, 1, 1, 0.5, "abandoned"),
        ("Aryan Bose", "+91 90909 11223", "Mi Power Bank 20000mAh", 1699, 3, 0, 38, "abandoned"),
        ("Kavya Menon", "kavya.menon@gmail.com", "Fastrack Sunglasses", 1499, 1, 0, 70, "recovered"),
    ]

    now = datetime.now()
    inserted_ids = []
    for name, contact, product, value, items, repeat, hours_ago, status in demo:
        cur = conn.execute(
            """INSERT INTO carts
               (customer_name, customer_contact, product_name, cart_value,
                items_count, is_repeat_customer, created_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, contact, product, value, items, repeat,
             (now - timedelta(hours=hours_ago)).isoformat(), status),
        )
        inserted_ids.append((cur.lastrowid, name, contact, product, value, items, repeat, hours_ago, status))
    conn.commit()

    # Backfill a matching decision-log history so the AI Decision Log and
    # the live "Agent Decisions" feed look populated, not empty.
    for cart_id, name, contact, product, value, items, repeat, hours_ago, status in inserted_ids:
        row = conn.execute("SELECT * FROM carts WHERE id = ?", (cart_id,)).fetchone()
        enriched = enrich_cart(row)
        decided_at = now - timedelta(hours=hours_ago, minutes=random.randint(1, 15))
        log_decision(cart_id, name, f"Recommended {enriched['action_text']}",
                     enriched["reasoning"], enriched["estimated_recoverable"],
                     outcome=("Recovered" if status == "recovered" else "Pending"),
                     created_at=decided_at.isoformat())
        if status == "recovered":
            log_decision(cart_id, name, "Cart recovered",
                         "Customer completed checkout after the recovery attempt.",
                         value, outcome="Recovered",
                         created_at=(decided_at + timedelta(minutes=random.randint(5, 90))).isoformat())

    conn.close()
    flash("Demo workspace loaded.", "success")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
