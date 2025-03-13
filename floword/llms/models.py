import json
from typing import Any

from fastapi import Depends
from pydantic import BaseModel
from pydantic_ai.models import Model

from floword.config import Config, get_config
from floword.log import logger

SUPPORTED_PROVIDERS = [
    "openai",
    "anthropic",
    "bedrock",
    "google-vertex",
    "google-gla",
    "cohere",
    "groq",
    "mistral",
]


KNOWN_MODELS = {
    "openai": [
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-0125",
        "gpt-3.5-turbo-0301",
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-1106",
        "gpt-3.5-turbo-16k",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4",
        "gpt-4-0125-preview",
        "gpt-4-0314",
        "gpt-4-0613",
        "gpt-4-1106-preview",
        "gpt-4-32k",
        "gpt-4-32k-0314",
        "gpt-4-32k-0613",
        "gpt-4-turbo",
        "gpt-4-turbo-2024-04-09",
        "gpt-4-turbo-preview",
        "gpt-4-vision-preview",
        "gpt-4.5-preview",
        "gpt-4.5-preview-2025-02-27",
        "gpt-4o",
        "gpt-4o-2024-05-13",
        "gpt-4o-2024-08-06",
        "gpt-4o-2024-11-20",
        "gpt-4o-audio-preview",
        "gpt-4o-audio-preview-2024-10-01",
        "gpt-4o-audio-preview-2024-12-17",
        "gpt-4o-mini",
        "gpt-4o-mini-2024-07-18",
        "gpt-4o-mini-audio-preview",
        "gpt-4o-mini-audio-preview-2024-12-17",
        "o1",
        "o1-2024-12-17",
        "o1-mini",
        "o1-mini-2024-09-12",
        "o1-preview",
        "o1-preview-2024-09-12",
        "o3-mini",
        "o3-mini-2025-01-31",
    ],
    "anthropic": [
        "claude-3-7-sonnet-20250219",
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-opus-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-opus-latest",
    ],
    "bedrock": [
        "amazon.titan-tg1-large",
        "amazon.titan-text-lite-v1",
        "amazon.titan-text-express-v1",
        "us.amazon.nova-pro-v1:0",
        "us.amazon.nova-lite-v1:0",
        "us.amazon.nova-micro-v1:0",
        "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "anthropic.claude-3-5-haiku-20241022-v1:0",
        "us.anthropic.claude-3-5-haiku-20241022-v1:0",
        "anthropic.claude-instant-v1",
        "anthropic.claude-v2:1",
        "anthropic.claude-v2",
        "anthropic.claude-3-sonnet-20240229-v1:0",
        "us.anthropic.claude-3-sonnet-20240229-v1:0",
        "anthropic.claude-3-haiku-20240307-v1:0",
        "us.anthropic.claude-3-haiku-20240307-v1:0",
        "anthropic.claude-3-opus-20240229-v1:0",
        "us.anthropic.claude-3-opus-20240229-v1:0",
        "anthropic.claude-3-5-sonnet-20240620-v1:0",
        "us.anthropic.claude-3-5-sonnet-20240620-v1:0",
        "anthropic.claude-3-7-sonnet-20250219-v1:0",
        "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        "cohere.command-text-v14",
        "cohere.command-r-v1:0",
        "cohere.command-r-plus-v1:0",
        "cohere.command-light-text-v14",
        "meta.llama3-8b-instruct-v1:0",
        "meta.llama3-70b-instruct-v1:0",
        "meta.llama3-1-8b-instruct-v1:0",
        "us.meta.llama3-1-8b-instruct-v1:0",
        "meta.llama3-1-70b-instruct-v1:0",
        "us.meta.llama3-1-70b-instruct-v1:0",
        "meta.llama3-1-405b-instruct-v1:0",
        "us.meta.llama3-2-11b-instruct-v1:0",
        "us.meta.llama3-2-90b-instruct-v1:0",
        "us.meta.llama3-2-1b-instruct-v1:0",
        "us.meta.llama3-2-3b-instruct-v1:0",
        "us.meta.llama3-3-70b-instruct-v1:0",
        "mistral.mistral-7b-instruct-v0:2",
        "mistral.mixtral-8x7b-instruct-v0:1",
        "mistral.mistral-large-2402-v1:0",
        "mistral.mistral-large-2407-v1:0",
    ],
    "cohere": [
        "c4ai-aya-expanse-32b",
        "c4ai-aya-expanse-8b",
        "command",
        "command-light",
        "command-light-nightly",
        "command-nightly",
        "command-r",
        "command-r-03-2024",
        "command-r-08-2024",
        "command-r-plus",
        "command-r-plus-04-2024",
        "command-r-plus-08-2024",
        "command-r7b-12-2024",
    ],
    "google-gla": [
        "gemini-1.0-pro",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro",
        "gemini-2.0-flash-exp",
        "gemini-2.0-flash-thinking-exp-01-21",
        "gemini-exp-1206",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite-preview-02-05",
    ],
    "google-vertex": [
        "gemini-1.0-pro",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro",
        "gemini-2.0-flash-exp",
        "gemini-2.0-flash-thinking-exp-01-21",
        "gemini-exp-1206",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite-preview-02-05",
    ],
    "groq": [
        "gemma2-9b-it",
        "llama-3.1-8b-instant",
        "llama-3.2-11b-vision-preview",
        "llama-3.2-1b-preview",
        "llama-3.2-3b-preview",
        "llama-3.2-90b-vision-preview",
        "llama-3.3-70b-specdec",
        "llama-3.3-70b-versatile",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
    ],
    "mistral": [
        "codestral-latest",
        "mistral-large-latest",
        "mistral-moderation-latest",
        "mistral-small-latest",
    ],
}


