import pytest
from inline_snapshot import snapshot

from floword.router.api.params import (
    ChatRequest,
    ConversionInfo,
    PermitCallToolRequest,
    QueryConversations,
)

API_BASE_URL = "/api/v1/conversation"


def create_conversation(client) -> str:
    response = client.post(
        f"{API_BASE_URL}/create",
    )
    assert response.status_code == 200
    return response.json()["conversation_id"]


@pytest.mark.xfail
def test_generate_title(client):
    conversation_id = create_conversation(client)
    response = client.post(
        f"{API_BASE_URL}/generate-title/{conversation_id}",
    )
    assert response.status_code == 200


@pytest.mark.xfail
def test_update_conversation(client):
    conversation_id = create_conversation(client)
    response = client.post(
        f"{API_BASE_URL}/update/{conversation_id}",
    )
    assert response.status_code == 200


def test_crud_conversation(client):
    response = client.post(
        f"{API_BASE_URL}/delete/not-exists",
    )
    assert response.status_code == 404

    response = client.get(
        f"{API_BASE_URL}/info/not-exists",
    )
    assert response.status_code == 404

    response = client.get(
        f"{API_BASE_URL}/list",
    )
    assert response.status_code == 200
    response_data = QueryConversations.model_validate(response.json())
    assert len(response_data.datas) == 0

    conversation_id = create_conversation(client)

    response = client.get(
        f"{API_BASE_URL}/list",
    )
    assert response.status_code == 200
    response_data = QueryConversations.model_validate(response.json())
    assert len(response_data.datas) == 1
    response = client.get(
        f"{API_BASE_URL}/info/{conversation_id}",
    )
    assert response.status_code == 200
    response_data = ConversionInfo.model_validate(response.json())
    assert response_data

    response = client.post(
        f"{API_BASE_URL}/delete/{conversation_id}",
    )
    assert response.status_code == 204
    response = client.get(
        f"{API_BASE_URL}/info/{conversation_id}",
    )
    assert response.status_code == 404


@pytest.fixture(autouse=True)
def reset_sse_starlette_appstatus_event():
    """
    Fixture that resets the appstatus event in the sse_starlette app.

    Should be used on any test that uses sse_starlette to stream events.
    """
    # See https://github.com/sysid/sse-starlette/issues/59
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None


def test_chat_and_permit_tool_call(client):
    conversation_id = create_conversation(client)
    response = client.post(
        f"{API_BASE_URL}/chat/{conversation_id}",
        data=ChatRequest(prompt="Hello world").model_dump_json(),
    )
    assert response.status_code == 200
    response = client.get(
        f"{API_BASE_URL}/info/{conversation_id}",
    )
    assert response.status_code == 200
    response_data = ConversionInfo.model_validate(response.json())
    assert len(response_data.messages) == snapshot(3)

    response = client.post(
        f"{API_BASE_URL}/permit-call-tool/{conversation_id}",
        data=PermitCallToolRequest(execute_all_tool_calls=True).model_dump_json(),
    )
    assert response.status_code == 200
    response = client.get(
        f"{API_BASE_URL}/info/{conversation_id}",
    )
    assert response.status_code == 200
    response_data = ConversionInfo.model_validate(response.json())
    assert len(response_data.messages) == snapshot(5)
