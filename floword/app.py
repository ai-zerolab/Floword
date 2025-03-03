from contextlib import asynccontextmanager

from fastapi import FastAPI

from floword.config import get_config
from floword.dbutils import init_engine
from floword.mcp.manager import init_mcp_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    async with init_engine(config), init_mcp_manager(config):
        yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def hello():
    return {"message": "Hello World"}
