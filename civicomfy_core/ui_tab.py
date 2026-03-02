# ================================================
# civicomfy_core/ui_tab.py
# Gradio tab for A1111 - injects the HTML/JS UI
# ================================================
import os
import gradio as gr


def build_tab():
    """Build the Gradio tab that hosts the Civicomfy UI."""
    extension_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    js_dir = os.path.join(extension_root, "javascript")
    css_path = os.path.join(js_dir, "civicomfy.css")

    with gr.Blocks(analytics_enabled=False) as tab_ui:
        gr.HTML("""
        <div id="civicomfy-root">
            <div id="civicomfy-app">
                <!-- UI is rendered by civicomfy_app.js -->
                <div style="padding: 20px; text-align: center; color: #aaa;">
                    Loading Civicomfy...
                </div>
            </div>
        </div>
        """)

    return tab_ui, None
