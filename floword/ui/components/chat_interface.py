"""Chat interface component for the Floword UI."""

from collections.abc import AsyncIterable
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from floword.llms.models import get_known_models, get_supported_providers
from floword.ui.api_client import FlowordAPIClient
from floword.ui.message_processor import MessageProcessor
from floword.ui.models import ToolCall

from pydantic_ai.models import ModelSettings
from floword.log import logger


# Global state
message_processor = MessageProcessor()


async def send_message(
    message: str,
    history: List[Dict[str, Any]],
    conversation_id: str,
    url: str,
    token: Optional[str] = None,
    provider: str = "openai",
    model_name: str = "gpt-4o",
    temperature: float = 0.7,
    max_tokens: int = 1000,
) -> AsyncIterable[Tuple[List[Dict[str, Any]], Optional[List[Dict[str, Any]]]]]:
    """Send a message to the backend.

    Args:
        message: The message to send.
        history: The conversation history.
        conversation_id: The ID of the conversation.
        url: The URL of the backend.
        token: Optional API token.
        provider: The model provider.
        model_name: The model name.
        temperature: The temperature parameter.
        max_tokens: The max tokens parameter.

    Returns:
        A tuple of (updated_history, tool_calls_data).
    """
    if not conversation_id:
        raise gr.Error("No conversation selected. Please create a new conversation first.")

    # Add the user message to the history
    history.append({"role": "user", "content": message})

    # Create the model settings
    model_settings = ModelSettings(
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Clear the message processor
    message_processor.clear()

    # Create the API client
    client = FlowordAPIClient(url, token)

    try:
        # Stream the response
        async for event in client.chat_stream(conversation_id, message, model_settings):
            # Process the event
            message_update, tool_calls = message_processor.process_event(event)

            # If we have tool calls, return them
            if tool_calls:
                tool_calls_data = [
                    {
                        "tool_name": tc.tool_name,
                        "args": tc.args,
                        "tool_call_id": tc.tool_call_id,
                    }
                    for tc in tool_calls
                ]
                await client.close()
                yield history, tool_calls_data

            # If we have a message update, add it to the history
            if message_update:
                # Check if we already have an assistant message
                if history and history[-1]["role"] == "assistant":
                    # Update the existing message
                    history[-1] = message_update
                else:
                    # Add a new message
                    history.append(message_update)

                # Yield the updated history
                yield history, None

        # Get the final message
        final_message = message_processor.get_current_message()
        if final_message:
            # Check if we already have an assistant message
            if history and history[-1]["role"] == "assistant":
                # Update the existing message
                history[-1] = final_message
            else:
                # Add a new message
                history.append(final_message)

        await client.close()
        yield history, None
    except Exception as e:
        await client.close()
        logger.exception(e)
        raise gr.Error(f"Failed to send message: {str(e)}")


def update_models(provider: str) -> List[str]:
    """Update the model list based on the selected provider.

    Args:
        provider: The selected provider.

    Returns:
        A list of models for the provider.
    """
    return get_known_models(provider)


def create_chat_interface() -> (
    Tuple[
        gr.Chatbot,
        gr.Textbox,
        gr.Button,
        gr.Dropdown,
        gr.Dropdown,
        gr.Slider,
        gr.Number,
    ]
):
    """Create the chat interface component.

    Returns:
        A tuple of (chatbot, message_input, submit_button, provider, model_name, temperature, max_tokens).
    """
    chatbot = gr.Chatbot(
        height=500,
        show_copy_button=True,
        render_markdown=True,
        type="messages",
    )

    with gr.Row():
        with gr.Column(scale=8):
            msg = gr.Textbox(
                placeholder="Type a message...",
                show_label=False,
                container=False,
                scale=8,
            )
        with gr.Column(scale=1):
            submit_btn = gr.Button("Send", variant="primary")

    with gr.Accordion("Model Settings", open=False):
        with gr.Row(visible=False):
            provider = gr.Dropdown(
                choices=get_supported_providers(),
                label="Provider",
                value="openai",
            )
            model_name = gr.Dropdown(
                label="Model",
                choices=get_known_models("openai"),
                value="gpt-4o",
            )

        with gr.Row():
            temperature = gr.Slider(
                minimum=0.0,
                maximum=1.0,
                value=0.7,
                step=0.1,
                label="Temperature",
            )
            max_tokens = gr.Number(
                value=1000,
                label="Max Tokens",
                precision=0,
            )

    return chatbot, msg, submit_btn, provider, model_name, temperature, max_tokens
