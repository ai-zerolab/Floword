from fastapi import APIRouter

router = APIRouter(
    tags=["workflow"],
    prefix="/api/v1/workflow",
)
