import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, HTTPException

from .commerce_monitor import CommerceMonitor
from .infrai_client import InfraiClient, InfraiError
from .models import WatchRequest, WatchResult


def create_app(
    *,
    gateway: InfraiClient | None = None,
    state_file: Path | None = None,
) -> FastAPI:
    client = gateway or InfraiClient(api_key=os.environ["INFRAI_API_KEY"])
    monitor = CommerceMonitor(
        client, state_file or Path(os.getenv("WATCH_STATE_FILE", ".watch-state.json"))
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await client.close()

    app = FastAPI(title="Commerce page change watch", lifespan=lifespan)

    @app.post("/checks", response_model=WatchResult)
    async def check_page(request: WatchRequest) -> WatchResult:
        try:
            return await monitor.check(request)
        except InfraiError as error:
            status = error.status_code if 400 <= error.status_code < 500 else 502
            raise HTTPException(
                status_code=status,
                detail={"code": error.code, "error": error.detail},
            ) from error

    return app


def run() -> None:
    uvicorn.run("order_watch.service:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
