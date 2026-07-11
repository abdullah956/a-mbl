"""a-mbl backend — local FastAPI prototype.

Run on the Mac so phones on the same Wi-Fi can reach it through Expo Go:

    conda activate a-mbl
    uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

This is a local demonstration server for synthetic data only.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import classifier, config, retention
from .db import connect
from .errors import install_handlers
from .routers import alerts, analysis, auth, cases, health, links, privacy, reports

CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60


async def _cleanup_loop():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        conn = connect()
        try:
            retention.cleanup(conn)
        finally:
            conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect()
    try:
        classifier.register_model_version(conn)
        retention.cleanup(conn)
        conn.commit()
    finally:
        conn.close()
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="a-mbl API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(  # local prototype on a trusted Wi-Fi network
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    install_handlers(app)
    for router in (health.router, auth.router, auth.me_router, links.router,
                   analysis.router, cases.router, alerts.router, reports.router,
                   privacy.router):
        app.include_router(router, prefix=config.API_PREFIX)
    return app


app = create_app()
