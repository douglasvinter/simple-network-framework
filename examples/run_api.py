"""Run SNF discovery and the optional REST/SSE API.

From the repository root:
    python -m uvicorn examples.run_api:app --host 127.0.0.1 --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from snf import NetworkRuntime
from snf.api import create_router

network = NetworkRuntime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with network:
        yield


app = FastAPI(title="Simple Network Framework", lifespan=lifespan)
app.include_router(create_router(network), prefix="/network")
