import pytest
from inline_snapshot import Is, snapshot
from pydantic_ai.usage import Usage

from floword.router.api.params import ConversionInfo, QueryConversations

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
    assert response_data == snapshot(
        Is(
            ConversionInfo(
                conversation_id=conversation_id,
                title="Untitled",
                messages=[],
                usage=Usage(),
                created_at=response_data.created_at,
                updated_at=response_data.updated_at,
            )
        )
    )

    response = client.post(
        f"{API_BASE_URL}/delete/{conversation_id}",
    )
    assert response.status_code == 204
    response = client.get(
        f"{API_BASE_URL}/info/{conversation_id}",
    )
    assert response.status_code == 404
