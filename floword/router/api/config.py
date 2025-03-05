from fastapi import APIRouter, Depends

from floword.llms.models import KNOWN_MODELS, SUPPORTED_PROVIDERS
from floword.mcp.manager import MCPManager, get_mcp_manager
from floword.router.api.params import GetMcpServersResponse, GetModelsResponse

router = APIRouter(
    tags=["config"],
    prefix="/api/config",
)


@router.get("/models")
async def get_provider_and_models() -> GetModelsResponse:
    return GetModelsResponse(providers=SUPPORTED_PROVIDERS, models=KNOWN_MODELS)


@router.get("/mcp")
async def get_mcp(
    mcp_manager: MCPManager = Depends(get_mcp_manager),
) -> GetMcpServersResponse:
    return GetMcpServersResponse(servers=mcp_manager.get_tools())
