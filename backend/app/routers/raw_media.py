from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.raw_service import RawDatasetNotFoundError, raw_media_file

router = APIRouter()


@router.get("/raw-media/{raw_name}/{episode_name}/{relative_path:path}")
def raw_media(raw_name: str, episode_name: str, relative_path: str) -> FileResponse:
    try:
        return FileResponse(raw_media_file(raw_name, episode_name, relative_path))
    except RawDatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
