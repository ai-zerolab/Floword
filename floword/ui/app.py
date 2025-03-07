"""Gradio UI for Floword."""

import gradio as gr

from floword.ui.components.backend_config_page import create_backend_config_page
from floword.ui.components.conversation_page import create_conversation_page


def create_ui() -> gr.Blocks:
    """Create the UI.

    Returns:
        A Gradio Blocks component for the UI.
    """
    with gr.Blocks(title="Floword UI") as app:
        with gr.Tabs() as tabs:
            with gr.TabItem("Conversation", id=0):
                conversation_page = create_conversation_page()

            with gr.TabItem("Backend Config", id=1):
                backend_config_page = create_backend_config_page()

    return app


def main():
    """Run the UI."""
    app = create_ui()
    app.launch(inbrowser=True)


if __name__ == "__main__":
    main()
