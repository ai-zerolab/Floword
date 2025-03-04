from fastapi import APIRouter

router = APIRouter(
    tags=["config"],
    prefix="/api/config",
)
