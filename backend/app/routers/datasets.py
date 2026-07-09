from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    DatasetListItem,
    DatasetSummary,
    EpisodeDetail,
    EpisodeListItem,
    EpisodeSeries,
)
from app.services.lerobot_service import (
    DatasetNotFoundError,
    get_episode,
    get_episode_series,
    get_summary,
    list_datasets,
    list_episodes,
)

router = APIRouter()


def _not_found(error: DatasetNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


@router.get("/datasets", response_model=list[DatasetListItem])
def datasets() -> list[DatasetListItem]:
    return list_datasets()


@router.get("/datasets/{dataset_name}/summary", response_model=DatasetSummary)
def dataset_summary(dataset_name: str) -> DatasetSummary:
    try:
        return get_summary(dataset_name)
    except DatasetNotFoundError as error:
        raise _not_found(error) from error


@router.get("/datasets/{dataset_name}/episodes", response_model=list[EpisodeListItem])
def dataset_episodes(dataset_name: str) -> list[EpisodeListItem]:
    try:
        return list_episodes(dataset_name)
    except DatasetNotFoundError as error:
        raise _not_found(error) from error


@router.get("/datasets/{dataset_name}/episodes/{episode_index}", response_model=EpisodeDetail)
def dataset_episode(dataset_name: str, episode_index: int) -> EpisodeDetail:
    try:
        return get_episode(dataset_name, episode_index)
    except DatasetNotFoundError as error:
        raise _not_found(error) from error


@router.get("/datasets/{dataset_name}/episodes/{episode_index}/series", response_model=EpisodeSeries)
def dataset_episode_series(dataset_name: str, episode_index: int) -> EpisodeSeries:
    try:
        return get_episode_series(dataset_name, episode_index)
    except DatasetNotFoundError as error:
        raise _not_found(error) from error
