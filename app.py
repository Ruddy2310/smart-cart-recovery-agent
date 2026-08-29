"""
Smart Cart Recovery Agent
--------------------------
An AI-powered agent that detects abandoned shopping carts, scores the
likelihood of recovery, and auto-generates a personalized recovery
message (email / WhatsApp style) with a dynamically calculated discount
offer based on cart value, customer history, and idle time.

Track: AI Growth & Agentic Commerce
Author: Rudra Soni
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime, timedelta
import sqlite3
import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))

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
    conn.commit()
    conn.close()


# Make sure the table exists before any request handles it -- important on
# Vercel because there is no __main__ block running there (see api/index.py).
init_db()


# ---------------------------------------------------------------------------
# Core "Agentic" logic
# ---------------------------------------------------------------------------
def calculate_idle_hours(created_at_str):
    created_at = datetime.fromisoformat(created_at_str)
    delta = datetime.now() - created_at
    return round(delta.total_seconds() / 3600, 1)


def score_recovery_priority(cart_value, items_count, is_repeat, idle_hours):
    """
    Simple weighted scoring model that decides how 'urgent' and how
    'incentivized' the recovery attempt should be. This is the decision
    engine of the agent -- it decides WHETHER and HOW MUCH discount to
    offer, instead of blindly offering the same discount to everyone.
    """
    score = 0
    score += min(cart_value / 500, 20)          # high value carts -> higher priority
    score += items_count * 2                     # more items -> more intent
    score += 15 if is_repeat else 0               # loyal customers matter more
    score += min(idle_hours * 1.5, 15)            # older abandonment -> more urgency

    if score >= 40:
        priority = "High"
        discount = 15
    elif score >= 22:
        priority = "Medium"
        discount = 10
    else:
        priority = "Low"
        discount = 5

    return round(score, 1), priority, discount


def generate_recovery_message(name, product, discount, priority, is_repeat):
    """
    Rule-based natural language generator that personalizes tone and
    urgency based on the recovery priority computed above. This acts as
    the 'agent's voice' -- no external AI API key needed for the demo,
    but this function is structured so it can be swapped for a live LLM
    call (see README) without changing the rest of the pipeline.
    """
    greeting = random.choice([f"Hey {name}!", f"Hi {name},", f"{name}, quick one for you \U0001F44B"])

    if is_repeat:
        loyalty_line = "As one of our valued repeat customers, "
    else:
        loyalty_line = ""

    if priority == "High":
        urgency_line = "Your cart is about to expire — don't miss out!"
    elif priority == "Medium":
        urgency_line = "Your items are still saved, but stock is moving fast."
    else:
        urgency_line = "We saved your cart in case you want to pick up where you left off."

    message = (
        f"{greeting} {loyalty_line}we noticed you left {product} in your cart. "
        f"{urgency_line} Complete your purchase now and get {discount}% off "
        f"with code SAVE{discount}. Tap below to checkout before your discount expires!"
    )
    return message


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    conn = get_db()
    carts = conn.execute("SELECT * FROM carts ORDER BY created_at DESC").fetchall()
    conn.close()

    enriched = []
    for cart in carts:
        idle_hours = calculate_idle_hours(cart["created_at"])
        score, priority, discount = score_recovery_priority(
            cart["cart_value"], cart["items_count"], cart["is_repeat_customer"], idle_hours
        )
        enriched.append({**dict(cart), "idle_hours": idle_hours, "score": score, "priority": priority})

    total_value = sum(c["cart_value"] for c in carts)
    recovered_value = sum(c["cart_value"] for c in carts if c["status"] == "recovered")

    stats = {
        "total_carts": len(carts),
        "abandoned": len([c for c in carts if c["status"] == "abandoned"]),
        "recovered": len([c for c in carts if c["status"] == "recovered"]),
        "total_value": round(total_value, 2),
        "recovered_value": round(recovered_value, 2),
    }

    return render_template("dashboard.html", carts=enriched, stats=stats)


@app.route("/add", methods=["GET", "POST"])
def add_cart():
    if request.method == "POST":
        conn = get_db()
        conn.execute(
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
        conn.close()
        return redirect(url_for("dashboard"))

    return render_template("add_cart.html")


@app.route("/generate/<int:cart_id>", methods=["POST"])
def generate(cart_id):
    conn = get_db()
    cart = conn.execute("SELECT * FROM carts WHERE id = ?", (cart_id,)).fetchone()

    idle_hours = calculate_idle_hours(cart["created_at"])
    score, priority, discount = score_recovery_priority(
        cart["cart_value"], cart["items_count"], cart["is_repeat_customer"], idle_hours
    )
    message = generate_recovery_message(
        cart["customer_name"], cart["product_name"], discount, priority, cart["is_repeat_customer"]
    )

    conn.execute(
        "UPDATE carts SET recovery_message = ?, discount_offered = ? WHERE id = ?",
        (message, discount, cart_id),
    )
    conn.commit()
    conn.close()

    return jsonify({"message": message, "discount": discount, "priority": priority, "score": score})


@app.route("/recover/<int:cart_id>", methods=["POST"])
def mark_recovered(cart_id):
    conn = get_db()
    conn.execute("UPDATE carts SET status = 'recovered' WHERE id = ?", (cart_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/delete/<int:cart_id>", methods=["POST"])
def delete_cart(cart_id):
    conn = get_db()
    conn.execute("DELETE FROM carts WHERE id = ?", (cart_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/seed")
def seed_demo_data():
    """Populates the DB with sample abandoned carts for demo purposes."""
    conn = get_db()
    conn.execute("DELETE FROM carts")
    demo_carts = [
        ("Rudra Soni", "rudra@example.com", "Wireless Headphones", 2499, 1, 1,
         (datetime.now() - timedelta(hours=6)).isoformat()),
        ("Ananya Patel", "ananya@example.com", "Running Shoes + Socks", 3899, 2, 0,
         (datetime.now() - timedelta(hours=30)).isoformat()),
        ("Karan Mehta", "karan@example.com", "Smart Watch", 8999, 1, 1,
         (datetime.now() - timedelta(hours=2)).isoformat()),
        ("Priya Shah", "priya@example.com", "Backpack", 1299, 1, 0,
         (datetime.now() - timedelta(hours=50)).isoformat()),
        ("Devansh Joshi", "devansh@example.com", "Gaming Mouse + Keyboard", 4599, 2, 1,
         (datetime.now() - timedelta(hours=12)).isoformat()),
    ]
    conn.executemany(
        """INSERT INTO carts
           (customer_name, customer_contact, product_name, cart_value,
            items_count, is_repeat_customer, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        demo_carts,
    )
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
