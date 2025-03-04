from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from floword.config import get_config
from floword.dbutils import init_engine
from floword.mcp.manager import init_mcp_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    async with init_engine(config), init_mcp_manager(config):
        yield


app = FastAPI(lifespan=lifespan)


# TODO: This is not secure, better move to config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def hello():
    return {"message": "Hello World"}
