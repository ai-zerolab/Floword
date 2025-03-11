from contextlib import asynccontextmanager

from fastapi import FastAPI

from floword.config import get_config
from floword.dbutils import init_engine
from floword.log import logger
from floword.mcp.manager import init_mcp_manager
from floword.router.api import routers
from floword.router.streamer import PersistentStreamer


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    logger.info(f"Current default model: {config.default_model_provider}:{config.default_model_name}")

    async with init_engine(config), init_mcp_manager(config), PersistentStreamer.auto_cleanup():
        yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def hello():
    return {"message": "Hello World"}


for router in routers:
    app.include_router(router)
