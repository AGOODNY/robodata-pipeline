from fastapi import APIRouter

from app.models.schemas import CatalogDataset
from app.services.catalog_service import list_catalog_datasets

router = APIRouter()


@router.get("/catalog/datasets", response_model=list[CatalogDataset])
def catalog_datasets() -> list[CatalogDataset]:
    return list_catalog_datasets()
