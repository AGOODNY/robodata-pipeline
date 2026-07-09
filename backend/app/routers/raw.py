from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    RawDatasetListItem,
    RawDatasetSummary,
    RawEpisodeDetail,
    RawEpisodeListItem,
    RawEpisodeSeries,
    RawFrameList,
)
from app.services.raw_service import (
    RawDatasetNotFoundError,
    get_raw_episode,
    get_raw_frames,
    get_raw_series,
    get_raw_summary,
    list_raw_datasets,
    list_raw_episodes,
)

router = APIRouter()


def _not_found(error: RawDatasetNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


@router.get("/raw/datasets", response_model=list[RawDatasetListItem])
def raw_datasets() -> list[RawDatasetListItem]:
    return list_raw_datasets()


@router.get("/raw/datasets/{raw_name}/episodes", response_model=list[RawEpisodeListItem])
def raw_episodes(raw_name: str) -> list[RawEpisodeListItem]:
    try:
        return list_raw_episodes(raw_name)
    except RawDatasetNotFoundError as error:
        raise _not_found(error) from error


@router.get("/raw/datasets/{raw_name}/summary", response_model=RawDatasetSummary)
def raw_summary(raw_name: str) -> RawDatasetSummary:
    try:
        return get_raw_summary(raw_name)
    except RawDatasetNotFoundError as error:
        raise _not_found(error) from error


@router.get("/raw/datasets/{raw_name}/episodes/{episode_name}", response_model=RawEpisodeDetail)
def raw_episode(raw_name: str, episode_name: str) -> RawEpisodeDetail:
    try:
        return get_raw_episode(raw_name, episode_name)
    except RawDatasetNotFoundError as error:
        raise _not_found(error) from error


@router.get("/raw/datasets/{raw_name}/episodes/{episode_name}/frames", response_model=RawFrameList)
def raw_frames(raw_name: str, episode_name: str, camera: str) -> RawFrameList:
    try:
        return get_raw_frames(raw_name, episode_name, camera)
    except RawDatasetNotFoundError as error:
        raise _not_found(error) from error


@router.get("/raw/datasets/{raw_name}/episodes/{episode_name}/series", response_model=RawEpisodeSeries)
def raw_series(raw_name: str, episode_name: str) -> RawEpisodeSeries:
    try:
        return get_raw_series(raw_name, episode_name)
    except RawDatasetNotFoundError as error:
        raise _not_found(error) from error
