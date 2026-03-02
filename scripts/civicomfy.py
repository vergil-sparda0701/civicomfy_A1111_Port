# ================================================
# Civicomfy - Civitai Downloader for Automatic1111
# Main Extension Entry Point (scripts/civicomfy.py)
# ================================================
import os
import sys

# Capture __file__ immediately at import time.
# In Colab + Google Drive, __file__ can become unreliable inside callbacks,
# so we freeze the path now and re-inject it each time it is needed.
_THIS_FILE = os.path.abspath(__file__)
_EXTENSION_ROOT = os.path.dirname(os.path.dirname(_THIS_FILE))


def _ensure_path():
    """Add the extension root to sys.path. Idempotent and Colab-safe."""
    for p in [
        _EXTENSION_ROOT,
        os.path.dirname(os.path.dirname(os.path.realpath(_THIS_FILE))),
    ]:
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
            print(f"[Civicomfy] Added to sys.path: {p}")


# Inject path at import time so any top-level imports already work.
_ensure_path()

from modules import script_callbacks  # noqa: E402


def on_ui_tabs():
    _ensure_path()
    from civicomfy_core.ui_tab import build_tab
    tab_ui, _ = build_tab()
    return [(tab_ui, "Civicomfy", "civicomfy_tab")]


def on_app_started(demo, app):
    _ensure_path()
    from civicomfy_core.routes import register_routes
    register_routes(app)
    print("[Civicomfy] API routes registered.")


script_callbacks.on_ui_tabs(on_ui_tabs)
script_callbacks.on_app_started(on_app_started)
