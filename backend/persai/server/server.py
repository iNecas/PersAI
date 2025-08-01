import os
import platform
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .endpoints import router
from persai.agent import initialize
from persai.errors import register_exception_handlers
from persai import version


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting Persai backend",
        python_version=platform.python_version(),
        system=platform.system(),
        version=version.__version__,
    )

    try:
        logger.info("Initializing Llama Stack client")
        await initialize()
        logger.info("Llama Stack client initialized successfully")
    except Exception as e:
        logger.exception("Failed to initialize Llama Stack client", error=str(e))
        raise

    yield

    logger.info("Shutting down Persai backend")


def get_server():
    app = FastAPI(
        title=f"PersAI Backend service - OpenAPI",
        description=f"PersAI Backend service API specification.",
        version=version.__version__,
        license_info={
            "name": "Apache 2.0",
            "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
        },
        lifespan=lifespan,
    )

    # Register exception handlers
    register_exception_handlers(app)

    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        "Add request info into logging context"
        request_id = str(uuid.uuid4())

        with logger.contextualize(
            request_id=request_id, path=request.url.path, method=request.method
        ):
            start_time = time.time()
            logger.info("Request started")

            response = await call_next(request)

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "Request completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            return response

    cors_origins = os.getenv("PERSAI_CORS_ORIGINS")
    if cors_origins is None:
        cors_origins = os.getenv("PERSES_API_URL", "http://localhost:3000")

    # Only add CORS middleware if origins are non-empty
    if cors_origins.strip():
        allow_origins = [origin.strip() for origin in cors_origins.split(",")]

        app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(router)
    return app
