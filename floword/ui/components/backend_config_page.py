"""Backend configuration page component for the Floword UI."""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Callable

import gradio as gr

from floword.ui.api_client import APIError, FlowordAPIClient
from floword.ui.backend_manager import BackendProcessManager
from floword.ui.models.backend_config import BackendConfig, BackendMode

# Set up logging
from floword.log import logger


class BackendConfigPage:
    """Backend configuration page component."""

    def __init__(self):
        """Initialize the backend configuration page."""
        self.backend_config = BackendConfig()
        self.backend_manager = BackendProcessManager()

    async def test_connection(self, url: str, token: Optional[str] = None) -> Tuple[bool, str]:
        """Test the connection to the backend.

        Args:
            url: The URL of the backend.
            token: Optional API token.

        Returns:
            A tuple of (is_connected, message).
        """
        client = FlowordAPIClient(url, token)
        try:
            await client.test_connection()
            await client.close()
            return True, "✅ Connected to backend successfully!"
        except Exception as e:
            await client.close()
            logger.error(f"Connection test failed: {str(e)}")
            return False, f"❌ Failed to connect to backend: {str(e)}"

    async def start_backend(self, config: BackendConfig) -> Tuple[bool, str]:
        """Start the backend process.

        Args:
            config: The backend configuration.

        Returns:
            A tuple of (success, message).
        """
        if config.mode != BackendMode.LOCAL:
            return False, "Backend is in remote mode, cannot start local process."

        # Find an available port if needed
        port = config.port
        if not await self.backend_manager.is_port_available(port):
            port = await self.backend_manager.find_available_port(port)
            config.port = port

        # Update the API URL
        config.api_url = f"http://localhost:{port}"

        # Start the backend
        success, message = await self.backend_manager.start_backend(port, config.env_vars)

        return success, message

    async def stop_backend(self) -> Tuple[bool, str]:
        """Stop the backend process.

        Returns:
            A tuple of (success, message).
        """
        return await self.backend_manager.stop_backend()

    async def get_backend_status(self) -> Tuple[bool, str]:
        """Get the status of the backend process.

        Returns:
            A tuple of (running, status_message).
        """
        return await self.backend_manager.get_backend_status()

    def update_mode(self, mode: str) -> Tuple[gr.update, gr.update, gr.update, gr.update]:
        """Update the UI based on the selected mode.

        Args:
            mode: The selected mode.

        Returns:
            A tuple of updates for (port_group, env_vars_group, start_stop_group, api_token_group).
        """
        if mode == BackendMode.LOCAL:
            return (
                gr.update(visible=True),  # port_group
                gr.update(visible=True),  # env_vars_group
                gr.update(visible=True),  # start_stop_group
                gr.update(visible=False),  # api_token_group
            )
        else:  # REMOTE
            return (
                gr.update(visible=False),  # port_group
                gr.update(visible=False),  # env_vars_group
                gr.update(visible=False),  # start_stop_group
                gr.update(visible=True),  # api_token_group
            )

    def parse_env_vars(self, env_vars_text: str) -> Dict[str, str]:
        """Parse environment variables from text.

        Args:
            env_vars_text: The environment variables text.

        Returns:
            A dictionary of environment variables.
        """
        env_vars = {}
        for line in env_vars_text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

        return env_vars

    def format_env_vars(self, env_vars: Dict[str, str]) -> str:
        """Format environment variables as text.

        Args:
            env_vars: The environment variables.

        Returns:
            The formatted environment variables text.
        """
        return "\n".join([f"{key}={value}" for key, value in env_vars.items()])

    def save_config(
        self,
        mode: str,
        port: int,
        api_url: str,
        api_token: str,
        env_vars_text: str,
    ) -> Tuple[BackendConfig, str]:
        """Save the backend configuration.

        Args:
            mode: The backend mode.
            port: The port for local mode.
            api_url: The API URL for remote mode.
            api_token: The API token for remote mode.
            env_vars_text: The environment variables text.

        Returns:
            A tuple of (config, message).
        """
        # Parse environment variables
        env_vars = self.parse_env_vars(env_vars_text)

        # Create the config
        config = BackendConfig(
            mode=mode,
            port=port,
            api_url=api_url if mode == BackendMode.REMOTE else f"http://localhost:{port}",
            api_token=api_token if mode == BackendMode.REMOTE else None,
            env_vars=env_vars,
        )

        # Save the config
        self.backend_config = config

        return config, "Configuration saved successfully!"

    def create_page(self) -> gr.Blocks:
        """Create the backend configuration page.

        Returns:
            A Gradio Blocks component for the backend configuration page.
        """
        with gr.Blocks() as backend_config_page:
            gr.Markdown("# Backend Configuration")

            # Status message
            status_message = gr.Markdown("")

            with gr.Row():
                # Mode selection
                mode = gr.Radio(
                    choices=[BackendMode.LOCAL, BackendMode.REMOTE],
                    label="Backend Mode",
                    value=self.backend_config.mode,
                )

            # Local mode settings
            with gr.Group(visible=self.backend_config.mode == BackendMode.LOCAL) as port_group:
                port = gr.Number(
                    value=self.backend_config.port,
                    label="Port",
                    precision=0,
                )

            # Remote mode settings
            with gr.Group(visible=self.backend_config.mode == BackendMode.REMOTE) as api_token_group:
                api_token = gr.Textbox(
                    value=self.backend_config.api_token or "",
                    label="API Token",
                    type="password",
                )

            # Common settings
            api_url = gr.Textbox(
                value=self.backend_config.api_url,
                label="API URL",
            )

            # Environment variables
            with gr.Group(visible=self.backend_config.mode == BackendMode.LOCAL) as env_vars_group:
                gr.Markdown("### Environment Variables")
                gr.Markdown("Enter one environment variable per line in the format: KEY=VALUE")
                env_vars = gr.TextArea(
                    value=self.format_env_vars(self.backend_config.env_vars),
                    label="Environment Variables",
                    lines=10,
                )

            # Buttons
            with gr.Row():
                save_btn = gr.Button("Save Configuration", variant="primary")
                test_btn = gr.Button("Test Connection", variant="secondary")

            # Start/Stop buttons (only for local mode)
            with gr.Row(visible=self.backend_config.mode == BackendMode.LOCAL) as start_stop_group:
                start_btn = gr.Button("Start Backend", variant="primary")
                stop_btn = gr.Button("Stop Backend", variant="stop")

            # State variables
            config_state = gr.State(self.backend_config)

            # Event handlers

            # Mode change
            mode.change(
                fn=self.update_mode,
                inputs=[mode],
                outputs=[
                    port_group,
                    env_vars_group,
                    start_stop_group,
                    api_token_group,
                ],
            )

            # Save configuration
            save_btn.click(
                fn=self.save_config,
                inputs=[mode, port, api_url, api_token, env_vars],
                outputs=[config_state, status_message],
            )

            # Test connection
            test_btn.click(
                fn=self.test_connection,
                inputs=[api_url, api_token],
                outputs=[gr.State(True), status_message],
            )

            # Start backend - directly pass the coroutine function
            start_btn.click(
                fn=self.start_backend,
                inputs=[config_state],
                outputs=[gr.State(True), status_message],
            )

            # Stop backend - directly pass the coroutine function
            stop_btn.click(
                fn=self.stop_backend,
                outputs=[gr.State(True), status_message],
            )

            # Check backend status on page load - directly pass the coroutine function
            backend_config_page.load(
                fn=self.get_backend_status,
                outputs=[gr.State(True), status_message],
            )

        return backend_config_page


# Create a global backend config page for use in the UI
backend_config_page = BackendConfigPage()


def create_backend_config_page() -> gr.Blocks:
    """Create the backend configuration page.

    Returns:
        A Gradio Blocks component for the backend configuration page.
    """
    return backend_config_page.create_page()
