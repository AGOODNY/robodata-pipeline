from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.lerobot_service import DatasetNotFoundError, media_file

router = APIRouter()


@router.get("/media/{dataset_name}/{relative_path:path}")
def dataset_media(dataset_name: str, relative_path: str) -> FileResponse:
    try:
        return FileResponse(media_file(dataset_name, relative_path))
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
