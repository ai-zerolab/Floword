"""Backend configuration page component for the Floword UI."""

from typing import Dict, List, Optional, Tuple, Any, Union

import gradio as gr
import pandas as pd

from floword.ui.api_client import FlowordAPIClient
from floword.ui.backend_manager import BackendProcessManager


# Global state
backend_manager = BackendProcessManager()


async def start_backend(port: int, env_vars_df: Union[List[List[str]], pd.DataFrame]) -> str:
    """Start the backend.

    Args:
        port: The port to start the backend on.
        env_vars_df: The environment variables as a dataframe.

    Returns:
        A status message.
    """
    # Convert dataframe to dict
    env_vars = {}

    # Handle both list and DataFrame inputs
    if isinstance(env_vars_df, pd.DataFrame):
        # Convert DataFrame to list of lists
        env_vars_list = env_vars_df.values.tolist()
    else:
        env_vars_list = env_vars_df

    # Process the list of lists
    if env_vars_list:
        for row in env_vars_list:
            if len(row) == 2 and row[0] and row[1]:
                env_vars[row[0]] = row[1]

    success, message = await backend_manager.start_backend(port, env_vars)
    return message


async def stop_backend() -> str:
    """Stop the backend.

    Returns:
        A status message.
    """
    success, message = await backend_manager.stop_backend()
    return message


async def test_connection(url: str, token: Optional[str] = None) -> str:
    """Test the connection to the backend.

    Args:
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        A status message.
    """
    client = FlowordAPIClient(url, token)
    try:
        # Try to create a conversation to test the connection
        conversation_id = await client.create_conversation()
        await client.close()
        return f"Connection successful! Created conversation: {conversation_id}"
    except Exception as e:
        await client.close()
        return f"Connection failed: {str(e)}"


def update_visibility(mode: str) -> Tuple[Dict, Dict]:
    """Update the visibility of the configuration sections based on the mode.

    Args:
        mode: The backend mode.

    Returns:
        A tuple of (local_config_update, remote_config_update).
    """
    return (
        gr.update(visible=(mode == "local")),
        gr.update(visible=(mode == "remote")),
    )


def create_backend_config_page() -> gr.Blocks:
    """Create the backend configuration page.

    Returns:
        A Gradio Blocks component for the backend configuration page.
    """
    with gr.Blocks() as backend_config_page:
        gr.Markdown("# Backend Configuration")

        with gr.Row():
            backend_mode = gr.Radio(
                choices=["local", "remote"],
                label="Backend Mode",
                value="local",
            )

        # Local backend configuration
        with gr.Column(visible=True) as local_config:
            gr.Markdown("### Local Backend Configuration")

            with gr.Row():
                port = gr.Number(
                    value=9772,
                    label="Port",
                    precision=0,
                )
                start_btn = gr.Button("Start Backend", variant="primary")
                stop_btn = gr.Button("Stop Backend", variant="stop")

            status = gr.Textbox(
                label="Status",
                interactive=False,
            )

            with gr.Accordion("Environment Variables", open=False):
                gr.Markdown("Set environment variables for the local backend.")

                # Simple approach: just use textboxes for key-value pairs
                env_vars_md = gr.Markdown("Current Environment Variables:")
                env_vars_display = gr.Markdown("None")

                # State to store environment variables
                env_vars_state = gr.State({})

                # Function to add environment variable
                def add_env_var(
                    key: str, value: str, current_vars: Dict[str, str]
                ) -> Tuple[str, str, Dict[str, str], str]:
                    if key and value:
                        if current_vars is None:
                            current_vars = {}
                        current_vars[key] = value

                        # Format the environment variables for display
                        if current_vars:
                            display = "<ul>"
                            for k, v in current_vars.items():
                                display += f"<li><b>{k}</b>: {v}</li>"
                            display += "</ul>"
                        else:
                            display = "None"

                        return "", "", current_vars, display
                    return key, value, current_vars or {}, env_vars_display

                with gr.Row():
                    env_key = gr.Textbox(label="Key")
                    env_value = gr.Textbox(label="Value")
                    add_env_btn = gr.Button("Add", size="sm")

                # Hidden dataframe for compatibility with start_backend
                env_vars = gr.Dataframe(
                    headers=["Key", "Value"],
                    datatype=["str", "str"],
                    row_count=0,
                    col_count=(2, "fixed"),
                    interactive=False,
                    visible=False,
                )

                # Function to update the hidden dataframe from the state
                def update_env_vars_df(env_vars_dict: Dict[str, str]) -> List[List[str]]:
                    return [[k, v] for k, v in env_vars_dict.items()]

        # Remote backend configuration
        with gr.Column(visible=False) as remote_config:
            gr.Markdown("### Remote Backend Configuration")

            with gr.Row():
                api_url = gr.Textbox(
                    value="http://localhost:9772",
                    label="API URL",
                )
                api_token = gr.Textbox(
                    label="API Token (Optional)",
                    placeholder="Enter API token...",
                    type="password",
                )

            test_connection_btn = gr.Button("Test Connection", variant="secondary")
            connection_status = gr.Textbox(
                label="Connection Status",
                interactive=False,
            )

        # Event handlers
        backend_mode.change(
            fn=update_visibility,
            inputs=[backend_mode],
            outputs=[local_config, remote_config],
        )

        # Add environment variable
        add_env_btn.click(
            fn=add_env_var,
            inputs=[env_key, env_value, env_vars_state],
            outputs=[env_key, env_value, env_vars_state, env_vars_display],
        ).then(
            fn=update_env_vars_df,
            inputs=[env_vars_state],
            outputs=[env_vars],
        )

        start_btn.click(
            fn=start_backend,
            inputs=[port, env_vars],
            outputs=[status],
        )

        stop_btn.click(
            fn=stop_backend,
            outputs=[status],
        )

        test_connection_btn.click(
            fn=test_connection,
            inputs=[api_url, api_token],
            outputs=[connection_status],
        )

    return backend_config_page
