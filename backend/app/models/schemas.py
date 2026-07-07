from typing import Any, Literal

from pydantic import BaseModel


class DatasetListItem(BaseModel):
    name: str
    path: str
    codebase_version: str | None = None
    robot_type: str | None = None
    total_episodes: int | None = None
    total_frames: int | None = None
    fps: float | None = None


class HealthResponse(BaseModel):
    status: str
    app: str


class DatasetSummary(BaseModel):
    name: str
    path: str
    codebase_version: str | None = None
    robot_type: str | None = None
    total_episodes: int | None = None
    total_frames: int | None = None
    total_tasks: int | None = None
    fps: float | None = None
    features: dict[str, Any]
    tasks: list[dict[str, Any]]
    stats: dict[str, Any]


class VideoAsset(BaseModel):
    key: str
    relative_path: str
    url: str
    exists: bool
    from_timestamp: float | None = None
    to_timestamp: float | None = None


class EpisodeListItem(BaseModel):
    episode_index: int
    tasks: list[str]
    length: int
    dataset_from_index: int | None = None
    dataset_to_index: int | None = None
    videos: list[VideoAsset]


class EpisodeDetail(EpisodeListItem):
    stats: dict[str, Any]


class EpisodeSeries(BaseModel):
    episode_index: int
    timestamp: list[float]
    observation_state: list[list[float]]
    action: list[list[float]]
    state_names: list[str]
    action_names: list[str]


class ValidationIssue(BaseModel):
    level: Literal["error", "warning", "info"]
    code: str
    message: str
    path: str | None = None
