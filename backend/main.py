from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import HTTPException as FastAPIHTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from logging import getLogger
import time
import uuid

from backend.app.core.config import settings
from backend.app.core.errors import api_exception_handler, global_exception_handler, http_exception_handler, validation_exception_handler
from backend.app.core.exceptions import APIException
from backend.app.composition import app_services
from backend.app.routers import wechat
from backend.app.infrastructure.database import init_database
from backend.app.infrastructure.repositories import repository_session
from backend.app.routers import ai_quality, auth, config, delivery, editorial, integrations, intelligence, market_intelligence, news, pipeline, public_content, publications, source_operations, spiders
from fastapi.responses import JSONResponse

logger = getLogger("uvicorn")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    init_database()
    app_services.credentials.initialize()
    app_services.scraper_runtime_state.ensure_runtime_initialized()
    logger.info("Database initialized")
    try:
        yield
    finally:
        await app_services.wechat_sources.cancel_login()
        logger.info("Shutting down...")


app = FastAPI(title=settings.PROJECT_NAME, version=settings.APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(APIException, api_exception_handler)
app.add_exception_handler(FastAPIHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)


@app.middleware("http")
async def bind_repository_session(request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id
    started_at = time.perf_counter()
    status_code = 500
    if request.url.path == "/health/live":
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    with repository_session():
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                status_code,
                (time.perf_counter() - started_at) * 1000,
            )

app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(news.router, prefix="/api", tags=["News"])
app.include_router(public_content.router, prefix="/api", tags=["Public Content"])
app.include_router(config.router, prefix="/api", tags=["Config"])
app.include_router(wechat.router, prefix='/api', tags=['Wechat'])
app.include_router(spiders.router, prefix="/api", tags=["Spiders"])
app.include_router(pipeline.router, prefix="/api", tags=["Content Pipeline"])
app.include_router(delivery.router, prefix="/api", tags=["Delivery"])
app.include_router(integrations.router, prefix="/api", tags=["Integrations"])
app.include_router(editorial.router, prefix="/api", tags=["Editorial Workbench"])
app.include_router(ai_quality.router, prefix="/api", tags=["AI Quality"])
app.include_router(publications.router, prefix="/api", tags=["Publications"])
app.include_router(intelligence.router, prefix="/api", tags=["Intelligence"])
app.include_router(source_operations.router, prefix="/api", tags=["Source Operations"])
app.include_router(market_intelligence.router, prefix="/api", tags=["Market Intelligence"])


def readiness_response(check):
    ready, payload = check()
    content = {**payload, "version": settings.APP_VERSION}
    return content if ready else JSONResponse(status_code=503, content=content)


@app.get("/")
def health_check():
    return readiness_response(app_services.runtime_health.api_readiness)


@app.get("/health/live")
def liveness_check():
    return {**app_services.runtime_health.liveness(), "version": settings.APP_VERSION}


@app.get("/health/ready")
def readiness_check():
    return readiness_response(app_services.runtime_health.api_readiness)


@app.get("/health/pipeline")
def pipeline_readiness_check():
    return readiness_response(app_services.runtime_health.pipeline_readiness)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True, proxy_headers=False)
