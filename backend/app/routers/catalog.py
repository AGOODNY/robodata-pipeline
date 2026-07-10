from fastapi import APIRouter, HTTPException

from app.models.schemas import CatalogDataset, DeletedDataset
from app.services.catalog_service import DatasetDeletionNotAllowedError, delete_generated_dataset, list_catalog_datasets

router = APIRouter()


@router.get("/catalog/datasets", response_model=list[CatalogDataset])
def catalog_datasets() -> list[CatalogDataset]:
    return list_catalog_datasets()


@router.delete("/catalog/datasets/{dataset_name}", response_model=DeletedDataset)
def delete_dataset(dataset_name: str) -> DeletedDataset:
    try:
        delete_generated_dataset(dataset_name)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DatasetDeletionNotAllowedError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    return DeletedDataset(name=dataset_name)
