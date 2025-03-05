from pydantic import BaseModel


class GetModelsResponse(BaseModel):
    providers: list[str]
    models: dict[str, list[str]]


class NewConversation(BaseModel):
    conversation_id: str


class ChatRequest(BaseModel):
    pass


class QueryConversations(BaseModel):
    pass


class ConversionInfo(BaseModel):
    pass


class PermitCallToolRequest(BaseModel):
    pass
