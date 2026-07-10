from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models.schemas import HealthResponse
from app.routers.catalog import router as catalog_router
from app.routers.datasets import router as datasets_router
from app.routers.media import router as media_router
from app.routers.raw import router as raw_router
from app.routers.raw_media import router as raw_media_router
from app.routers.converter import router as converter_router
from app.routers.hdf5 import router as hdf5_router


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog_router, prefix=settings.api_prefix)
app.include_router(datasets_router, prefix=settings.api_prefix)
app.include_router(raw_router, prefix=settings.api_prefix)
app.include_router(media_router)
app.include_router(raw_media_router)
app.include_router(converter_router, prefix=settings.api_prefix)
app.include_router(hdf5_router, prefix=settings.api_prefix)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)
