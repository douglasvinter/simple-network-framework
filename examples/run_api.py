"""Run SNF discovery and the optional REST/SSE API.

From the repository root:
    python -m uvicorn examples.run_api:app --host 127.0.0.1 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from snf import NetworkRuntime
from snf.api import create_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("snf-debug.log", encoding="utf-8")],
)
logging.getLogger("snf").setLevel(logging.DEBUG)

network = NetworkRuntime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with network:
        yield


app = FastAPI(title="Simple Network Framework", lifespan=lifespan)
app.include_router(create_router(network), prefix="/network")
