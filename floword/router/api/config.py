from fastapi import APIRouter

from floword.llms.models import KNOWN_MODELS, SUPPORTED_PROVIDERS
from floword.router.api.params import GetModelsResponse

router = APIRouter(
    tags=["config"],
    prefix="/api/config",
)


@router.get("/models")
async def get_provider_and_models() -> GetModelsResponse:
    return GetModelsResponse(providers=SUPPORTED_PROVIDERS, models=KNOWN_MODELS)
