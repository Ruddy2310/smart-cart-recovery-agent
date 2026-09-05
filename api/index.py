import sys
import os

# Make sure the project root (where app.py lives) is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

# Vercel's Python runtime looks for a WSGI/ASGI callable named `app`
