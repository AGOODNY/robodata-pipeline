from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.lerobot_service import DatasetNotFoundError, hdf5_frame, hdf5_frames

router = APIRouter()


@router.get("/datasets/{dataset_name}/episodes/{episode_index}/frames")
def episode_frames(dataset_name: str, episode_index: int, camera: str):
    try:
        return hdf5_frames(dataset_name, episode_index, camera)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/hdf5-media/{dataset_name}/{episode_index}/{camera}/{frame_index}")
def episode_frame_media(dataset_name: str, episode_index: int, camera: str, frame_index: int):
    try:
        image = hdf5_frame(dataset_name, episode_index, camera, frame_index)
        from PIL import Image
        buffer = BytesIO()
        Image.fromarray(image).save(buffer, format="JPEG", quality=90)
        return Response(buffer.getvalue(), media_type="image/jpeg")
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
