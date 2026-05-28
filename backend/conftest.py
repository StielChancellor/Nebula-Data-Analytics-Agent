"""
Ensures the backend root is on sys.path so `services.api_gateway.app.main`
resolves when pytest runs from anywhere in the tree.
"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