def _get_model_cls(provider: str) -> type["Model"]:
    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIModel

        return OpenAIModel
    elif provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel

        return AnthropicModel
    elif provider == "bedrock":
        from pydantic_ai.models.bedrock import BedrockConverseModel

        return BedrockConverseModel
    elif provider == "cohere":
        from pydantic_ai.models.cohere import CohereModel

        return CohereModel
    elif provider == "google-gla":
        from pydantic_ai.models.gemini import GeminiModel

        return GeminiModel
    elif provider == "google-vertex":
        from pydantic_ai.models.vertexai import VertexAIModel

        return VertexAIModel
    elif provider == "groq":
        from pydantic_ai.models.groq import GroqModel

        return GroqModel
    elif provider == "mistral":
        from pydantic_ai.models.mistral import MistralModel

        return MistralModel
    elif provider == "test":
        from pydantic_ai.models.test import TestModel

        return TestModel
    else:
        from pydantic_ai.models.openai import OpenAIModel

        # Fallback to OpenAI
        return OpenAIModel


class ModelInitParams(BaseModel):
    provider: str | None = None
    model_name: str | None = None
    model_kwargs: dict[str, Any] = {}


def get_default_model(config: Config = Depends(get_config)) -> Model | None:
    if not config.default_model_name:
        return None

    return init_model(
        ModelInitParams(
            provider=config.default_model_provider,
            model_name=config.default_model_name,
            model_kwargs=json.loads(config.default_model_kwargs or "{}"),
        )
    )


def init_model(model_init_params: ModelInitParams) -> Model:
    model_cls = _get_model_cls(model_init_params.provider)
    logger.debug(f"Initializing model {model_cls}")
    return model_cls(
        model_name=model_init_params.model_name,
        **model_init_params.model_kwargs,
    )


def get_supported_providers() -> list[str]:
    return SUPPORTED_PROVIDERS


def get_all_known_models() -> dict[str, list[str]]:
    return KNOWN_MODELS


def get_known_models(provider: str) -> list[str]:
    return KNOWN_MODELS.get(provider, [])
