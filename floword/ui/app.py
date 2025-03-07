"""Main application for the Floword UI."""

import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from floword.ui.components.backend_config_page import create_backend_config_page
from floword.ui.components.conversation_page import create_conversation_page
from floword.ui.models.backend_config import BackendConfig


def create_app() -> gr.Blocks:
    """Create the Floword UI application.

    Returns:
        A Gradio Blocks application.
    """
    with gr.Blocks(title="Floword") as app:
        gr.Markdown("# Floword")

        with gr.Tabs() as tabs:
            with gr.TabItem("Conversation"):
                conversation_page = create_conversation_page()

            with gr.TabItem("Backend Config"):
                backend_config_page = create_backend_config_page()

        # Shared state
        backend_config = gr.State(BackendConfig())

        # Event handlers

        # Update conversation page when backend config changes
        backend_config_page.load(
            fn=lambda config: config,
            inputs=[backend_config],
            outputs=[backend_config],
        )

    return app


def main():
    """Run the Floword UI application."""
    app = create_app()
    app.launch(inbrowser=True)


if __name__ == "__main__":
    main()
