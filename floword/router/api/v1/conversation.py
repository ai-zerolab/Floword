from fastapi import APIRouter

router = APIRouter(
    tags=["conversation"],
    prefix="/api/v1/conversation",
)
